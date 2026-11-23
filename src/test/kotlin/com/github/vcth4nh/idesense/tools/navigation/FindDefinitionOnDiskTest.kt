package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.tools.models.DefinitionResult
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.PsiTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * ide_find_definition on files on the disk (a source root below the project base path), so that
 * the tool can resolve a position by its path.
 */
class FindDefinitionOnDiskTest : BasePlatformTestCase() {

    private val json = Json { ignoreUnknownKeys = true }
    private lateinit var sourceRoot: VirtualFile

    override fun setUp() {
        super.setUp()
        // ide_find_definition resolves a path through LocalFileSystem. The files of
        // myFixture.addFileToProject live in the in-memory temp:// file system, so it cannot find them.
        val root = Files.createDirectories(Path.of(project.basePath!!).resolve("defdisk"))
        write(root, "pkg/Defs.kt", "package probe.def\n\ntypealias DefAlias = String\n")
        write(root, "pkg/Use.kt", "package probe.use\n\nimport probe.def.DefAlias\n\nval x: DefAlias = \"\"\n")
        sourceRoot = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(root)!!
        PsiTestUtil.addSourceRoot(module, sourceRoot)
        IndexingTestUtil.waitUntilIndexesAreReady(project)
    }

    override fun tearDown() {
        try {
            PsiTestUtil.removeSourceRoot(module, sourceRoot)
            // The files are real files on the disk: the fixture does not remove them.
            val dir = Path.of(project.basePath!!).resolve("defdisk")
            if (Files.exists(dir)) Files.walk(dir).use { it.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
        } catch (e: Throwable) {
            addSuppressedException(e)
        } finally {
            super.tearDown()
        }
    }

    private fun write(root: Path, name: String, text: String) {
        val path = root.resolve(name)
        Files.createDirectories(path.parent)
        Files.writeString(path, text)
    }

    /** The definition of the last use of [needle] in [file] (a path below the source root). */
    private fun definitionAt(file: String, needle: String): DefinitionResult = runBlocking {
        val lines = Files.readAllLines(Path.of(sourceRoot.path).resolve(file))
        val hit = lines.withIndex().last { it.value.contains(needle) }
        val result = FindDefinitionTool().execute(project, buildJsonObject {
            put("file", "defdisk/$file")
            put("line", hit.index + 1)
            put("column", hit.value.lastIndexOf(needle) + 1)
        })
        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("Find definition should succeed: $text", result.isError)
        json.decodeFromString<DefinitionResult>(text)
    }

    fun testFindDefinitionGivesQualifiedNameForKotlinTypeAlias() {
        // #278: the IDE gives no qualified name for a Kotlin type alias; the tool gives package + name.
        val def = definitionAt("pkg/Use.kt", "DefAlias")
        assertEquals("TYPE_ALIAS", def.kind)
        assertEquals("probe.def.DefAlias", def.qualifiedName)
    }
}
