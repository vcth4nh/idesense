package com.github.vcth4nh.idesense.tools.refactoring

import com.github.vcth4nh.idesense.exceptions.IndexNotReadyException
import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.server.transport.KtorMcpServer
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.RefactoringResult
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.WriteAction
import com.intellij.openapi.extensions.LoadingOrder
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement
import com.intellij.refactoring.rename.naming.AutomaticRenamer
import com.intellij.refactoring.rename.naming.AutomaticRenamerFactory
import com.intellij.testFramework.DumbModeTestUtils
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.testFramework.PsiTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.intellij.usageView.UsageInfo
import com.intellij.util.FileContentUtilCore
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Platform tests for #295: `ide_refactor_rename` and `ide_move_file` check for dumb mode at their
 * start, and the IDE can enter dumb mode after that check. A refactoring processor of the platform
 * that meets dumb mode makes no change and throws nothing (`BaseRefactoringProcessor.doRun`).
 *
 * A tool runs on a pooled thread, as in a request, and its step on the EDT goes through the event
 * queue. Most tests start dumb mode inside that step, after the dumb mode check of the tool and
 * before the processor runs: a rename through an [AutomaticRenamerFactory] that the tool asks for
 * its option name, a move through [MoveFileTool.executeGenericFileMove].
 */
class RefactoringDumbModeTest : BasePlatformTestCase() {

    private val json = Json { ignoreUnknownKeys = true }
    private lateinit var root: Path
    private lateinit var sourceRoot: VirtualFile

    override fun setUp() {
        super.setUp()
        root = Path.of(project.basePath!!).resolve("dumb-${getTestName(true)}")
        Files.createDirectories(root.resolve("dumb"))
        Files.writeString(root.resolve(HOLDER), HOLDER_TEXT)
        Files.writeString(root.resolve(NOTES), NOTES_TEXT)
        sourceRoot = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(root)!!
        sourceRoot.refresh(false, true)
        PsiTestUtil.addSourceRoot(module, sourceRoot)
        IndexingTestUtil.waitUntilIndexesAreReady(project)
    }

    override fun tearDown() {
        try {
            PsiTestUtil.removeSourceRoot(module, sourceRoot)
            WriteAction.run<Throwable> { sourceRoot.delete(this) }
        } catch (e: Throwable) {
            addSuppressedException(e)
        } finally {
            AbstractMcpTool.indexWaitLimitMs = AbstractMcpTool.INDEX_WAIT_LIMIT_MS
            super.tearDown()
        }
    }

    // The happy path of the rename in a request: no dumb mode, the symbol and its usage get the new name.
    fun testRenameOfASymbolInSmartModeRenamesIt() {
        val result = success(callInRequest { RenameSymbolTool().execute(project, renameCountArgs()) })

        assertTrue(result.message, result.success)
        assertEquals(HOLDER_TEXT.replace("count", "total"), Files.readString(root.resolve(HOLDER)))
    }

    fun testRenameOfASymbolGivesIndexNotReadyWhenDumbModeStartsBeforeTheRename() {
        val hook = dumbModeAtTheRenameStep()

        val outcome = try {
            callInRequest { RenameSymbolTool().execute(project, renameCountArgs()) }
        } finally {
            hook.endDumbMode()
        }

        assertTrue("Dumb mode started inside the step of the rename", hook.started)
        assertEquals("The file did not change", HOLDER_TEXT, Files.readString(root.resolve(HOLDER)))
        assertIndexNotReady(RENAME_TEXT, outcome)
    }

    fun testRenameOfAFileGivesIndexNotReadyWhenDumbModeStartsBeforeTheRename() {
        val hook = dumbModeAtTheRenameStep()

        val outcome = try {
            callInRequest { RenameSymbolTool().execute(project, renameNotesArgs("memo.txt")) }
        } finally {
            hook.endDumbMode()
        }

        assertTrue("Dumb mode started inside the step of the rename", hook.started)
        assertTrue("The file keeps its name", Files.exists(root.resolve(NOTES)))
        assertFalse(Files.exists(root.resolve("dumb/memo.txt")))
        assertIndexNotReady(RENAME_TEXT, outcome)
    }

    // A file name with no extension gets the extension of the file: "notes" is the name "notes.txt".
    fun testRenameOfAFileToItsNameWithNoExtensionGivesTheSameNameError() {
        val outcome = callInRequest { RenameSymbolTool().execute(project, renameNotesArgs("notes")) }

        val result = outcome.getOrThrow()
        assertTrue("The file keeps its name", Files.exists(root.resolve(NOTES)))
        assertTrue("Expected an error, got ${text(result)}", result.isError)
        assertToolError(SAME_NAME, result)
    }

    // RenameProcessor.doRun returns with no change when its element is not valid. The tool reads the
    // element again through its pointer: the element keeps its old name. No dumb mode, so no index_not_ready.
    fun testRenameGivesAnErrorWhenTheProcessorChangesNothingWithNoDumbMode() {
        atTheRenameStep { FileContentUtilCore.reparseFiles(holderFile()) }

        val outcome = callInRequest { RenameSymbolTool().execute(project, renameCountArgs()) }

        assertEquals("The file did not change", HOLDER_TEXT, Files.readString(root.resolve(HOLDER)))
        val result = outcome.getOrThrow()
        assertTrue("Expected an error, got ${text(result)}", result.isError)
        assertToolError(RENAME_NO_CHANGE, result)
    }

    // The happy path of the move in a request.
    fun testMoveInSmartModeMovesTheFile() {
        val result = success(callInRequest { MoveFileTool().execute(project, moveNotesArgs()) })

        assertTrue(result.message, result.success)
        assertFalse(Files.exists(root.resolve(NOTES)))
        assertTrue(Files.exists(root.resolve("archive/notes.txt")))
    }

    fun testMoveGivesIndexNotReadyWhenDumbModeStartsBeforeTheMove() {
        var token: DumbModeTestUtils.EternalTaskShutdownToken? = null
        val tool = object : MoveFileTool() {
            override fun executeGenericFileMove(preparation: MovePreparation) {
                token = DumbModeTestUtils.startEternalDumbModeTask(project)
                super.executeGenericFileMove(preparation)
            }
        }

        val outcome = try {
            callInRequest { tool.execute(project, moveNotesArgs()) }
        } finally {
            token?.let { DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, it) }
        }

        assertNotNull("Dumb mode started inside the step of the move", token)
        assertTrue("The file stays in its folder", Files.exists(root.resolve(NOTES)))
        assertFalse(Files.exists(root.resolve("archive/notes.txt")))
        assertIndexNotReady(MOVE_TEXT, outcome)
    }

    // Dumb mode starts and ends inside the step: the IDE is in smart mode at the end of the move.
    fun testMoveGivesIndexNotReadyWhenDumbModeStartsAndEndsInsideTheStep() {
        var dumbAtTheEnd: Boolean? = null
        val tool = object : MoveFileTool() {
            override fun executeGenericFileMove(preparation: MovePreparation) {
                val token = DumbModeTestUtils.startEternalDumbModeTask(project)
                try {
                    super.executeGenericFileMove(preparation)
                } finally {
                    DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, token)
                }
                dumbAtTheEnd = DumbService.isDumb(project)
            }
        }

        val outcome = callInRequest { tool.execute(project, moveNotesArgs()) }

        assertEquals("Smart mode at the end of the move", false, dumbAtTheEnd)
        assertTrue("The file stays in its folder", Files.exists(root.resolve(NOTES)))
        assertFalse(Files.exists(root.resolve("archive/notes.txt")))
        assertIndexNotReady(MOVE_TEXT, outcome)
    }

    // A move that changes nothing with no dumb mode: the cause is not dumb mode.
    fun testMoveThatChangesNothingWithNoDumbModeGivesAnErrorThatIsNotIndexNotReady() {
        val tool = object : MoveFileTool() {
            override fun executeGenericFileMove(preparation: MovePreparation) {}
        }

        val result = callInRequest { tool.execute(project, moveNotesArgs()) }.getOrThrow()

        assertTrue(Files.exists(root.resolve(NOTES)))
        assertTrue("Expected an error, got ${text(result)}", result.isError)
        assertToolError(MOVE_NO_CHANGE, result)
    }

    // A folder in the target folder with the name of the file is no moved file.
    fun testMoveThatChangesNothingGivesAnErrorWhenTheTargetHasAFolderWithTheNameOfTheFile() {
        Files.createDirectories(root.resolve("archive/notes.txt"))
        LocalFileSystem.getInstance().refreshAndFindFileByNioFile(root.resolve("archive/notes.txt"))!!
        IndexingTestUtil.waitUntilIndexesAreReady(project)
        val tool = object : MoveFileTool() {
            override fun executeGenericFileMove(preparation: MovePreparation) {}
        }

        val result = callInRequest { tool.execute(project, moveNotesArgs()) }.getOrThrow()

        assertTrue(Files.exists(root.resolve(NOTES)))
        assertTrue(Files.isDirectory(root.resolve("archive/notes.txt")))
        assertTrue("Expected an error, got ${text(result)}", result.isError)
        assertToolError(MOVE_NO_CHANGE, result)
    }

    // The step on the EDT starts only in smart mode: in dumb mode it waits for the end of dumb mode.
    fun testStepOnTheEdtWaitsForTheEndOfDumbMode() {
        val ranInDumbMode = mutableListOf<Boolean>()
        val tool = EdtStepTool { ranInDumbMode.add(DumbService.isDumb(project)) }
        val token = DumbModeTestUtils.startEternalDumbModeTask(project)
        var tokenOpen = true
        try {
            val future = ApplicationManager.getApplication().executeOnPooledThread<Result<ToolCallResult>> {
                runCatching { runBlocking { KtorMcpServer.runWithIdeModality { tool.execute(project, buildJsonObject {}) } } }
            }
            val end = System.currentTimeMillis() + DUMB_WINDOW_MS
            while (System.currentTimeMillis() < end) {
                PlatformTestUtil.dispatchAllInvocationEventsInIdeEventQueue()
                Thread.sleep(5)
            }
            assertEquals("The step ran in dumb mode", emptyList<Boolean>(), ranInDumbMode)
            assertFalse("The call ended in dumb mode", future.isDone)

            DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, token)
            tokenOpen = false
            PlatformTestUtil.waitWithEventsDispatching("The call did not end after dumb mode", { future.isDone }, 30)
            assertFalse(future.get().getOrThrow().isError)
            assertEquals("The step ran one time, in smart mode", listOf(false), ranInDumbMode)
        } finally {
            if (tokenOpen) DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, token)
        }
    }

    // The wait has the limit of the wait for the index; after it, the call gets index_not_ready, and
    // the step never runs.
    fun testStepOnTheEdtGivesIndexNotReadyAfterTheWaitLimit() {
        val runs = AtomicInteger()
        val tool = EdtStepTool { runs.incrementAndGet() }
        AbstractMcpTool.indexWaitLimitMs = TEST_WAIT_LIMIT_MS
        val token = DumbModeTestUtils.startEternalDumbModeTask(project)
        var tokenOpen = true
        try {
            val start = System.currentTimeMillis()
            val future = ApplicationManager.getApplication().executeOnPooledThread<Result<ToolCallResult>> {
                runCatching { runBlocking { KtorMcpServer.runWithIdeModality { tool.execute(project, buildJsonObject {}) } } }
            }
            PlatformTestUtil.waitWithEventsDispatching("The call did not end in dumb mode", { future.isDone }, 30)
            val elapsed = System.currentTimeMillis() - start
            val error = future.get().exceptionOrNull()
            assertTrue("Expected index_not_ready, got ${future.get()}", error is IndexNotReadyException)
            assertEquals(EdtStepTool.MESSAGE, error!!.message)
            assertTrue("The call ended after $elapsed ms, before the limit", elapsed >= TEST_WAIT_LIMIT_MS - LIMIT_TOLERANCE_MS)
            assertTrue("The call ended after $elapsed ms, long after the limit", elapsed < 3 * TEST_WAIT_LIMIT_MS + LIMIT_SLACK_MS)

            DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, token)
            tokenOpen = false
            val end = System.currentTimeMillis() + DUMB_WINDOW_MS
            while (System.currentTimeMillis() < end) {
                PlatformTestUtil.dispatchAllInvocationEventsInIdeEventQueue()
                Thread.sleep(5)
            }
            assertEquals("Runs of the step", 0, runs.get())
        } finally {
            if (tokenOpen) DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, token)
        }
    }

    /** Runs [action] in one step on the EDT, in smart mode. */
    private class EdtStepTool(private val action: () -> Unit) : AbstractMcpTool() {
        override val name = "test_edt_step"
        override val description = "Runs one step on the EDT in smart mode."
        override val inputSchema = buildJsonObject {}
        override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
            smartEdtAction(project, MESSAGE) { action() }
            return createSuccessResult("ran")
        }

        companion object {
            const val MESSAGE = "not ready in the test"
        }
    }

    /**
     * Runs [action] one time when the rename tool asks the automatic renamers for their option names:
     * on the EDT, after the dumb mode check of the tool and before the rename processor runs.
     */
    private fun atTheRenameStep(action: () -> Unit) {
        AutomaticRenamerFactory.EP_NAME.point.registerExtension(RenameStepHook(action), LoadingOrder.FIRST, testRootDisposable)
    }

    /** Starts dumb mode at the rename step. */
    private fun dumbModeAtTheRenameStep(): DumbModeAtTheRenameStep {
        val hook = DumbModeAtTheRenameStep(project)
        atTheRenameStep { hook.start() }
        return hook
    }

    private class DumbModeAtTheRenameStep(private val project: Project) {
        private var token: DumbModeTestUtils.EternalTaskShutdownToken? = null
        val started: Boolean get() = token != null

        fun start() {
            token = DumbModeTestUtils.startEternalDumbModeTask(project)
        }

        fun endDumbMode() {
            token?.let { DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, it) }
        }
    }

    private class RenameStepHook(private val action: () -> Unit) : AutomaticRenamerFactory {
        private val armed = AtomicBoolean(true)

        override fun getOptionName(): String? {
            if (ApplicationManager.getApplication().isDispatchThread && armed.compareAndSet(true, false)) action()
            return null
        }

        override fun isApplicable(element: PsiElement) = false
        override fun isEnabled() = false
        override fun setEnabled(enabled: Boolean) {}
        override fun createRenamer(element: PsiElement, newName: String, usages: Collection<UsageInfo>): AutomaticRenamer =
            throw UnsupportedOperationException()
    }

    /** Runs [call] on a pooled thread with the modality of a request, and dispatches the events of the EDT meanwhile. */
    private fun callInRequest(call: suspend () -> ToolCallResult): Result<ToolCallResult> {
        val future = ApplicationManager.getApplication().executeOnPooledThread<Result<ToolCallResult>> {
            runCatching { runBlocking { KtorMcpServer.runWithIdeModality { call() } } }
        }
        PlatformTestUtil.waitWithEventsDispatching("The call did not end", { future.isDone }, 60)
        return future.get()
    }

    private fun assertIndexNotReady(expectedMessage: String, outcome: Result<ToolCallResult>) {
        val error = outcome.exceptionOrNull()
        assertTrue(
            "Expected index_not_ready, got ${outcome.getOrNull()?.let { text(it) } ?: error}",
            error is IndexNotReadyException
        )
        assertEquals(expectedMessage, error!!.message)
    }

    private fun assertToolError(expectedMessage: String, result: ToolCallResult) {
        val body = result.structuredContent!!
        assertEquals("tool_error", body["error"]?.jsonPrimitive?.content)
        assertEquals(expectedMessage, body["message"]?.jsonPrimitive?.content)
    }

    private fun success(outcome: Result<ToolCallResult>): RefactoringResult {
        val result = outcome.getOrThrow()
        assertFalse("The call must succeed: ${text(result)}", result.isError)
        return json.decodeFromString<RefactoringResult>(text(result))
    }

    private fun text(result: ToolCallResult): String = (result.content.first() as ContentBlock.Text).text

    private fun relative(path: String) = "${root.fileName}/$path"

    private fun holderFile() = LocalFileSystem.getInstance().findFileByNioFile(root.resolve(HOLDER))!!

    private fun renameCountArgs() = buildJsonObject {
        val offset = HOLDER_TEXT.indexOf("count")
        put("file", relative(HOLDER))
        put("line", HOLDER_TEXT.substring(0, offset).count { it == '\n' } + 1)
        put("column", offset - HOLDER_TEXT.lastIndexOf('\n', offset - 1))
        put("newName", "total")
    }

    private fun renameNotesArgs(newName: String) = buildJsonObject {
        put("file", relative(NOTES))
        put("newName", newName)
    }

    private fun moveNotesArgs() = buildJsonObject {
        put("file", relative(NOTES))
        put("destination", relative("archive"))
    }

    private companion object {
        const val HOLDER = "dumb/Holder.java"
        const val NOTES = "dumb/notes.txt"
        const val NOTES_TEXT = "notes\n"
        val HOLDER_TEXT = """
            package dumb;

            public class Holder {
                private int count;

                int read() {
                    return count;
                }
            }
        """.trimIndent() + "\n"

        const val RENAME_TEXT = "The IDE went into dumb mode before the rename ran, and nothing changed. " +
            "Wait for the end of the indexing (ide_index_status shows isDumbMode: false), then call again."
        const val MOVE_TEXT = "The IDE went into dumb mode before the move ran, and the file did not move. " +
            "Wait for the end of the indexing (ide_index_status shows isDumbMode: false), then call again."
        const val RENAME_NO_CHANGE = "Rename failed: the element still has its old name."
        const val MOVE_NO_CHANGE = "Move failed: the file did not move."
        const val SAME_NAME = "New name is the same as the current name"

        const val DUMB_WINDOW_MS = 1000L
        const val TEST_WAIT_LIMIT_MS = 500L
        const val LIMIT_TOLERANCE_MS = 50L
        const val LIMIT_SLACK_MS = 2000L
    }
}
