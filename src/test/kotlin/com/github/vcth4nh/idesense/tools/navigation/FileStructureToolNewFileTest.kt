package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.server.transport.KtorMcpServer
import com.github.vcth4nh.idesense.tools.project.SyncFilesTool
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.WriteAction
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.LoggedErrorProcessor
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import java.nio.file.Files
import java.nio.file.Path
import java.util.EnumSet
import java.util.concurrent.Callable
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * ide_file_structure finds its file inside its read action with no refresh of the file system
 * (#314). The platform does no synchronous refresh under a read lock: it logs the error "Do not
 * perform a synchronous refresh under read lock" and does not refresh (`RefreshQueueImpl.execute`).
 *
 * The light fixture has an in-memory file system for its source files, but the base path of its
 * project is a real folder, so this test writes the files there with `java.nio`. The calls run on
 * a pooled thread, as a request of the server does: on the EDT of a test, a synchronous refresh is
 * permitted.
 */
class FileStructureToolNewFileTest : BasePlatformTestCase() {

    fun testFileThatTheIdeDoesNotKnowYetGivesAnErrorThatNamesSyncFiles() {
        // A folder of its own for each run: the file system of the IDE persists between test runs.
        val dir = Files.createDirectories(Path.of(project.basePath!!).resolve("new-file-${System.nanoTime()}"))
        Files.writeString(dir.resolve("Known.java"), "class Known {}\n")
        // The IDE knows the folder and each of its files, as a folder of an open project.
        val knownDir = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(dir)!!
        try {
            assertEquals(listOf("Known.java"), knownDir.children.map { it.name })
            IndexingTestUtil.waitUntilIndexesAreReady(project)
            // A new file from outside the IDE, for example from a git pull.
            val added = dir.resolve("Added.java")
            Files.writeString(added, "class Added {\n    int size() { return 0; }\n}\n")
            val path = "${dir.fileName}/Added.java"
            val args = buildJsonObject { put("file", path) }

            val errors = ConcurrentLinkedQueue<String>()
            var first: ToolCallResult? = null
            LoggedErrorProcessor.executeWith<Throwable>(collectInto(errors)) {
                first = inRequest { FileStructureTool().execute(project, args) }
            }

            assertEquals("Errors logged during the call", emptyList<String>(), errors.toList())
            assertTrue("Expected an error: ${text(first!!)}", first!!.isError)
            assertEquals(
                "File not found: $path. If the file exists on the disk, the IDE does not know it yet: " +
                    "call ide_sync_files, then call again.",
                first!!.structuredContent?.get("message")?.jsonPrimitive?.content,
            )
            assertNull("The call refreshed the file system", LocalFileSystem.getInstance().findFileByNioFile(added))

            val sync = inRequest {
                SyncFilesTool().execute(project, buildJsonObject { putJsonArray("paths") { add(path) } })
            }
            assertFalse("ide_sync_files failed: ${text(sync)}", sync.isError)
            IndexingTestUtil.waitUntilIndexesAreReady(project)
            val second = inRequest { FileStructureTool().execute(project, args) }
            assertFalse("Expected the outline: ${text(second)}", second.isError)
            assertTrue(text(second), text(second).contains("size(): int"))
        } finally {
            // Through the file system of the IDE: a refresh of the base folder would make the IDE
            // know each file there, and another test writes a file there with java.nio.
            WriteAction.run<Throwable> { knownDir.delete(this) }
            IndexingTestUtil.waitUntilIndexesAreReady(project)
        }
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

    private fun text(result: ToolCallResult): String = (result.content.first() as ContentBlock.Text).text

    private companion object {
        const val TIMEOUT_MS = 30_000L
    }
}
