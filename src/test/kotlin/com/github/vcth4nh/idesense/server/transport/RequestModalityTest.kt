package com.github.vcth4nh.idesense.server.transport

import com.github.vcth4nh.idesense.tools.intelligence.DiagnosticsAnalysisService
import com.github.vcth4nh.idesense.tools.project.SyncFilesTool
import com.github.vcth4nh.idesense.util.ThreadingUtils
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.application.TransactionGuard
import com.intellij.openapi.application.impl.LaterInvocator
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.buildJsonObject
import java.util.concurrent.Callable
import java.util.concurrent.Future
import java.util.concurrent.atomic.AtomicReference

/**
 * The modality of a request (#145, #147). A request runs on a background thread in the context of
 * [KtorMcpServer.runWithIdeModality]. A model change needs a write-safe modality, and
 * `ModalityState.any()` is not write-safe: the platform logs an error, and in a test a logged
 * error fails the test (`TestLoggerFactory`). `LaterInvocator.enterModal` stands for a modal dialog.
 */
class RequestModalityTest : BasePlatformTestCase() {

    fun testRequestRunsWithTheModalityNonModal() {
        val modality = PlatformTestUtil.waitForFuture(inRequest { ModalityState.defaultModalityState() }, TIMEOUT_MS)

        assertEquals(ModalityState.nonModal(), modality)
    }

    fun testDocumentCommitOfARequestIsWriteSafe() {
        val result = PlatformTestUtil.waitForFuture(
            inRequest { SyncFilesTool().execute(project, buildJsonObject {}) },
            TIMEOUT_MS
        )

        assertFalse("ide_sync_files failed: ${result.content}", result.isError)
    }

    fun testRestartRequestWaitsWhileAModalDialogIsOpenAndIsWriteSafe() {
        val writingAllowed = AtomicReference<Boolean?>()
        val dialog = Any()
        LaterInvocator.enterModal(dialog)
        try {
            ThreadingUtils.runOnEdt { writingAllowed.set(TransactionGuard.getInstance().isWritingAllowed) }
            PlatformTestUtil.dispatchAllInvocationEventsInIdeEventQueue()
            assertNull("The restart request ran while a modal dialog was open", writingAllowed.get())
        } finally {
            LaterInvocator.leaveModal(dialog)
        }
        PlatformTestUtil.dispatchAllInvocationEventsInIdeEventQueue()

        assertEquals("The restart request did not run in a write-safe context", true, writingAllowed.get())
    }

    /** The UI step of ide_diagnostics makes no model change, so it runs while a modal dialog is open. */
    fun testDiagnosticsUiStepDoesNotWaitWhileAModalDialogIsOpen() {
        val psiFile = myFixture.configureByText("Open.java", "class Open {}")
        val service = DiagnosticsAnalysisService.getInstance(project)
        service.openFileAnalysisOverride = { emptyList() }
        service.closedFileAnalysisOverride = { emptyList() }
        val dialog = Any()
        LaterInvocator.enterModal(dialog)
        var analysis: Future<DiagnosticsAnalysisService.FileAnalysisResult>? = null
        try {
            analysis = inRequest {
                service.analyzeFile(psiFile.virtualFile, "Open.java", "all", null, null, 10)
            }
            val result = PlatformTestUtil.waitForFuture(analysis, TIMEOUT_MS)
            assertFalse("The analysis timed out", result.analysisTimedOut)
        } finally {
            LaterInvocator.leaveModal(dialog)
            service.openFileAnalysisOverride = null
            service.closedFileAnalysisOverride = null
            // A step that waited for the dialog can now end; do not leave its thread to the next test.
            analysis?.let { runCatching { PlatformTestUtil.waitForFuture(it, TIMEOUT_MS) } }
        }
    }

    /** Runs [block] on a background thread in the context that the server gives a request. */
    private fun <T> inRequest(block: suspend () -> T): Future<T> =
        ApplicationManager.getApplication().executeOnPooledThread(Callable {
            runBlocking { KtorMcpServer.runWithIdeModality(block) }
        })

    private companion object {
        const val TIMEOUT_MS = 10_000L
    }
}
