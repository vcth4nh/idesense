package com.github.vcth4nh.idesense.tools.intelligence

import com.github.vcth4nh.idesense.constants.UsageMatch
import com.github.vcth4nh.idesense.tools.intelligence.ExplainSymbolTool.Companion.MAX_TOP_USAGES
import com.github.vcth4nh.idesense.tools.intelligence.ExplainSymbolTool.Companion.MAX_USAGE_COUNT
import com.github.vcth4nh.idesense.tools.models.UsageLocation
import junit.framework.TestCase
import java.util.concurrent.CountDownLatch
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

// #215: the usage part of ide_explain_symbol. The search can call the processor from more than
// one thread, and it can deliver more usages after the processor returned false.
class ExplainSymbolUsageCollectorUnitTest : TestCase() {

    private fun ExplainSymbolTool.UsageCollector.deliver(line: Int, usageType: String, match: String? = null, file: String = "a.go") =
        add("$file:$line:1", match, { usageType }) { type -> UsageLocation(file, line, 1, "preview", type, emptyList(), match) }

    private fun ExplainSymbolTool.UsageCollector.top() = topUsages.map { "${it.file}:${it.line}:${it.usageType}:${it.match}" }

    fun testTheCountStaysAtTheLimitWhenTheSearchDeliversMoreUsages() {
        val collector = ExplainSymbolTool.UsageCollector()

        // The test ignores isFull: the hits that other threads have in progress still arrive.
        repeat(MAX_USAGE_COUNT + 50) { collector.deliver(it + 1, "REFERENCE") }

        assertEquals(MAX_USAGE_COUNT, collector.usageCount)
        assertTrue(collector.isFull)
    }

    fun testAUsageAfterTheLimitIsNoTopUsage() {
        val collector = ExplainSymbolTool.UsageCollector()
        repeat(MAX_USAGE_COUNT) { collector.deliver(it + 1, "COMMENT") }

        collector.deliver(1, "METHOD_CALL", file = "b.go")

        assertEquals(List(MAX_TOP_USAGES) { "COMMENT" }, collector.topUsages.map { it.usageType })
    }

    fun testOneThreadCountsEachPositionOneTime() {
        val collector = ExplainSymbolTool.UsageCollector()

        repeat(2) { repeat(30) { collector.deliver(it + 1, "REFERENCE") } }

        assertEquals(30, collector.usageCount)
        assertFalse(collector.isFull)
    }

    fun testOneThreadIsTruncatedAtTheLimitAndNotBelowIt() {
        val below = ExplainSymbolTool.UsageCollector()
        repeat(MAX_USAGE_COUNT - 1) { below.deliver(it + 1, "REFERENCE") }
        val atLimit = ExplainSymbolTool.UsageCollector()
        repeat(MAX_USAGE_COUNT) { atLimit.deliver(it + 1, "REFERENCE") }

        assertEquals(MAX_USAGE_COUNT - 1, below.usageCount)
        assertFalse(below.isFull)
        assertEquals(MAX_USAGE_COUNT, atLimit.usageCount)
        assertTrue(atLimit.isFull)
    }

    fun testOneThreadSelectsTheTopUsagesByClassThenByArrival() {
        val collector = ExplainSymbolTool.UsageCollector()
        collector.deliver(1, "COMMENT")
        collector.deliver(2, "METHOD_CALL", UsageMatch.DYNAMIC)
        collector.deliver(3, "COMMENT")
        collector.deliver(4, "METHOD_CALL", UsageMatch.BASE)
        collector.deliver(5, "METHOD_CALL")
        collector.deliver(6, "METHOD_CALL", UsageMatch.DYNAMIC)
        collector.deliver(7, "METHOD_CALL", UsageMatch.OVERRIDE)
        collector.deliver(8, "REFERENCE")
        collector.deliver(9, "COMMENT")

        assertEquals(
            listOf(
                "a.go:5:METHOD_CALL:null",
                "a.go:8:REFERENCE:null",
                "a.go:4:METHOD_CALL:BASE",
                "a.go:7:METHOD_CALL:OVERRIDE",
                "a.go:2:METHOD_CALL:DYNAMIC",
            ),
            collector.top(),
        )
    }

    fun testOneThreadKeepsTheFirstFiveSureUsages() {
        val collector = ExplainSymbolTool.UsageCollector()
        collector.deliver(1, "COMMENT")
        (2..8).forEach { collector.deliver(it, "METHOD_CALL") }
        collector.deliver(9, "METHOD_CALL", UsageMatch.BASE)

        assertEquals((2..6).map { "a.go:$it:METHOD_CALL:null" }, collector.top())
        assertEquals(9, collector.usageCount)
    }

    // The base pass of the Go search gives the usages of the base declaration after the usages of the direct pass.
    fun testTheFirstHitAtAPositionKeepsItsMatch() {
        val collector = ExplainSymbolTool.UsageCollector()
        collector.deliver(1, "METHOD_CALL")
        collector.deliver(1, "METHOD_CALL", UsageMatch.BASE)

        assertEquals(listOf("a.go:1:METHOD_CALL:null"), collector.top())
        assertEquals(1, collector.usageCount)
    }

    fun testManyThreadsCountEachUsageOneTime() {
        val pool = Executors.newFixedThreadPool(THREADS)
        try {
            repeat(ROUNDS) { round ->
                // 100 positions that each thread delivers, and 10 positions of each thread: 180 usages.
                val below = deliverConcurrently(pool, ownPositions = 10)
                assertEquals("round $round, below the limit", 100 + THREADS * 10, below.usageCount)
                assertFalse("round $round, below the limit", below.isFull)
                assertTopUsages("round $round, below the limit", below)

                // 100 positions that each thread delivers, and 100 positions of each thread: 900 usages.
                val above = deliverConcurrently(pool, ownPositions = 100)
                assertEquals("round $round, above the limit", MAX_USAGE_COUNT, above.usageCount)
                assertTrue("round $round, above the limit", above.isFull)
                assertTopUsages("round $round, above the limit", above)
            }
        } finally {
            pool.shutdownNow()
        }
    }

    /**
     * Each thread delivers the 100 positions that all threads deliver, in the same order, and
     * [ownPositions] (at most 100) positions of its own between them. A thread stops when the
     * collector is full, as the search stops when the processor returns false. Each third line is
     * a COMMENT usage.
     */
    private fun deliverConcurrently(pool: ExecutorService, ownPositions: Int): ExplainSymbolTool.UsageCollector {
        val collector = ExplainSymbolTool.UsageCollector()
        val start = CountDownLatch(1)
        val tasks = (0 until THREADS).map { thread ->
            pool.submit(Runnable {
                start.await()
                val positions = (1..100).flatMap { line ->
                    listOfNotNull("shared.go" to line, if (line <= ownPositions) "t$thread.go" to line else null)
                }
                for ((file, line) in positions) {
                    if (collector.isFull) break
                    collector.deliver(line, if (line % 3 == 0) "COMMENT" else "REFERENCE", file = file)
                }
            })
        }
        start.countDown()
        tasks.forEach { it.get(30, TimeUnit.SECONDS) }
        return collector
    }

    private fun assertTopUsages(message: String, collector: ExplainSymbolTool.UsageCollector) {
        val top = collector.topUsages
        assertEquals(message, MAX_TOP_USAGES, top.size)
        assertEquals(message, top.size, top.map { "${it.file}:${it.line}" }.distinct().size)
        assertTrue(message, top.all { it.usageType == "REFERENCE" })
    }

    private companion object {
        const val THREADS = 8
        const val ROUNDS = 200
    }
}
