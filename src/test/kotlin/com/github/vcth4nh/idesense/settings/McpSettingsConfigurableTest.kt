package com.github.vcth4nh.idesense.settings

import com.github.vcth4nh.idesense.McpBundle
import com.github.vcth4nh.idesense.settings.McpSettings.AvailableProjectsMode
import com.github.vcth4nh.idesense.settings.McpSettings.ResponseFormat
import com.intellij.openapi.ui.ComboBox
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.intellij.ui.SimpleColoredComponent
import com.intellij.util.ui.UIUtil
import javax.swing.JComponent
import javax.swing.JLabel
import javax.swing.JList
import javax.swing.ListCellRenderer

// The text that the combo boxes of the settings page show for each value and for no value (#76).
class McpSettingsConfigurableTest : BasePlatformTestCase() {

    fun testTheComboBoxesShowTheLabelOfEachValueAndNoTextForNoValue() {
        val configurable = McpSettingsConfigurable()
        try {
            val boxes = UIUtil.findComponentsOfType(configurable.createComponent(), ComboBox::class.java)
            val shown = boxes.flatMap { box ->
                ((0 until box.itemCount).map { box.getItemAt(it) } + null).map { value -> value to renderedText(box, value) }
            }
            assertEquals(
                listOf(
                    AvailableProjectsMode.EXPANDED to McpBundle.message("settings.availableProjectsMode.expanded"),
                    AvailableProjectsMode.COMPACT to McpBundle.message("settings.availableProjectsMode.compact"),
                    null to "",
                    ResponseFormat.JSON to McpBundle.message("settings.responseFormat.json"),
                    ResponseFormat.TOON to McpBundle.message("settings.responseFormat.toon"),
                    null to "",
                ),
                shown,
            )
        } finally {
            configurable.disposeUIResources()
        }
    }

    // A SimpleListCellRenderer is a label. A renderer of the Kotlin UI DSL paints its text with a
    // SimpleColoredComponent.
    private fun renderedText(box: ComboBox<*>, value: Any?): String {
        @Suppress("UNCHECKED_CAST")
        val renderer = box.renderer as ListCellRenderer<Any?>
        val component = renderer.getListCellRendererComponent(JList<Any?>(), value, -1, false, false)
        if (component is JLabel) return component.text
        return UIUtil.findComponentsOfType(component as JComponent, SimpleColoredComponent::class.java)
            .joinToString("") { it.getCharSequence(false).toString() }
    }
}
