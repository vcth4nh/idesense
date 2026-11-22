package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.tools.models.SearchTextResult
import com.intellij.openapi.roots.ModuleRootManager
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.PsiTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * The excluded-path rules of `ide_search_text` (`ExcludedPathScope`) test the path of a file
 * relative to the project base path, or, for a file outside the base path, relative to its
 * content root (#148).
 */
class SearchTextToolExcludedPathTest : BasePlatformTestCase() {

    private val json = Json { ignoreUnknownKeys = true }
    private val addedContentRoots = mutableListOf<VirtualFile>()
    private val createdPaths = mutableListOf<Path>()

    override fun tearDown() {
        try {
            addedContentRoots.forEach { PsiTestUtil.removeContentEntry(module, it) }
            createdPaths.forEach { it.toFile().deleteRecursively() }
            LocalFileSystem.getInstance().refreshNioFiles(createdPaths)
        } catch (e: Throwable) {
            addSuppressedException(e)
        } finally {
            super.tearDown()
        }
    }

    // Case a of #148: a folder above a content root outside the base path has the name of a
    // deep rule. The rules must not see it.
    fun testAParentFolderOfAContentRootOutsideTheBasePathDoesNotExcludeItsFiles() {
        val root = newFolderOutsideTheBasePath().resolve("node_modules/shared-src")
        writeFile(root, "Probe.txt", "probewordparent")
        addContentRoot(root)

        assertEquals("Content root: $root", setOf("Probe.txt"), filesWith("probewordparent"))
    }

    // Case b of #148: a root-only rule applies at a content root outside the base path, as it
    // applies at the base path.
    fun testARootOnlyRuleAppliesAtAContentRootOutsideTheBasePath() {
        val root = newFolderOutsideTheBasePath().resolve("lib")
        writeFile(root, "build/Gen.txt", "probewordbuild")
        writeFile(root, "src/build/Keep.txt", "probewordbuild")
        addContentRoot(root)

        assertEquals("Content root: $root", setOf("src/build/Keep.txt"), filesWith("probewordbuild"))
    }

    // Case c of #148: a folder beside the base path whose name starts with the name of the base
    // path folder. Its files are not below the base path.
    fun testAFolderBesideTheBasePathWithTheSameNamePrefixIsNotBelowTheBasePath() {
        val root = Path.of(basePath() + "bin")
        createdPaths.add(root)
        writeFile(root, "Probe.txt", "probewordsibling")
        addContentRoot(root)

        assertEquals("Content root: $root", setOf("Probe.txt"), filesWith("probewordsibling"))
    }

    // A project with one content root at the base path: the rules see the path relative to the
    // base path, as before #148.
    fun testTheRulesApplyToThePathBelowTheBasePath() {
        val base = Path.of(basePath())
        createdPaths.add(base.resolve("build"))
        createdPaths.add(base.resolve("src148"))
        writeFile(base, "build/Gen.txt", "probewordbase")
        writeFile(base, "src148/build/Keep.txt", "probewordbase")
        writeFile(base, "src148/node_modules/dep/Dep.txt", "probewordbase")
        writeFile(base, "src148/Main.txt", "probewordbase")
        addContentRoot(base)

        assertEquals(
            "Base path: $base",
            setOf("src148/build/Keep.txt", "src148/Main.txt"),
            filesWith("probewordbase")
        )
    }

    // A content root inside the base path, for example the folder of a module: the rules still
    // see the path relative to the base path. `sub148/build/` is not at the base path.
    fun testAContentRootInsideTheBasePathKeepsThePathRelativeToTheBasePath() {
        val base = Path.of(basePath())
        val sub = base.resolve("sub148")
        createdPaths.add(sub)
        writeFile(sub, "build/Gen.txt", "probewordnested")
        addContentRoot(base)
        addContentRoot(sub)

        assertEquals("Base path: $base", setOf("sub148/build/Gen.txt"), filesWith("probewordnested"))
    }

    private fun basePath(): String = requireNotNull(project.basePath) { "The test project needs a base path" }

    private fun newFolderOutsideTheBasePath(): Path =
        Files.createTempDirectory("idesense-148-").also { createdPaths.add(it) }

    private fun writeFile(root: Path, relativePath: String, word: String) {
        val file = root.resolve(relativePath)
        Files.createDirectories(file.parent)
        Files.writeString(file, "$word\n")
    }

    /** Adds [root] as a content root of the module, if it is not one, and waits for the index. */
    private fun addContentRoot(root: Path) {
        val dir = requireNotNull(LocalFileSystem.getInstance().refreshAndFindFileByNioFile(root)) {
            "Expected a VFS folder for $root"
        }
        VfsUtil.markDirtyAndRefresh(false, true, true, dir)
        if (dir !in ModuleRootManager.getInstance(module).contentRoots) {
            PsiTestUtil.addContentRoot(module, dir)
            addedContentRoots += dir
        }
        IndexingTestUtil.waitUntilIndexesAreReady(project)
    }

    /** The `file` values of the result of `ide_search_text` for [word]. */
    private fun filesWith(word: String): Set<String> = runBlocking {
        val result = SearchTextTool().execute(project, buildJsonObject { put("query", word) })
        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("The search must succeed: $text", result.isError)
        json.decodeFromString<SearchTextResult>(text).matches.map { it.file }.toSet()
    }
}
