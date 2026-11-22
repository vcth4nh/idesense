package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.exceptions.IndexNotReadyException
import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.models.FileStructureResult
import com.github.vcth4nh.idesense.tools.models.FindUsagesResult
import com.github.vcth4nh.idesense.tools.models.ImplementationResult
import com.github.vcth4nh.idesense.tools.models.ReadFileResult
import com.github.vcth4nh.idesense.tools.navigation.FileStructureTool
import com.github.vcth4nh.idesense.tools.navigation.FindImplementationsTool
import com.github.vcth4nh.idesense.tools.navigation.FindUsagesTool
import com.github.vcth4nh.idesense.tools.navigation.ReadFileTool
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.extensions.LoadingOrder
import com.intellij.openapi.progress.ProgressManager
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
import com.intellij.util.QueryExecutor
import java.nio.file.Files
import java.nio.file.Path
import java.util.EnumSet
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Platform tests for #195 and #267: a tool checks for dumb mode one time (`requireSmartMode`), and
 * the IDE can enter dumb mode before its search runs. The search of such a tool runs in a smart
 * read action, so it waits for the index and gives the full result.
 *
 * The race tests stop the first search inside its read action, start dumb mode, and keep dumb
 * mode on for [DUMB_WINDOW_MS]. The write action that starts dumb mode interrupts the read action,
 * and the platform runs the read action again. A plain read action runs it again at once, in dumb
 * mode; a smart read action waits for the end of dumb mode.
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

        val result = callAcrossDumbModeStart(trigger) { FindImplementationsTool().execute(project, args) }

        assertEquals("The implementations of a search that met dumb mode", baseline.sorted(), implementations(result).sorted())
    }

    fun testFindUsagesGivesTheFullResultWhenDumbModeStartsAfterTheCheck() {
        val args = positionOf(SHAPE_FILE, "area")
        val baseline = json.decodeFromString<FindUsagesResult>(text(runTool(FindUsagesTool(), args)))
        assertEquals(2, baseline.usages.size)
        assertNull(baseline.warnings)

        val trigger = DumbModeTrigger("race.Shape#area")
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

        val result = callAcrossDumbModeStart(trigger) { FindUsagesTool().execute(project, args) }
        val usages = json.decodeFromString<FindUsagesResult>(text(result))

        assertEquals(
            "The usages of a search that met dumb mode",
            baseline.usages.map { "${it.file}:${it.line}:${it.column}" }.sorted(),
            usages.usages.map { "${it.file}:${it.line}:${it.column}" }.sorted()
        )
        assertNull("A search that waited for the index has no warning", usages.warnings)
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

    // A tool with no dumb mode check reads in a plain read action: it answers in dumb mode.
    fun testFileStructureAnswersInDumbMode() {
        inDumbMode {
            val result = runBlocking {
                withTimeout(CALL_TIMEOUT_MS) {
                    FileStructureTool().execute(project, buildJsonObject { put("file", SHAPE_FILE) })
                }
            }
            val structure = json.decodeFromString<FileStructureResult>(text(result))
            assertTrue(structure.structure, structure.structure.contains("Shape"))
        }
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

    /**
     * Runs [call] on a pooled thread. When the search reaches [trigger], starts dumb mode, keeps it
     * on for [DUMB_WINDOW_MS], ends it, and returns the result of the call.
     *
     * A search that runs in dumb mode can log an error (the Java functional expression search does).
     * The IDE writes such an error to its log and goes on. The test does the same, so that the
     * result of the call shows the effect.
     */
    private fun callAcrossDumbModeStart(trigger: DumbModeTrigger, call: suspend () -> ToolCallResult): ToolCallResult {
        var result: ToolCallResult? = null
        LoggedErrorProcessor.executeWith<Throwable>(object : LoggedErrorProcessor() {
            override fun processError(category: String, message: String, details: Array<out String>, t: Throwable?) =
                EnumSet.of(Action.LOG)
        }) {
            val future = ApplicationManager.getApplication().executeOnPooledThread<ToolCallResult> { runBlocking { call() } }
            PlatformTestUtil.waitWithEventsDispatching("The search did not reach the trigger", { trigger.reached.count == 0L }, 30)
            val token = DumbModeTestUtils.startEternalDumbModeTask(project)
            try {
                val end = System.currentTimeMillis() + DUMB_WINDOW_MS
                while (!future.isDone && System.currentTimeMillis() < end) {
                    PlatformTestUtil.dispatchAllInvocationEventsInIdeEventQueue()
                    Thread.sleep(5)
                }
            } finally {
                DumbModeTestUtils.endEternalDumbModeTaskAndWaitForSmartMode(project, token)
            }
            PlatformTestUtil.waitWithEventsDispatching("The call did not end after dumb mode", { future.isDone }, 60)
            result = future.get()
        }
        return result!!
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

    private fun implementations(result: ToolCallResult): List<String> =
        json.decodeFromString<ImplementationResult>(text(result)).implementations.map { it.qualifiedName ?: it.name }

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
        const val DUMB_WINDOW_MS = 1500L
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
        )
    }
}
