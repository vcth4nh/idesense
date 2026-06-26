package com.github.vcth4nh.idesense.ui

import com.github.vcth4nh.idesense.history.CommandEntry
import com.github.vcth4nh.idesense.history.CommandFilter
import com.github.vcth4nh.idesense.history.CommandHistoryService
import com.github.vcth4nh.idesense.settings.McpSettings
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.serialization.json.buildJsonObject
import javax.swing.DefaultListModel

class McpToolWindowPanelTest : BasePlatformTestCase() {

    private lateinit var historyService: CommandHistoryService
    private var originalMaxHistorySize: Int = 100

    override fun setUp() {
        super.setUp()
        originalMaxHistorySize = McpSettings.getInstance().maxHistorySize
        historyService = CommandHistoryService.getInstance(project)
        historyService.clearHistory()
    }

    override fun tearDown() {
        try {
            historyService.clearHistory()
            McpSettings.getInstance().maxHistorySize = originalMaxHistorySize
        } finally {
            super.tearDown()
        }
    }

    fun testFilteredHistoryRefreshRemovesTrimmedEntries() {
        McpSettings.getInstance().maxHistorySize = 1

        val panel = McpToolWindowPanel(project)
        try {
            applyFilter(panel, CommandFilter(toolName = "match"))

            historyService.recordCommand(CommandEntry(
                toolName = "match",
                parameters = buildJsonObject { }
            ))
            dispatchUiEvents()
            assertEquals(listOf("match"), visibleToolNames(panel))

            historyService.recordCommand(CommandEntry(
                toolName = "other",
                parameters = buildJsonObject { }
            ))
            dispatchUiEvents()

            assertTrue(
                "Filtered history should be rebuilt from the bounded service snapshot",
                visibleToolNames(panel).isEmpty()
            )
        } finally {
            panel.dispose()
        }
    }

    private fun applyFilter(panel: McpToolWindowPanel, filter: CommandFilter) {
        val filterField = McpToolWindowPanel::class.java.getDeclaredField("currentFilter")
        filterField.isAccessible = true
        filterField.set(panel, filter)

        val refreshMethod = McpToolWindowPanel::class.java.getDeclaredMethod("refreshHistory")
        refreshMethod.isAccessible = true
        refreshMethod.invoke(panel)
    }

    @Suppress("UNCHECKED_CAST")
    private fun visibleToolNames(panel: McpToolWindowPanel): List<String> {
        val modelField = McpToolWindowPanel::class.java.getDeclaredField("historyListModel")
        modelField.isAccessible = true
        val model = modelField.get(panel) as DefaultListModel<CommandEntry>
        return (0 until model.size()).map { model.getElementAt(it).toolName }
    }

    private fun dispatchUiEvents() {
        PlatformTestUtil.dispatchAllEventsInIdeEventQueue()
    }
}
