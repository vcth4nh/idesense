package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.constants.ErrorMessages
import com.github.vcth4nh.idesense.exceptions.IndexNotReadyException
import com.github.vcth4nh.idesense.exceptions.SymbolNotFoundException
import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.models.CallElement
import com.github.vcth4nh.idesense.tools.models.CallHierarchyResult
import com.github.vcth4nh.idesense.tools.models.FileStructureResult
import com.github.vcth4nh.idesense.tools.models.FindUsagesResult
import com.github.vcth4nh.idesense.tools.models.ImplementationResult
import com.github.vcth4nh.idesense.tools.models.ReadFileResult
import com.github.vcth4nh.idesense.tools.navigation.CallHierarchyTool
import com.github.vcth4nh.idesense.tools.navigation.FileStructureTool
import com.github.vcth4nh.idesense.tools.navigation.FindImplementationsTool
import com.github.vcth4nh.idesense.tools.navigation.FindUsagesTool
import com.github.vcth4nh.idesense.tools.navigation.ReadFileTool
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.extensions.LoadingOrder
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.openapi.project.SmartModeScheduler
import com.intellij.openapi.roots.ContentIterator
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiMethod
import com.intellij.psi.search.searches.DefinitionsScopedSearch
import com.intellij.psi.search.searches.MethodReferencesSearch
import com.intellij.psi.search.searches.ReferencesSearch
import com.intellij.testFramework.DumbModeTestUtils
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.LoggedErrorProcessor
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.testFramework.PsiTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.intellij.openapi.vfs.VirtualFileFilter
import com.intellij.util.QueryExecutor
import com.intellij.util.indexing.UnindexedFilesScanner
import com.intellij.util.indexing.roots.IndexableFilesIterator
import com.intellij.util.indexing.roots.kind.IndexableSetOrigin
import java.nio.file.Files
import java.nio.file.Path
import java.util.EnumSet
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Platform tests for #195 and #267: a tool checks for dumb mode one time (`requireSmartMode`), and
 * the IDE can enter dumb mode or scan files before its search runs. The search of such a tool
 * waits for smart mode (no dumb mode and no file scan), up to a limit, and gives the full result.
 *
 * The race tests stop the first search inside its read action, start dumb mode, and keep dumb
 * mode on for [DUMB_WINDOW_MS]. The write action that starts dumb mode interrupts the read action,
 * and the platform runs the read action again. A plain read action runs again at once, in dumb
 * mode. The start of a file scan also takes a write action, so it interrupts a run too: see
 * [testCallWaitsForAFileScanThatStartsDuringTheSearch].
 */
class SmartReadActionTest : BasePlatformTestCase() {

    private val json = Json { ignoreUnknownKeys = true }
    private lateinit var sourceRoot: VirtualFile

    override fun setUp() {
        super.setUp()
        val root = Files.createDirectories(Path.of(project.basePath!!).resolve(ROOT))
        val files = SOURCES.map { (name, text) ->
            root.resolve("race/$name").also {
                Files.createDirectories(it.parent)
                Files.writeString(it, text)
            }
        }
        sourceRoot = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(root)!!
        files.forEach { LocalFileSystem.getInstance().refreshAndFindFileByNioFile(it)!! }
        PsiTestUtil.addSourceRoot(module, sourceRoot)
        IndexingTestUtil.waitUntilIndexesAreReady(project)
    }

    override fun tearDown() {
        try {
            PsiTestUtil.removeSourceRoot(module, sourceRoot)
        } catch (e: Throwable) {
            addSuppressedException(e)
        } finally {
            super.tearDown()
        }
    }

    fun testFindImplementationsGivesTheFullResultWhenDumbModeStartsAfterTheCheck() {
        val args = positionOf(SHAPE_FILE, "area")
        val baseline = implementations(runTool(FindImplementationsTool(), args))
        assertEquals(setOf("race.Circle#area", "race.Square#area"), baseline.toSet())

        val trigger = DumbModeTrigger("race.Shape#area")
        DefinitionsScopedSearch.EP_NAME.point.registerExtension(
            QueryExecutor { params, _ -> trigger.onSearch(params.element); true },
            LoadingOrder.FIRST,
            testRootDisposable
        )

        val race = callAcrossDumbModeStart(trigger) { FindImplementationsTool().execute(project, args) }

        assertEquals("The implementations of a search that met dumb mode", baseline.sorted(), implementations(race.result).sorted())
        assertEquals("Errors logged during the call", emptyList<String>(), race.errors)
    }

    fun testFindUsagesGivesTheFullResultWhenDumbModeStartsAfterTheCheck() {
        val args = positionOf(SHAPE_FILE, "area")
        val baseline = usages(runTool(FindUsagesTool(), args))
        assertEquals(2, baseline.usages.size)
        assertNull(baseline.warnings)

        val trigger = DumbModeTrigger("race.Shape#area")
        holdReferenceSearches(trigger)

        val race = callAcrossDumbModeStart(trigger) { FindUsagesTool().execute(project, args) }
        val result = usages(race.result)

        assertEquals("The usages of a search that met dumb mode", baseline.keys().sorted(), result.keys().sorted())
        assertNull("A search that waited for the index has no warning", result.warnings)
        assertEquals("Errors logged during the call", emptyList<String>(), race.errors)
    }

    // The hierarchy walker takes an empty child list when the children of a node throw, and a
    // search in dumb mode throws the platform IndexNotReadyException: 0 callers with no signal.
    fun testCallHierarchyGivesTheFullTreeWhenDumbModeStartsAfterTheCheck() {
        val args = buildJsonObject {
            positionOf(SHAPE_FILE, "area").forEach { (key, value) -> put(key, value) }
            put("direction", "callers")
        }
        val baseline = calls(runTool(CallHierarchyTool(), args))
        assertTrue("Painter#total calls Shape#area: $baseline", baseline.any { it.contains("total") })

        val trigger = DumbModeTrigger("race.Shape#area")
        holdReferenceSearches(trigger)

        val race = callAcrossDumbModeStart(trigger) { CallHierarchyTool().execute(project, args) }

        assertEquals("The callers of a call that met dumb mode", baseline, calls(race.result))
        assertEquals("Errors logged during the call", emptyList<String>(), race.errors)
    }

    // A call with a cursor does not check for dumb mode. When its page needs more results than the
    // first call kept, it searches again (the search extender of the cursor), and that search waits
    // for the index too.
    fun testFindUsagesCursorGivesTheFullPageWhenDumbModeStartsBeforeTheSearchAgain() {
        val baselineFirst = usages(runTool(FindUsagesTool(), firstTickPage()))
        val baselineNext = usages(runTool(FindUsagesTool(), nextTickPage(baselineFirst.nextCursor!!)))
        assertEquals(FIRST_PAGE, baselineFirst.usages.size)
        assertEquals(TICKS - FIRST_PAGE, baselineNext.usages.size)
        assertEquals(TICKS, (baselineFirst.keys() + baselineNext.keys()).toSet().size)

        val raceFirst = usages(runTool(FindUsagesTool(), firstTickPage()))
        val trigger = DumbModeTrigger("race.Counter#tick")
        holdReferenceSearches(trigger)

        val race = callAcrossDumbModeStart(trigger) { FindUsagesTool().execute(project, nextTickPage(raceFirst.nextCursor!!)) }
        val next = usages(race.result)

        assertEquals("The usages of a cursor page that met dumb mode", TICKS - FIRST_PAGE, next.usages.size)
        assertEquals(
            "The usages of the two pages",
            (baselineFirst.keys() + baselineNext.keys()).sorted(),
            (raceFirst.keys() + next.keys()).sorted()
        )
        assertEquals("Errors logged during the call", emptyList<String>(), race.errors)
    }

    // The wait for the index has a limit. After it, the call gives index_not_ready.
    fun testCallGivesIndexNotReadyAfterTheWaitLimit() {
        val args = positionOf(SHAPE_FILE, "area")
        val trigger = DumbModeTrigger("race.Shape#area")
        DefinitionsScopedSearch.EP_NAME.point.registerExtension(
            QueryExecutor { params, _ -> trigger.onSearch(params.element); true },
            LoadingOrder.FIRST,
            testRootDisposable
        )

        val race = withIndexWaitLimit {
            callAcrossDumbModeStart(trigger, LONG_DUMB_WINDOW_MS) { FindImplementationsTool().execute(project, args) }
        }

        assertWaitLimit(race)
    }

    // A call with a cursor has the same limit for a dumb mode that starts after its first search began.
    fun testCursorCallGivesIndexNotReadyAfterTheWaitLimit() {
        val first = usages(runTool(FindUsagesTool(), firstTickPage()))
        val trigger = DumbModeTrigger("race.Counter#tick")
        holdReferenceSearches(trigger)

        val race = withIndexWaitLimit {
            callAcrossDumbModeStart(trigger, LONG_DUMB_WINDOW_MS) { FindUsagesTool().execute(project, nextTickPage(first.nextCursor!!)) }
        }

        assertWaitLimit(race)
    }

    // A call with a cursor has no dumb mode check at its start. When it must search again in dumb
    // mode, its first search makes the check and gives index_not_ready at once, with no wait.
    fun testCursorCallThatMustSearchAgainInDumbModeGetsIndexNotReadyAtOnce() {
        val first = usages(runTool(FindUsagesTool(), firstTickPage()))
        var error: Throwable? = null
        var elapsedMs = 0L
        inDumbMode {
            val start = System.currentTimeMillis()
            error = runCatching {
                runBlocking { withTimeout(CALL_TIMEOUT_MS) { FindUsagesTool().execute(project, nextTickPage(first.nextCursor!!)) } }
            }.exceptionOrNull()
            elapsedMs = System.currentTimeMillis() - start
        }

        assertTrue("Expected index_not_ready, got $error", error is IndexNotReadyException)
        assertEquals(ErrorMessages.INDEX_NOT_READY, error!!.message)
        assertTrue("The call waited $elapsedMs ms", elapsedMs < AT_ONCE_MS)
    }

    // A cursor page that the first call kept needs no search: it answers in dumb mode.
    fun testCursorPageFromTheCacheAnswersInDumbMode() {
        val first = usages(runTool(FindUsagesTool(), firstTickPage()))
        var next: FindUsagesResult? = null
        inDumbMode {
            next = usages(runTool(FindUsagesTool(), buildJsonObject {
                put("cursor", first.nextCursor!!)
                put("pageSize", FIRST_PAGE)
            }))
        }

        assertEquals(FIRST_PAGE, next!!.usages.size)
    }

    // An exception of the action that is no cancellation comes to the caller as with a plain read action.
    fun testExceptionOfTheActionComesToTheCaller() {
        for (thrown in listOf(IllegalStateException("of the test"), SymbolNotFoundException("of the test"))) {
            val error = runCatching { runTool(ThrowingTool(thrown), buildJsonObject {}) }.exceptionOrNull()
            assertEquals("The exception of the caller", thrown.javaClass, error?.javaClass)
            assertEquals(thrown.message, error!!.message)
        }
    }

    /** Checks for dumb mode, then throws [error] in a read action. */
    private class ThrowingTool(private val error: Throwable) : AbstractMcpTool() {
        override val name = "test_throwing_tool"
        override val description = "Throws in a read action."
        override val inputSchema = buildJsonObject {}
        override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
            requireSmartMode(project)
            return suspendingReadAction { throw error }
        }
    }

    // A file scan that starts during a run of the search, queued from a thread with no write-intent
    // lock: the scanner executor sets its running state in a write action, which interrupts the run.
    // The smart read action then starts the search again only after the scan.
    fun testCallWaitsForAFileScanThatStartsDuringTheSearch() {
        val args = positionOf(FN_FILE, "apply")
        val baseline = implementations(runTool(FindImplementationsTool(), args))
        assertEquals(2, baseline.size)

        val scan = HeldScan()
        val reached = CountDownLatch(1)
        val armed = AtomicBoolean(true)
        val interrupted = AtomicBoolean(false)
        val holdTimedOut = AtomicBoolean(false)
        DefinitionsScopedSearch.EP_NAME.point.registerExtension(
            QueryExecutor { params, _ ->
                val element = params.element
                if (element is PsiMethod && element.containingClass?.qualifiedName == "race.Fn" && armed.compareAndSet(true, false)) {
                    reached.countDown()
                    // Hold the run until the scan starts, at most HOLD_TIMEOUT_MS. A write action interrupts the run here.
                    val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(HOLD_TIMEOUT_MS)
                    try {
                        while (scan.started.count > 0L) {
                            if (System.nanoTime() >= deadline) {
                                holdTimedOut.set(true)
                                break
                            }
                            ProgressManager.checkCanceled()
                            Thread.sleep(5)
                        }
                    } catch (e: Throwable) {
                        interrupted.set(true)
                        throw e
                    }
                }
                true
            },
            LoadingOrder.FIRST,
            testRootDisposable
        )

        val errors = ConcurrentLinkedQueue<String>()
        var outcome: Result<ToolCallResult>? = null
        var endedDuringTheScan = false
        try {
            LoggedErrorProcessor.executeWith<Throwable>(collectInto(errors)) {
                val call = ApplicationManager.getApplication().executeOnPooledThread<Result<ToolCallResult>> {
                    runCatching { runBlocking { FindImplementationsTool().execute(project, args) } }
                }
                PlatformTestUtil.waitWithEventsDispatching("The search did not reach the hook", { reached.count == 0L }, 30)
                // A pooled thread has no write-intent lock: submitTask itself takes no write action.
                ApplicationManager.getApplication().executeOnPooledThread {
                    UnindexedFilesScanner(project, listOf(scan), "a held scan of the test").queue()
                }
                PlatformTestUtil.waitWithEventsDispatching("The scan did not start", { scan.started.count == 0L }, 30)
                endedDuringTheScan = try {
                    call.get(SCAN_HOLD_MS, TimeUnit.MILLISECONDS)
                    true
                } catch (_: TimeoutException) {
                    false
                }
                scan.release.countDown()
                PlatformTestUtil.waitWithEventsDispatching("The call did not end", { call.isDone }, 30)
                outcome = call.get()
            }
        } finally {
            endHeldScan(scan)
        }

        assertFalse("The hold of the search ended after $HOLD_TIMEOUT_MS ms with no scan start", holdTimedOut.get())
        assertEquals("The implementations of a search that met a scan start", baseline.sorted(), implementations(outcome!!.getOrThrow()).sorted())
        assertEquals("Errors logged during the call", emptyList<String>(), errors.toList())
        assertFalse("The call ended during the file scan", endedDuringTheScan)
        assertTrue("The start of the scan interrupted the run of the search", interrupted.get())
    }

    // The call also waits while the IDE scans the files with no dumb mode. The Java functional
    // expression search of the platform needs the inSmartMode constraint, which is false during
    // the scan: inside a read action that search throws, and the query logs the error and goes on
    // without the lambdas and method references.
    fun testCallWaitsForAFileScanAndGivesTheFullResult() {
        val args = positionOf(FN_FILE, "apply")
        val baseline = implementations(runTool(FindImplementationsTool(), args))
        assertEquals("A lambda and a method reference implement Fn#apply: $baseline", 2, baseline.size)

        val errors = ConcurrentLinkedQueue<String>()
        var outcome: Result<ToolCallResult>? = null
        var endedDuringTheScan = false
        val scan = startHeldScan()
        try {
            LoggedErrorProcessor.executeWith<Throwable>(collectInto(errors)) {
                val call = ApplicationManager.getApplication().executeOnPooledThread<Result<ToolCallResult>> {
                    runCatching { runBlocking { FindImplementationsTool().execute(project, args) } }
                }
                endedDuringTheScan = try {
                    call.get(SCAN_HOLD_MS, TimeUnit.MILLISECONDS)
                    true
                } catch (_: TimeoutException) {
                    false
                }
                scan.release.countDown()
                PlatformTestUtil.waitWithEventsDispatching("The call did not end after the scan", { call.isDone }, 30)
                outcome = call.get()
            }
        } finally {
            endHeldScan(scan)
        }

        assertEquals("The implementations of a call that met a file scan", baseline.sorted(), implementations(outcome!!.getOrThrow()).sorted())
        assertEquals("Errors logged during the call", emptyList<String>(), errors.toList())
        assertFalse("The call ended during the file scan", endedDuringTheScan)
    }

    // The limit covers the wait for a file scan too, and the error names the scan: during a file
    // scan ide_index_status shows isDumbMode: false.
    fun testCallGivesIndexNotReadyWhenAFileScanOutlastsTheWaitLimit() {
        val args = positionOf(SHAPE_FILE, "area")
        var outcome: Result<ToolCallResult>? = null
        var scanHeld = false
        val scan = startHeldScan()
        try {
            withIndexWaitLimit {
                val call = ApplicationManager.getApplication().executeOnPooledThread<Result<ToolCallResult>> {
                    runCatching { runBlocking { FindImplementationsTool().execute(project, args) } }
                }
                outcome = call.get(CALL_TIMEOUT_MS, TimeUnit.MILLISECONDS)
                scanHeld = scanMode() == SmartModeScheduler.SCANNING
            }
        } finally {
            endHeldScan(scan)
        }

        val error = outcome!!.exceptionOrNull()
        assertTrue("Expected index_not_ready, got $outcome", error is IndexNotReadyException)
        assertTrue("The error names the file scan: ${error!!.message}", error.message!!.contains("file scan"))
        assertTrue("The scan held until the end of the call", scanHeld)
    }

    // A cancel of the call from outside ends the wait: the call gets the cancellation, not index_not_ready.
    fun testCancelOfACallThatWaitsForSmartModeEndsTheCall() {
        val args = positionOf(SHAPE_FILE, "area")
        // A first call loads the classes, so that a call that does not wait ends before the cancel.
        assertEquals(2, implementations(runTool(FindImplementationsTool(), args)).size)
        var outcome: Result<ToolCallResult>? = null
        val scan = startHeldScan()
        try {
            val call = ApplicationManager.getApplication().executeOnPooledThread<Result<ToolCallResult>> {
                runCatching { runBlocking { withTimeout(CANCEL_AFTER_MS) { FindImplementationsTool().execute(project, args) } } }
            }
            outcome = call.get(CALL_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        } finally {
            endHeldScan(scan)
        }

        assertTrue("Expected the cancellation, got $outcome", outcome!!.exceptionOrNull() is TimeoutCancellationException)
    }

    private fun scanMode(): Int = project.getService(SmartModeScheduler::class.java).getCurrentMode()

    /** Starts a [HeldScan]: the IDE scans files and is not in dumb mode until [endHeldScan]. */
    private fun startHeldScan(): HeldScan {
        val scan = HeldScan()
        UnindexedFilesScanner(project, listOf(scan), "a held scan of the test").queue()
        PlatformTestUtil.waitWithEventsDispatching("The scan did not start", { scan.started.count == 0L }, 30)
        assertEquals(SmartModeScheduler.SCANNING, scanMode())
        assertFalse(DumbService.isDumb(project))
        return scan
    }

    private fun endHeldScan(scan: HeldScan) {
        scan.release.countDown()
        IndexingTestUtil.waitUntilIndexesAreReady(project)
    }

    /** A scan of no files that holds the scanner until [release], at most [HOLD_TIMEOUT_MS]. */
    private class HeldScan : IndexableFilesIterator {
        val started = CountDownLatch(1)
        val release = CountDownLatch(1)

        override fun getDebugName() = "held scan"
        override fun getIndexingProgressText() = "held scan"
        override fun getRootsScanningProgressText() = "held scan"
        override fun getOrigin() = object : IndexableSetOrigin {}
        override fun getRootUrls(project: Project) = emptySet<String>()

        override fun iterateFiles(project: Project, fileIterator: ContentIterator, fileFilter: VirtualFileFilter): Boolean {
            started.countDown()
            release.await(HOLD_TIMEOUT_MS, TimeUnit.MILLISECONDS)
            return true
        }
    }

    // requireSmartMode stays: a call that starts in dumb mode gets index_not_ready at once.
    fun testCallThatStartsInDumbModeGetsIndexNotReady() {
        val args = positionOf(SHAPE_FILE, "area")
        inDumbMode {
            val error = runCatching {
                runBlocking { withTimeout(CALL_TIMEOUT_MS) { FindImplementationsTool().execute(project, args) } }
            }.exceptionOrNull()
            assertTrue("Expected index_not_ready, got $error", error is IndexNotReadyException)
        }
    }

    // ide_file_structure checks for dumb mode (#174). In dumb mode the Java structure view gives
    // an outline with no types and no initializers, and the Rust structure view throws.
    fun testFileStructureGivesIndexNotReadyInDumbMode() {
        val args = buildJsonObject { put("file", SHAPE_FILE) }
        var error: Throwable? = null
        DumbModeTestUtils.runInDumbModeSynchronously(project) {
            error = runCatching {
                runBlocking { withTimeout(CALL_TIMEOUT_MS) { FileStructureTool().execute(project, args) } }
            }.exceptionOrNull()
        }

        assertTrue("Expected index_not_ready, got $error", error is IndexNotReadyException)
        assertEquals(ErrorMessages.INDEX_NOT_READY, error!!.message)
        val structure = json.decodeFromString<FileStructureResult>(text(runTool(FileStructureTool(), args))).structure
        assertTrue("The outline in smart mode has the types: $structure", structure.contains("area(): double"))
    }

    // ide_read_file checks for dumb mode only for a class name: a read by path answers in dumb mode.
    fun testReadFileByPathAnswersInDumbMode() {
        inDumbMode {
            val result = runBlocking {
                withTimeout(CALL_TIMEOUT_MS) {
                    ReadFileTool().execute(project, buildJsonObject { put("file", SHAPE_FILE) })
                }
            }
            val content = json.decodeFromString<ReadFileResult>(text(result))
            assertTrue(content.content, content.content.contains("abstract class Shape"))
        }
    }

    /**
     * Holds the first search of [target] (`race.Shape` or `race.Shape#area`) inside its read action
     * until the write action that starts dumb mode interrupts it.
     */
    private class DumbModeTrigger(private val target: String) {
        val reached = CountDownLatch(1)
        private val armed = AtomicBoolean(true)

        fun onSearch(element: PsiElement) {
            val name = when (element) {
                is PsiMethod -> "${element.containingClass?.qualifiedName}#${element.name}"
                is PsiClass -> element.qualifiedName
                else -> null
            }
            if (name != target || !armed.compareAndSet(true, false)) return
            reached.countDown()
            val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(HOLD_TIMEOUT_MS)
            while (System.nanoTime() < deadline) {
                ProgressManager.checkCanceled()
                Thread.sleep(5)
            }
        }
    }

    /** The reference search of a Java method goes to [MethodReferencesSearch]; other elements to [ReferencesSearch]. */
    private fun holdReferenceSearches(trigger: DumbModeTrigger) {
        ReferencesSearch.EP_NAME.point.registerExtension(
            QueryExecutor { params, _ -> trigger.onSearch(params.elementToSearch); true },
            LoadingOrder.FIRST,
            testRootDisposable
        )
        MethodReferencesSearch.EP_NAME.point.registerExtension(
            QueryExecutor { params, _ -> trigger.onSearch(params.method); true },
            LoadingOrder.FIRST,
            testRootDisposable
        )
    }

    /**
     * The outcome of a call across a dumb mode start, and the errors that the IDE logged meanwhile.
     * [endedInDumbModeAfterMs] is the time from the start of dumb mode to the end of the call, or
     * null when the call ended after dumb mode.
     */
    private class RaceCall(val outcome: Result<ToolCallResult>, val errors: List<String>, val endedInDumbModeAfterMs: Long?) {
        val result: ToolCallResult get() = outcome.getOrThrow()
    }

    /**
     * Runs [call] on a pooled thread. When the search reaches [trigger], starts dumb mode, keeps it
     * on for [dumbWindowMs] or until the call ends, ends it, and returns the outcome of the call.
     *
     * A search that runs in dumb mode can log an error (the Java functional expression search does).
     * The IDE writes such an error to its log and goes on. The test keeps each logged error in
     * [RaceCall.errors], so that the result of the call shows the effect first. A test asserts the
     * errors after the result.
     */
    private fun callAcrossDumbModeStart(
        trigger: DumbModeTrigger,
        dumbWindowMs: Long = DUMB_WINDOW_MS,
        call: suspend () -> ToolCallResult
    ): RaceCall {
        var outcome: Result<ToolCallResult>? = null
        var endedInDumbModeAfterMs: Long? = null
        val errors = ConcurrentLinkedQueue<String>()
        LoggedErrorProcessor.executeWith<Throwable>(collectInto(errors)) {
            val future = ApplicationManager.getApplication().executeOnPooledThread<Result<ToolCallResult>> {
                runCatching { runBlocking { call() } }
            }
            PlatformTestUtil.waitWithEventsDispatching("The search did not reach the trigger", { trigger.reached.count == 0L }, 30)
            // Before the start of dumb mode: the wait of the call can start in the write action that starts it.
            val start = System.currentTimeMillis()
            val token = DumbModeTestUtils.startEternalDumbModeTask(project)
            try {
                while (!future.isDone && System.currentTimeMillis() < start + dumbWindowMs) {
                    PlatformTestUtil.dispatchAllInvocationEventsInIdeEventQueue()
                    Thread.sleep(5)
                }
                if (future.isDone) endedInDumbModeAfterMs = System.currentTimeMillis() - start
            } finally {
                DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, token)
            }
            PlatformTestUtil.waitWithEventsDispatching("The call did not end after dumb mode", { future.isDone }, 60)
            outcome = future.get()
        }
        return RaceCall(outcome!!, errors.toList(), endedInDumbModeAfterMs)
    }

    /** Keeps each error that the IDE logs, and lets the IDE write it to its log and go on. */
    private fun collectInto(errors: MutableCollection<String>) = object : LoggedErrorProcessor() {
        override fun processError(category: String, message: String, details: Array<out String>, t: Throwable?): Set<Action> {
            errors.add("$category: $message${t?.let { " ($it)" } ?: ""}")
            return EnumSet.of(Action.LOG)
        }
    }

    private fun <T> withIndexWaitLimit(block: () -> T): T {
        AbstractMcpTool.indexWaitLimitMs = TEST_WAIT_LIMIT_MS
        try {
            return block()
        } finally {
            AbstractMcpTool.indexWaitLimitMs = AbstractMcpTool.INDEX_WAIT_LIMIT_MS
        }
    }

    /**
     * The call ended with index_not_ready after the wait limit, while dumb mode was still on. The
     * clocks of the test and of the call differ a little, so the test allows a small tolerance.
     */
    private fun assertWaitLimit(race: RaceCall) {
        assertTrue("Expected index_not_ready, got ${race.outcome}", race.outcome.exceptionOrNull() is IndexNotReadyException)
        val after = race.endedInDumbModeAfterMs
        assertNotNull("The call ended only after dumb mode", after)
        assertTrue(
            "The call ended $after ms after the start of dumb mode, before the limit",
            after!! >= TEST_WAIT_LIMIT_MS - LIMIT_TOLERANCE_MS
        )
        assertEquals("Errors logged during the call", emptyList<String>(), race.errors)
    }

    /** The first call keeps 500 usages of Counter#tick (the collection limit) and gives the first 100. */
    private fun firstTickPage() = buildJsonObject {
        positionOf(COUNTER_FILE, "tick").forEach { (key, value) -> put(key, value) }
        put("pageSize", FIRST_PAGE)
    }

    /** A cursor call with a page of 500 needs the other usages, so it searches again. */
    private fun nextTickPage(cursor: String) = buildJsonObject {
        put("cursor", cursor)
        put("pageSize", 500)
    }

    private fun inDumbMode(block: () -> Unit) {
        val token = DumbModeTestUtils.startEternalDumbModeTask(project)
        try {
            block()
        } finally {
            DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, token)
        }
    }

    private fun runTool(tool: McpTool, args: JsonObject): ToolCallResult = runBlocking { tool.execute(project, args) }

    private fun text(result: ToolCallResult): String {
        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("The call must succeed: $text", result.isError)
        return text
    }

    private fun usages(result: ToolCallResult): FindUsagesResult = json.decodeFromString<FindUsagesResult>(text(result))

    private fun FindUsagesResult.keys(): List<String> = usages.map { "${it.file}:${it.line}:${it.column}" }

    private fun implementations(result: ToolCallResult): List<String> =
        json.decodeFromString<ImplementationResult>(text(result)).implementations.map { it.qualifiedName ?: it.name }

    /** The caller tree, one line for each node, with its depth. */
    private fun calls(result: ToolCallResult): List<String> {
        fun walk(nodes: List<CallElement>, depth: Int): List<String> =
            nodes.flatMap { listOf("$depth ${it.qualifiedName ?: it.name}") + walk(it.children.orEmpty(), depth + 1) }
        return walk(json.decodeFromString<CallHierarchyResult>(text(result)).calls, 1)
    }

    private fun positionOf(file: String, needle: String): JsonObject {
        val source = SOURCES.getValue(file.substringAfterLast('/'))
        val offset = source.indexOf(needle)
        val line = source.substring(0, offset).count { it == '\n' } + 1
        val column = offset - source.lastIndexOf('\n', offset - 1)
        return buildJsonObject {
            put("file", file)
            put("line", line)
            put("column", column)
        }
    }

    private companion object {
        const val ROOT = "race-src"
        const val SHAPE_FILE = "$ROOT/race/Shape.java"
        const val COUNTER_FILE = "$ROOT/race/Counter.java"
        const val FN_FILE = "$ROOT/race/Fn.java"
        const val TICKS = 520
        const val FIRST_PAGE = 100
        const val DUMB_WINDOW_MS = 1500L
        const val TEST_WAIT_LIMIT_MS = 500L
        const val LONG_DUMB_WINDOW_MS = 5000L
        const val LIMIT_TOLERANCE_MS = 50L
        const val AT_ONCE_MS = 2000L
        const val SCAN_HOLD_MS = 1500L
        const val CANCEL_AFTER_MS = 300L
        const val HOLD_TIMEOUT_MS = 30_000L
        const val CALL_TIMEOUT_MS = 10_000L

        val SOURCES = mapOf(
            "Shape.java" to """
                package race;

                public abstract class Shape {
                    public abstract double area();
                }
            """.trimIndent(),
            "Circle.java" to """
                package race;

                public class Circle extends Shape {
                    @Override
                    public double area() { return 3.0; }
                }
            """.trimIndent(),
            "Square.java" to """
                package race;

                public class Square extends Shape {
                    @Override
                    public double area() { return 4.0; }
                }
            """.trimIndent(),
            "Painter.java" to """
                package race;

                public class Painter {
                    double total(Shape a, Shape b) {
                        double sum = a.area();
                        sum += b.area();
                        return sum;
                    }
                }
            """.trimIndent(),
            "Fn.java" to """
                package race;

                @FunctionalInterface
                public interface Fn {
                    int apply(int x);
                }
            """.trimIndent(),
            "Fns.java" to """
                package race;

                public class Fns {
                    static int twice(int x) { return 2 * x; }
                    Fn lambda() { return x -> x + 1; }
                    Fn reference() { return Fns::twice; }
                }
            """.trimIndent(),
            "Counter.java" to """
                package race;

                public class Counter {
                    public void tick() { }
                }
            """.trimIndent(),
            // More usages of Counter#tick than the collection limit of the first call (500).
            "Ticks.java" to buildString {
                append("package race;\n\npublic class Ticks {\n    void run(Counter c) {\n")
                repeat(TICKS) { append("        c.tick();\n") }
                append("    }\n}\n")
            },
        )
    }
}
