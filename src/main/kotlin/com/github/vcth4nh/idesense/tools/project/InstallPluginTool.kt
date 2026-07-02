package com.github.vcth4nh.idesense.tools.project

import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.InstallPluginResult
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.intellij.openapi.application.PathManager
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.io.FileUtil
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path
import java.util.zip.ZipFile
import java.util.zip.ZipInputStream

/**
 * Installs a locally built plugin distribution (`.zip`) into THIS IDE's custom plugins
 * directory ([PathManager.getPluginsDir]), replacing any prior copy of the same plugin.
 *
 * This is half of the local plugin dev loop: `ide_install_plugin` stages the new bits on
 * disk, [RestartIdeTool] (`ide_restart`) makes the IDE pick them up. They are split because
 * this plugin is not dynamically reloadable (app-level Ktor service + listeners), so the
 * running code keeps serving until the IDE restarts.
 *
 * The unpack is a plain JDK unzip (with zip-slip guarding) rather than the platform's
 * internal `PluginInstaller`, so it is stable across IDE versions and fully headless.
 */
class InstallPluginTool : AbstractMcpTool() {

    companion object {
        private val LOG = logger<InstallPluginTool>()
        private val PLUGIN_XML_ID = Regex("<id>([^<]+)</id>")
        private val PLUGIN_XML_VERSION = Regex("<version>([^<]+)</version>")
    }

    override val requiresPsiSync: Boolean = false

    override val name = ToolNames.INSTALL_PLUGIN

    override val description = """
        Install a locally built plugin .zip into this IDE's custom plugins directory, replacing any
        existing copy. Use as the first half of the dev loop: build → install → ide_restart. The new
        code does NOT take effect until the IDE restarts — always follow with ide_restart.

        When path is omitted, picks the newest *.zip in <project>/build/distributions/ automatically.

        Returns: source zip path, installed plugin directory, detected pluginId/pluginVersion
        (best-effort from META-INF/plugin.xml), restartRequired (always true).

        Gotchas: disabled by default — must be enabled in Settings → Tools → IdeSense. Plugin is
        not dynamically reloadable; restart is mandatory.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .stringProperty(
            ParamNames.PATH,
            "Path to the plugin .zip. Absolute, or relative to the project root. Default: newest *.zip in <project>/build/distributions/."
        )
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val pathArg = arguments[ParamNames.PATH]?.jsonPrimitive?.content?.takeIf { it.isNotBlank() }

        val sourceZip = resolveSourceZip(project, pathArg)
            ?: return createErrorResult(
                if (pathArg != null) "Plugin zip not found: $pathArg"
                else "No *.zip found in <project>/build/distributions/. Build the plugin first (./gradlew buildPlugin) or pass an explicit \"path\"."
            )

        if (!sourceZip.isFile || !sourceZip.name.endsWith(".zip", ignoreCase = true)) {
            return createErrorResult("Not a .zip file: ${sourceZip.absolutePath}")
        }

        return withContext(Dispatchers.IO) {
            val rootDir = try {
                readPluginRootDir(sourceZip)
            } catch (e: Exception) {
                LOG.warn("Failed to read plugin zip ${sourceZip.absolutePath}", e)
                return@withContext createErrorResult("Invalid plugin zip (${sourceZip.name}): ${e.message}")
            } ?: return@withContext createErrorResult(
                "Plugin zip ${sourceZip.name} has no single top-level plugin directory; not a directory-style IntelliJ plugin distribution."
            )

            val pluginsDir = PathManager.getPluginsDir()
            val target = pluginsDir.resolve(rootDir)

            try {
                // Clean replace: remove any existing copy of this plugin first.
                val existing = target.toFile()
                if (existing.exists() && !FileUtil.delete(existing)) {
                    return@withContext createErrorResult(
                        "Could not remove existing plugin install at ${existing.absolutePath} (is the IDE locking it?)."
                    )
                }
                Files.createDirectories(pluginsDir)
                unzipInto(sourceZip, pluginsDir)

                val (pluginId, pluginVersion) = readPluginCoordinates(target)

                createJsonResult(
                    InstallPluginResult(
                        installed = true,
                        source = sourceZip.absolutePath,
                        pluginDir = target.toString(),
                        pluginId = pluginId,
                        pluginVersion = pluginVersion,
                        restartRequired = true,
                        message = "Installed into $target. Call ide_restart to load it — the running plugin keeps the old code until the IDE restarts."
                    )
                )
            } catch (e: Exception) {
                LOG.warn("Plugin install failed", e)
                createErrorResult("Plugin install failed: ${e.message}")
            }
        }
    }

    private fun resolveSourceZip(project: Project, pathArg: String?): File? {
        if (pathArg != null) {
            val f = File(pathArg)
            val resolved = if (f.isAbsolute) f else File(project.basePath ?: ".", pathArg)
            return resolved.takeIf { it.isFile }
        }
        val basePath = project.basePath ?: return null
        val dist = File(basePath, "build/distributions")
        if (!dist.isDirectory) return null
        return dist.listFiles { _, n -> n.endsWith(".zip", ignoreCase = true) }
            ?.maxByOrNull { it.lastModified() }
    }

    /** The single top-level directory name inside the zip, or null if not exactly one. */
    private fun readPluginRootDir(zip: File): String? {
        ZipFile(zip).use { zf ->
            val roots = zf.entries().asSequence()
                .map { it.name.substringBefore('/') }
                .filter { it.isNotEmpty() }
                .toSet()
            return roots.singleOrNull()
        }
    }

    private fun unzipInto(zip: File, destDir: Path) {
        val destCanonical = destDir.toFile().canonicalFile
        ZipInputStream(zip.inputStream().buffered()).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                val outFile = File(destCanonical, entry.name).canonicalFile
                // Zip-slip protection: every entry must stay inside destDir.
                if (outFile.path != destCanonical.path &&
                    !outFile.path.startsWith(destCanonical.path + File.separator)
                ) {
                    throw IOException("Zip entry escapes target directory: ${entry.name}")
                }
                if (entry.isDirectory) {
                    outFile.mkdirs()
                } else {
                    outFile.parentFile?.mkdirs()
                    outFile.outputStream().use { os -> zis.copyTo(os) }
                }
                zis.closeEntry()
                entry = zis.nextEntry
            }
        }
    }

    /** Best-effort: pull <id>/<version> from META-INF/plugin.xml in one of the unpacked lib jars. */
    private fun readPluginCoordinates(pluginDir: Path): Pair<String?, String?> {
        return try {
            val libDir = pluginDir.resolve("lib").toFile()
            val jars = libDir.listFiles { _, n -> n.endsWith(".jar", ignoreCase = true) }
                ?: return null to null
            for (jar in jars) {
                ZipFile(jar).use { zf ->
                    val e = zf.getEntry("META-INF/plugin.xml") ?: return@use
                    val xml = zf.getInputStream(e).use { it.readBytes() }.toString(Charsets.UTF_8)
                    val id = PLUGIN_XML_ID.find(xml)?.groupValues?.get(1)?.trim()
                    val version = PLUGIN_XML_VERSION.find(xml)?.groupValues?.get(1)?.trim()
                    if (id != null || version != null) return id to version
                }
            }
            null to null
        } catch (e: Exception) {
            LOG.debug("Could not read plugin coordinates", e)
            null to null
        }
    }
}
