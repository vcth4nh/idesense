package com.github.vcth4nh.idesense.history

import com.github.vcth4nh.idesense.settings.McpSettings
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

class CommandHistoryServiceTest : BasePlatformTestCase() {

    private lateinit var historyService: CommandHistoryService
    private var originalMaxHistorySize: Int = 100

    override fun setUp() {
        super.setUp()
        originalMaxHistorySize = McpSettings.getInstance().maxHistorySize
        historyService = CommandHistoryService.getInstance(project)
        historyService.clearHistory()
        McpSettings.getInstance().maxHistorySize = 100
    }

    override fun tearDown() {
        try {
            historyService.clearHistory()
            McpSettings.getInstance().maxHistorySize = originalMaxHistorySize
        } finally {
            super.tearDown()
        }
    }

    fun testRecordCommand() {
        val entry = CommandEntry(
            toolName = "test_tool",
            parameters = buildJsonObject {
                put("param1", "value1")
            }
        )

        historyService.recordCommand(entry)

        val history = historyService.entries
        assertEquals(1, history.size)
        assertEquals("test_tool", history[0].toolName)
        assertEquals(CommandStatus.PENDING, history[0].status)
    }

    fun testUpdateCommandStatus() {
        val entry = CommandEntry(
            toolName = "test_tool",
            parameters = buildJsonObject { }
        )

        historyService.recordCommand(entry)
        historyService.updateCommandStatus(entry.id, CommandStatus.SUCCESS, "Result", 100)

        val history = historyService.entries
        assertEquals(1, history.size)
        assertEquals(CommandStatus.SUCCESS, history[0].status)
        assertEquals("Result", history[0].result)
        assertEquals(100L, history[0].durationMs)
    }

    fun testClearHistory() {
        repeat(5) { i ->
            historyService.recordCommand(CommandEntry(
                toolName = "tool_$i",
                parameters = buildJsonObject { }
            ))
        }

        assertEquals(5, historyService.entries.size)

        historyService.clearHistory()

        assertEquals(0, historyService.entries.size)
    }

    fun testHistoryListener() {
        var commandRecorded = false
        var commandUpdated = false

        val listener = object : CommandHistoryListener {
            override fun onCommandAdded(entry: CommandEntry) {
                commandRecorded = true
            }

            override fun onCommandUpdated(entry: CommandEntry) {
                commandUpdated = true
            }

            override fun onHistoryCleared() {
            }
        }

        historyService.addListener(listener)

        val entry = CommandEntry(
            toolName = "test_tool",
            parameters = buildJsonObject { }
        )

        historyService.recordCommand(entry)

        historyService.updateCommandStatus(entry.id, CommandStatus.SUCCESS, null, 50)

        historyService.removeListener(listener)
    }

    fun testHistorySizeLimit() {
        val maxSize = 100
        repeat(maxSize + 50) { i ->
            historyService.recordCommand(CommandEntry(
                toolName = "tool_$i",
                parameters = buildJsonObject { }
            ))
        }

        val history = historyService.entries
        assertTrue("History should not exceed max size", history.size <= maxSize)
    }

    fun testConcurrentRecordCommandDoesNotCrashOrExceedLimit() {
        McpSettings.getInstance().maxHistorySize = 100

        val threadCount = 8
        val iterationsPerThread = 5000
        val startLatch = CountDownLatch(1)
        val doneLatch = CountDownLatch(threadCount)
        val failure = AtomicReference<Throwable?>(null)
        val executor = Executors.newFixedThreadPool(threadCount)

        repeat(threadCount) { worker ->
            executor.execute {
                try {
                    startLatch.await()
                    repeat(iterationsPerThread) { iteration ->
                        historyService.recordCommand(CommandEntry(
                            toolName = "tool_${worker}_$iteration",
                            parameters = buildJsonObject { }
                        ))
                    }
                } catch (t: Throwable) {
                    failure.compareAndSet(null, t)
                } finally {
                    doneLatch.countDown()
                }
            }
        }

        startLatch.countDown()
        assertTrue("Concurrent recording did not finish in time", doneLatch.await(30, TimeUnit.SECONDS))
        executor.shutdownNow()

        failure.get()?.let { throw AssertionError("Concurrent recording should not throw", it) }

        val history = historyService.entries
        assertTrue("History should not exceed max size after concurrent writes", history.size <= 100)

        val sentinel = CommandEntry(
            toolName = "sentinel",
            parameters = buildJsonObject { }
        )
        historyService.recordCommand(sentinel)
        assertEquals("Newest entry should be first", sentinel.id, historyService.entries.first().id)
    }

    fun testMaxHistorySizeZeroDisablesAndClearsHistory() {
        historyService.recordCommand(CommandEntry(
            toolName = "before_disable",
            parameters = buildJsonObject { }
        ))
        assertEquals(1, historyService.entries.size)

        McpSettings.getInstance().maxHistorySize = 0

        assertTrue("History should be cleared when max size is zero", historyService.entries.isEmpty())

        historyService.recordCommand(CommandEntry(
            toolName = "after_disable",
            parameters = buildJsonObject { }
        ))
        assertTrue("History should stay empty when disabled", historyService.entries.isEmpty())
    }

    fun testNegativeMaxHistorySizeIsClampedToDisabled() {
        historyService.recordCommand(CommandEntry(
            toolName = "before_negative_disable",
            parameters = buildJsonObject { }
        ))
        assertEquals(1, historyService.entries.size)

        McpSettings.getInstance().maxHistorySize = -1

        assertTrue("Negative max size should clear history", historyService.entries.isEmpty())

        historyService.recordCommand(CommandEntry(
            toolName = "after_negative_disable",
            parameters = buildJsonObject { }
        ))
        assertTrue("Negative max size should disable recording", historyService.entries.isEmpty())
    }

    fun testExportToJson() {
        historyService.recordCommand(CommandEntry(
            toolName = "tool1",
            parameters = buildJsonObject { put("key", "value") }
        ))
        historyService.recordCommand(CommandEntry(
            toolName = "tool2",
            parameters = buildJsonObject { }
        ))

        val jsonExport = historyService.exportToJson()

        assertNotNull(jsonExport)
        assertTrue("JSON should contain tool1", jsonExport.contains("tool1"))
        assertTrue("JSON should contain tool2", jsonExport.contains("tool2"))
    }

    fun testExportToCsv() {
        historyService.recordCommand(CommandEntry(
            toolName = "tool1",
            parameters = buildJsonObject { }
        ))
        historyService.recordCommand(CommandEntry(
            toolName = "tool2",
            parameters = buildJsonObject { }
        ))

        val csvExport = historyService.exportToCsv()

        assertNotNull(csvExport)
        assertTrue("CSV should have header", csvExport.contains("ID,Timestamp"))
        assertTrue("CSV should contain tool1", csvExport.contains("tool1"))
        assertTrue("CSV should contain tool2", csvExport.contains("tool2"))
    }

    fun testGetHistoryByFilter() {
        historyService.recordCommand(CommandEntry(
            toolName = "find_usages",
            parameters = buildJsonObject { }
        ))
        historyService.recordCommand(CommandEntry(
            toolName = "find_definition",
            parameters = buildJsonObject { }
        ))

        val entry3 = CommandEntry(
            toolName = "find_usages",
            parameters = buildJsonObject { }
        )
        historyService.recordCommand(entry3)
        historyService.updateCommandStatus(entry3.id, CommandStatus.ERROR, "Failed", 10)

        val allHistory = historyService.entries
        assertEquals(3, allHistory.size)

        val findUsagesFilter = CommandFilter(toolName = "find_usages")
        val findUsagesHistory = historyService.getFilteredHistory(findUsagesFilter)
        assertEquals(2, findUsagesHistory.size)

        val errorFilter = CommandFilter(status = CommandStatus.ERROR)
        val errorHistory = historyService.getFilteredHistory(errorFilter)
        assertEquals(1, errorHistory.size)
    }

    fun testCommandEntryTimestamp() {
        val beforeCreate = java.time.Instant.now()
        val entry = CommandEntry(
            toolName = "test",
            parameters = buildJsonObject { }
        )
        val afterCreate = java.time.Instant.now()

        assertTrue("Timestamp should be after test start", !entry.timestamp.isBefore(beforeCreate))
        assertTrue("Timestamp should be before test end", !entry.timestamp.isAfter(afterCreate))
    }

    fun testCommandEntryId() {
        val entry1 = CommandEntry(toolName = "test1", parameters = buildJsonObject { })
        val entry2 = CommandEntry(toolName = "test2", parameters = buildJsonObject { })

        assertFalse("Each entry should have unique ID", entry1.id == entry2.id)
    }
}
