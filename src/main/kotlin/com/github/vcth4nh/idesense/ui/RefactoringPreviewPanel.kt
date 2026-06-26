package com.github.vcth4nh.idesense.ui

import com.intellij.diff.DiffContentFactory
import com.intellij.diff.DiffDialogHints
import com.intellij.diff.DiffManager
import com.intellij.diff.requests.SimpleDiffRequest
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTabbedPane
import com.intellij.util.ui.JBUI
import java.awt.BorderLayout
import java.awt.Dimension
import java.awt.Font
import javax.swing.DefaultListModel
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JTextArea
import javax.swing.ListSelectionModel
import javax.swing.border.EmptyBorder

/**
 * Panel for previewing refactoring changes before applying them.
 * Shows a diff view of each affected file.
 */
class RefactoringPreviewPanel(
    private val project: Project?,
    private val operationName: String,
    private val changes: List<RefactoringChange>
) : DialogWrapper(project, true) {

    private var selectedChange: RefactoringChange? = null

    init {
        title = "Preview Refactoring: $operationName"
        init()
    }

    override fun createCenterPanel(): JComponent {
        val mainPanel = JPanel(BorderLayout(JBUI.scale(10), 0))
        mainPanel.preferredSize = Dimension(JBUI.scale(900), JBUI.scale(600))

        // Left panel: file list
        val leftPanel = createFileListPanel()
        mainPanel.add(leftPanel, BorderLayout.WEST)

        // Right panel: diff view
        val rightPanel = createDiffPanel()
        mainPanel.add(rightPanel, BorderLayout.CENTER)

        return mainPanel
    }

    private fun createFileListPanel(): JComponent {
        val panel = JPanel(BorderLayout())
        panel.preferredSize = Dimension(JBUI.scale(250), JBUI.scale(600))
        panel.border = JBUI.Borders.empty(0, 0, 0, 10)

        // Header
        val headerLabel = JBLabel("Affected Files (${changes.size})")
        headerLabel.font = headerLabel.font.deriveFont(Font.BOLD)
        headerLabel.border = JBUI.Borders.empty(0, 0, 5, 0)
        panel.add(headerLabel, BorderLayout.NORTH)

        // File list
        val listModel = DefaultListModel<RefactoringChange>()
        changes.forEach { listModel.addElement(it) }

        val fileList = JBList(listModel)
        fileList.selectionMode = ListSelectionModel.SINGLE_SELECTION
        fileList.cellRenderer = FileChangeRenderer()

        fileList.addListSelectionListener { e ->
            if (!e.valueIsAdjusting) {
                selectedChange = fileList.selectedValue
            }
        }

        // Select first item
        if (changes.isNotEmpty()) {
            fileList.selectedIndex = 0
            selectedChange = changes[0]
        }

        val scrollPane = JBScrollPane(fileList)
        panel.add(scrollPane, BorderLayout.CENTER)

        return panel
    }

    private fun createDiffPanel(): JComponent {
        val panel = JPanel(BorderLayout())

        // Tabbed pane for different views
        val tabbedPane = JBTabbedPane()

        // Summary tab
        val summaryPanel = createSummaryPanel()
        tabbedPane.addTab("Summary", summaryPanel)

        // Changes tab
        val changesPanel = createChangesTextPanel()
        tabbedPane.addTab("All Changes", changesPanel)

        panel.add(tabbedPane, BorderLayout.CENTER)

        return panel
    }

    private fun createSummaryPanel(): JComponent {
        val panel = JPanel(BorderLayout())
        panel.border = JBUI.Borders.empty(10)

        val summaryText = buildString {
            appendLine("Refactoring Operation: $operationName")
            appendLine()
            appendLine("Files to be modified: ${changes.size}")
            appendLine()

            appendLine("Changes summary:")
            changes.forEach { change ->
                appendLine("  • ${change.file}")
                appendLine("    ${change.description}")
            }
        }

        val textArea = JTextArea(summaryText)
        textArea.isEditable = false
        textArea.font = Font(Font.MONOSPACED, Font.PLAIN, 12)
        textArea.border = JBUI.Borders.empty(5)

        val scrollPane = JBScrollPane(textArea)
        panel.add(scrollPane, BorderLayout.CENTER)

        return panel
    }

    private fun createChangesTextPanel(): JComponent {
        val panel = JPanel(BorderLayout())
        panel.border = JBUI.Borders.empty(10)

        val changesText = buildString {
            changes.forEach { change ->
                appendLine("=" .repeat(60))
                appendLine("File: ${change.file}")
                appendLine("=" .repeat(60))
                appendLine()

                if (change.beforeContent != null && change.afterContent != null) {
                    appendLine("--- Before ---")
                    appendLine(change.beforeContent)
                    appendLine()
                    appendLine("+++ After +++")
                    appendLine(change.afterContent)
                } else {
                    appendLine(change.description)
                }
                appendLine()
            }
        }

        val textArea = JTextArea(changesText)
        textArea.isEditable = false
        textArea.font = Font(Font.MONOSPACED, Font.PLAIN, 12)
        textArea.border = JBUI.Borders.empty(5)

        val scrollPane = JBScrollPane(textArea)
        panel.add(scrollPane, BorderLayout.CENTER)

        return panel
    }

    /**
     * Custom renderer for file changes in the list
     */
    private inner class FileChangeRenderer : javax.swing.ListCellRenderer<RefactoringChange> {
        private val panel = JPanel(BorderLayout())
        private val fileLabel = JBLabel()
        private val descLabel = JBLabel()

        init {
            panel.border = JBUI.Borders.empty(5)
            panel.add(fileLabel, BorderLayout.NORTH)
            descLabel.font = descLabel.font.deriveFont(Font.ITALIC)
            descLabel.foreground = JBColor.GRAY
            panel.add(descLabel, BorderLayout.SOUTH)
        }

        override fun getListCellRendererComponent(
            list: javax.swing.JList<out RefactoringChange>?,
            value: RefactoringChange?,
            index: Int,
            isSelected: Boolean,
            cellHasFocus: Boolean
        ): java.awt.Component {
            if (value != null) {
                fileLabel.text = value.file.substringAfterLast("/")
                descLabel.text = value.description.take(50) + if (value.description.length > 50) "..." else ""
            }

            if (isSelected) {
                panel.background = list?.selectionBackground
                fileLabel.foreground = list?.selectionForeground
            } else {
                panel.background = list?.background
                fileLabel.foreground = list?.foreground
            }

            return panel
        }
    }

    companion object {
        /**
         * Shows the preview dialog and returns true if the user accepted.
         */
        fun showPreview(
            project: Project?,
            operationName: String,
            changes: List<RefactoringChange>
        ): Boolean {
            val panel = RefactoringPreviewPanel(project, operationName, changes)
            return panel.showAndGet()
        }

        /**
         * Shows a simple diff dialog for before/after comparison.
         */
        fun showDiff(
            project: Project?,
            title: String,
            beforeContent: String,
            afterContent: String,
            fileName: String
        ) {
            val factory = DiffContentFactory.getInstance()
            val beforeDoc = factory.create(beforeContent)
            val afterDoc = factory.create(afterContent)

            val request = SimpleDiffRequest(
                title,
                beforeDoc,
                afterDoc,
                "Before",
                "After"
            )

            DiffManager.getInstance().showDiff(project, request, DiffDialogHints.DEFAULT)
        }
    }
}

/**
 * Represents a single change in a refactoring operation.
 */
data class RefactoringChange(
    val file: String,
    val description: String,
    val beforeContent: String? = null,
    val afterContent: String? = null,
    val changeType: ChangeType = ChangeType.MODIFY
)

enum class ChangeType {
    ADD,
    MODIFY,
    DELETE,
    MOVE
}
