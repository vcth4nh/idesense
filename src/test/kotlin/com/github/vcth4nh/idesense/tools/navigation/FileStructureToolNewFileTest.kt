package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.server.transport.KtorMcpServer
import com.github.vcth4nh.idesense.tools.project.SyncFilesTool
import com.github.vcth4nh.idesense.tools.refactoring.RenameSymbolTool
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.WriteAction
import com.intellij.openapi.roots.libraries.Library
import com.intellij.openapi.vfs.JarFileSystem
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.LoggedErrorProcessor
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.testFramework.PsiTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import java.nio.file.Files
import java.nio.file.Path
import java.util.EnumSet
import java.util.concurrent.Callable
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.jar.JarEntry
import java.util.jar.JarOutputStream

/**
 * ide_file_structure finds its file inside its read action with no refresh of the file system
 * (#314). The platform does no synchronous refresh under a read lock: it logs the error "Do not
 * perform a synchronous refresh under read lock" and does not refresh (`RefreshQueueImpl.execute`).
 * The error names ide_sync_files only for a file of the project that is on the disk and that the
 * IDE does not know yet; each other "File not found" error is the plain text. The tools that take a
 * position give these errors too when their lookup finds no file (#354).
 *
 * The light fixture has an in-memory file system for its source files, but the base path of its
 * project is a real folder, so this test writes the files there with `java.nio`. The calls run on
 * a pooled thread, as a request of the server does: on the EDT of a test, a synchronous refresh is
 * permitted.
 */
class FileStructureToolNewFileTest : BasePlatformTestCase() {

    fun testFileThatTheIdeDoesNotKnowYetGivesAnErrorThatNamesSyncFiles() = withKnownFolder { dir ->
        // A new file from outside the IDE, for example from a git pull.
        val added = dir.resolve("Added.java")
        Files.writeString(added, "class Added {\n    int size() { return 0; }\n}\n")
        val path = "${dir.fileName}/Added.java"
        val args = buildJsonObject { put("file", path) }

        val errors = ConcurrentLinkedQueue<String>()
        val results = mutableMapOf<String, ToolCallResult>()
        LoggedErrorProcessor.executeWith<Throwable>(collectInto(errors)) {
            results["ide_file_structure"] = inRequest { FileStructureTool().execute(project, args) }
            results["ide_read_file"] = inRequest { ReadFileTool().execute(project, args) }
            results["ide_refactor_rename"] = inRequest { RenameSymbolTool().execute(project, renameArgs(path)) }
        }

        assertEquals("Errors logged during the calls", emptyList<String>(), errors.toList())
        for ((tool, result) in results) {
            assertEquals(
                tool,
                "File not found: $path. The file is on the disk, but the IDE does not know it yet: " +
                    "call ide_sync_files, then call again.",
                message(result),
            )
        }
        assertNull("A call refreshed the file system", LocalFileSystem.getInstance().findFileByNioFile(added))

        val sync = inRequest {
            SyncFilesTool().execute(project, buildJsonObject { putJsonArray("paths") { add(path) } })
        }
        assertFalse("ide_sync_files failed: ${text(sync)}", sync.isError)
        IndexingTestUtil.waitUntilIndexesAreReady(project)
        val second = inRequest { FileStructureTool().execute(project, args) }
        assertFalse("Expected the outline: ${text(second)}", second.isError)
        assertTrue(text(second), text(second).contains("size(): int"))
    }

    // A folder is no file: ide_sync_files does not make it a file.
    fun testFolderThatTheIdeDoesNotKnowYetGivesThePlainText() = withKnownFolder { dir ->
        Files.createDirectories(dir.resolve("added"))
        val path = "${dir.fileName}/added"
        val args = buildJsonObject { put("file", path) }

        assertEquals("ide_file_structure", "File not found: $path", message(inRequest { FileStructureTool().execute(project, args) }))
        assertEquals("ide_read_file", "File not found: $path", message(inRequest { ReadFileTool().execute(project, args) }))
    }

    // ide_sync_files does not make a file outside the project known to these tools.
    fun testFileOutsideTheProjectGivesThePlainText() {
        val outside = Path.of(project.basePath!!).parent.resolve("outside-${System.nanoTime()}.java")
        Files.writeString(outside, "class Outside {}\n")
        try {
            val path = outside.toString()

            assertEquals(
                "ide_file_structure",
                "File not found: $path",
                message(inRequest { FileStructureTool().execute(project, buildJsonObject { put("file", path) }) }),
            )
            assertEquals(
                "ide_refactor_rename",
                "File not found: $path",
                message(inRequest { RenameSymbolTool().execute(project, renameArgs(path)) }),
            )
        } finally {
            Files.deleteIfExists(outside)
        }
    }

    // The tools that take a position give the same error when their lookup finds no file (#354).
    // ide_find_definition stands for the six tools of resolveElementFromArguments: each of them uses
    // the lookup that also finds a file of a library.
    fun testPositionToolsGiveAnErrorThatNamesSyncFilesForAFileThatTheIdeDoesNotKnowYet() = withKnownFolder { dir ->
        val added = dir.resolve("Added.java")
        Files.writeString(added, "class Added {\n    int size() { return 0; }\n}\n")
        val path = "${dir.fileName}/Added.java"

        val errors = ConcurrentLinkedQueue<String>()
        var results = emptyMap<String, ToolCallResult>()
        LoggedErrorProcessor.executeWith<Throwable>(collectInto(errors)) {
            results = positionToolResults(path, line = 1, column = 7)
        }

        assertEquals("Errors logged during the calls", emptyList<String>(), errors.toList())
        val hint = "File not found: $path. The file is on the disk, but the IDE does not know it yet: " +
            "call ide_sync_files, then call again."
        assertEquals(results.keys.associateWith { hint }, results.mapValues { message(it.value) })
        assertNull("A call refreshed the file system", LocalFileSystem.getInstance().findFileByNioFile(added))

        // After ide_sync_files each tool finds the file: a position outside the text gives its
        // "no element" text.
        val sync = inRequest {
            SyncFilesTool().execute(project, buildJsonObject { putJsonArray("paths") { add(path) } })
        }
        assertFalse("ide_sync_files failed: ${text(sync)}", sync.isError)
        IndexingTestUtil.waitUntilIndexesAreReady(project)
        assertNoElementTexts(path)
    }

    fun testPositionToolsGiveThePlainTextForAPathThatIsNotOnTheDisk() {
        val path = "nonexistent/Missing.java"
        val results = positionToolResults(path, line = 1, column = 1)
        assertEquals(results.keys.associateWith { "File not found: $path" }, results.mapValues { message(it.value) })
        // The two forms of a path into a library, for a jar that is not on the disk: the plain text.
        for (library in listOf("jar:///nonexistent/lib.jar!/demo/Missing.class", "lib/missing.jar!/demo/Missing.class")) {
            val result = inRequest { FindDefinitionTool().execute(project, positionArgs(library, line = 1, column = 1)) }
            assertEquals(library, "File not found: $library", message(result))
        }
    }

    // A file that the IDE knows, with no element at the position: the text of each tool does not change.
    fun testPositionToolsKeepTheNoElementTextForAFileThatTheIdeKnows() = withKnownFolder { dir ->
        assertNoElementTexts("${dir.fileName}/Known.java")
    }

    // A file outside the project that the IDE knows: the lookup of each tool rejects it (it is no
    // file of the project or of a library), so each tool gives the plain text, as ide_file_structure.
    fun testFileOutsideTheProjectThatTheIdeKnowsGivesThePlainTextOfThePositionTools() {
        val outside = Path.of(project.basePath!!).parent.resolve("outside-${System.nanoTime()}.java")
        Files.writeString(outside, "class Outside {}\n")
        var known: VirtualFile? = null
        try {
            known = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(outside)
            assertNotNull("The IDE does not know $outside", known)
            IndexingTestUtil.waitUntilIndexesAreReady(project)
            val path = outside.toString()
            val results = positionToolResults(path, line = 1, column = 7)
            assertEquals(results.keys.associateWith { "File not found: $path" }, results.mapValues { message(it.value) })
        } finally {
            val file = known
            if (file != null) WriteAction.run<Throwable> { file.delete(this) }
            Files.deleteIfExists(outside)
        }
    }

    // A file of a library that the IDE knows, with no element at the position: the "no element" text.
    // The project lookup does not find a jar entry: only the lookup of the six tools finds it.
    fun testLibraryFileThatTheIdeKnowsKeepsTheNoElementTextOfThePositionTools() {
        val jar = Path.of(project.basePath!!).parent.resolve("library-${System.nanoTime()}.jar")
        JarOutputStream(Files.newOutputStream(jar)).use { out ->
            out.putNextEntry(JarEntry("demo/Sample.txt"))
            out.write("hello\n".toByteArray())
            out.closeEntry()
        }
        var jarFile: VirtualFile? = null
        var library: Library? = null
        try {
            jarFile = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(jar)
            val jarRoot = JarFileSystem.getInstance().getJarRootForLocalFile(jarFile!!)!!
            library = PsiTestUtil.addProjectLibrary(module, "library-354", listOf(jarRoot), emptyList())
            val path = "jar://${jar.toString().replace('\\', '/')}!/demo/Sample.txt"
            val result = inRequest { FindDefinitionTool().execute(project, positionArgs(path, line = 99, column = 1)) }
            assertEquals("No element found at position $path:99:1", message(result))
        } finally {
            library?.let { PsiTestUtil.removeLibrary(module, it) }
            val file = jarFile
            if (file != null) WriteAction.run<Throwable> { file.delete(this) }
            Files.deleteIfExists(jar)
        }
    }

    // A relative path that names a file that the IDE knows below a second content root, outside the
    // base path, with no element at the position: the "no element" text, no sync hint. The lookup of
    // the six tools and the project lookup both find this file (#357).
    fun testFileBelowAnotherContentRootThatTheIdeKnowsGetsNoSyncHint() =
        withContentRootOutsideTheBasePath(mapOf("InContentRoot.java" to "class InContentRoot {}\n")) {
            val path = "InContentRoot.java"
            val result = inRequest { FindDefinitionTool().execute(project, positionArgs(path, line = 99, column = 1)) }
            assertEquals("No element found at position $path:99:1", message(result))
        }

    // The tools give a file below a second content root, outside the base path, with a path relative
    // to that content root (ProjectUtils.getRelativePath). The six tools find the file by that path
    // (#357). ide_find_definition stands for them.
    fun testPositionToolsFindAFileBelowAnotherContentRootByItsRelativePath() =
        withContentRootOutsideTheBasePath(mapOf("InContentRoot.java" to IN_CONTENT_ROOT)) {
            val path = "InContentRoot.java"
            val result = inRequest { FindDefinitionTool().execute(project, positionArgs(path, line = 2, column = 5)) }
            assertFalse("Expected the definition: ${text(result)}", result.isError)
            assertEquals(path, result.structuredContent?.get("file")?.jsonPrimitive?.content)
            assertEquals(1, result.structuredContent?.get("line")?.jsonPrimitive?.int)
            // A relative path below no root: the plain text, as before.
            val missing = inRequest { FindDefinitionTool().execute(project, positionArgs("Missing.java", line = 1, column = 1)) }
            assertEquals("File not found: Missing.java", message(missing))
        }

    fun testReadFileFindsAFileBelowAnotherContentRootByItsRelativePath() =
        withContentRootOutsideTheBasePath(mapOf("InContentRoot.java" to IN_CONTENT_ROOT)) {
            val result = inRequest { ReadFileTool().execute(project, buildJsonObject { put("file", "InContentRoot.java") }) }
            assertFalse("Expected the content: ${text(result)}", result.isError)
            assertEquals(IN_CONTENT_ROOT, result.structuredContent?.get("content")?.jsonPrimitive?.content)
            // A relative path below no root: the plain text, as before.
            val missing = inRequest { ReadFileTool().execute(project, buildJsonObject { put("file", "Missing.java") }) }
            assertEquals("File not found: Missing.java", message(missing))
        }

    // The same relative path below the base path and below a second content root: each tool takes the
    // file below the base path, as resolveFile does. The file below the content root has no element at
    // the position.
    fun testRelativePathBelowTheBasePathAndAnotherContentRootGivesTheFileBelowTheBasePath() = withKnownFolder { dir ->
        val path = "${dir.fileName}/Same.java"
        val belowBasePath = dir.resolve("Same.java")
        val source = "class Same {\n    Same self() { return this; }\n}\n"
        Files.writeString(belowBasePath, source)
        assertNotNull(LocalFileSystem.getInstance().refreshAndFindFileByNioFile(belowBasePath))
        withContentRootOutsideTheBasePath(mapOf(path to "class Same {}\n")) {
            val definition = inRequest { FindDefinitionTool().execute(project, positionArgs(path, line = 2, column = 5)) }
            assertFalse("Expected the definition: ${text(definition)}", definition.isError)
            assertEquals(1, definition.structuredContent?.get("line")?.jsonPrimitive?.int)
            val read = inRequest { ReadFileTool().execute(project, buildJsonObject { put("file", path) }) }
            assertEquals(source, read.structuredContent?.get("content")?.jsonPrimitive?.content)
        }
    }

    /** The answers of ide_find_definition, of the rename at a position and of ide_type_hierarchy. */
    private fun positionToolResults(path: String, line: Int, column: Int): Map<String, ToolCallResult> {
        val args = positionArgs(path, line, column)
        val renameArgs = buildJsonObject {
            put("file", path)
            put("line", line)
            put("column", column)
            put("newName", "Renamed")
        }
        return mapOf(
            "ide_find_definition" to inRequest { FindDefinitionTool().execute(project, args) },
            "ide_refactor_rename" to inRequest { RenameSymbolTool().execute(project, renameArgs) },
            "ide_type_hierarchy" to inRequest { TypeHierarchyTool().execute(project, args) },
        )
    }

    /** Asserts the "no element" text of each tool for [path] at a line after the end of the file. */
    private fun assertNoElementTexts(path: String) {
        val results = positionToolResults(path, line = 99, column = 1)
        assertEquals("No element found at position $path:99:1", message(results.getValue("ide_find_definition")))
        assertEquals("No element found at the specified position", message(results.getValue("ide_refactor_rename")))
        assertEquals(
            "No class found at the specified file/line/column position.",
            message(results.getValue("ide_type_hierarchy")),
        )
    }

    private fun positionArgs(path: String, line: Int, column: Int): JsonObject = buildJsonObject {
        put("file", path)
        put("line", line)
        put("column", column)
    }

    /**
     * Runs [block] with a new folder below the base path that the IDE knows with each of its files,
     * as a folder of an open project. A folder of its own for each run: the file system of the IDE
     * persists between test runs.
     */
    private fun withKnownFolder(block: (Path) -> Unit) {
        val dir = Files.createDirectories(Path.of(project.basePath!!).resolve("new-file-${System.nanoTime()}"))
        var knownDir: VirtualFile? = null
        try {
            Files.writeString(dir.resolve("Known.java"), "class Known {}\n")
            knownDir = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(dir)!!
            assertEquals(listOf("Known.java"), knownDir.children.map { it.name })
            IndexingTestUtil.waitUntilIndexesAreReady(project)
            block(dir)
        } finally {
            // Through the file system of the IDE: a refresh of the base folder would make the IDE
            // know each file there, and another test writes a file there with java.nio.
            val known = knownDir
            if (known != null) WriteAction.run<Throwable> { known.delete(this) } else dir.toFile().deleteRecursively()
            IndexingTestUtil.waitUntilIndexesAreReady(project)
        }
    }

    /**
     * Runs [block] with a second content root of the module: a new folder outside the base path with
     * [files] (a relative path to its text), which the IDE knows with each of its files.
     */
    private fun withContentRootOutsideTheBasePath(files: Map<String, String>, block: () -> Unit) {
        val dir = Files.createDirectories(Path.of(project.basePath!!).parent.resolve("content-root-${System.nanoTime()}"))
        for ((path, text) in files) {
            val file = dir.resolve(path)
            Files.createDirectories(file.parent)
            Files.writeString(file, text)
        }
        var root: VirtualFile? = null
        var added = false
        try {
            root = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(dir)!!
            VfsUtil.markDirtyAndRefresh(false, true, true, root)
            for (path in files.keys) assertNotNull("The IDE does not know $path", root.findFileByRelativePath(path))
            PsiTestUtil.addContentRoot(module, root)
            added = true
            IndexingTestUtil.waitUntilIndexesAreReady(project)
            block()
        } finally {
            val known = root
            if (added) PsiTestUtil.removeContentEntry(module, known!!)
            if (known != null) WriteAction.run<Throwable> { known.delete(this) }
            dir.toFile().deleteRecursively()
            IndexingTestUtil.waitUntilIndexesAreReady(project)
        }
    }

    private fun renameArgs(path: String): JsonObject = buildJsonObject {
        put("file", path)
        put("newName", "Renamed.java")
    }

    /** Runs [block] on a pooled thread in the context of a request of the server. */
    private fun inRequest(block: suspend () -> ToolCallResult): ToolCallResult = PlatformTestUtil.waitForFuture(
        ApplicationManager.getApplication().executeOnPooledThread(Callable {
            runBlocking { KtorMcpServer.runWithIdeModality(block) }
        }),
        TIMEOUT_MS,
    )

    /** Keeps each error that the IDE logs, and lets the IDE write it to its log and go on. */
    private fun collectInto(errors: MutableCollection<String>) = object : LoggedErrorProcessor() {
        override fun processError(category: String, message: String, details: Array<out String>, t: Throwable?): Set<Action> {
            errors.add("$category: $message")
            return EnumSet.of(Action.LOG)
        }
    }

    /** The message of an error result. */
    private fun message(result: ToolCallResult): String? {
        assertTrue("Expected an error: ${text(result)}", result.isError)
        return result.structuredContent?.get("message")?.jsonPrimitive?.content
    }

    private fun text(result: ToolCallResult): String = (result.content.first() as ContentBlock.Text).text

    private companion object {
        const val TIMEOUT_MS = 30_000L

        /** A class with a reference to itself at line 2, column 5. */
        const val IN_CONTENT_ROOT = "class InContentRoot {\n    InContentRoot self() { return this; }\n}\n"
    }
}
