package com.github.vcth4nh.idesense.tools.editor

import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.ActiveFileInfo
import com.github.vcth4nh.idesense.tools.models.GetActiveFileResult
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.TextEditor
import com.intellij.openapi.project.Project
import kotlinx.serialization.json.JsonObject

class GetActiveFileTool : AbstractMcpTool() {

    override val requiresPsiSync: Boolean = false

    override val name = ToolNames.GET_ACTIVE_FILE

    override val description = """
        Get the file(s) currently visible in the IDE editor — all visible tabs including split
        panes. Use when you need to know what the user is looking at or to anchor subsequent
        operations to the current cursor position.

        Returns: list of active files with project-relative path, cursor line/column, selected
        text (if any), and file type. Returns an empty list when no editors are open.

        Gotchas: disabled by default — must be enabled in Settings → IdeSense.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val activeFiles = edtAction {
            val editorManager = FileEditorManager.getInstance(project)
            val selectedEditors = editorManager.selectedEditors

            selectedEditors.mapNotNull { fileEditor ->
                val virtualFile = fileEditor.file ?: return@mapNotNull null
                val relativePath = getRelativePath(project, virtualFile)

                val textEditor = fileEditor as? TextEditor
                val editor = textEditor?.editor
                val caret = editor?.caretModel?.primaryCaret

                val line = caret?.let { it.logicalPosition.line + 1 }
                val column = caret?.let { it.logicalPosition.column + 1 }

                val selectionModel = editor?.selectionModel
                val hasSelection = selectionModel?.hasSelection() ?: false
                val selectedText = if (hasSelection) selectionModel?.selectedText else null

                val language = virtualFile.fileType.name

                ActiveFileInfo(
                    file = relativePath,
                    line = line,
                    column = column,
                    selectedText = selectedText,
                    hasSelection = hasSelection,
                    language = language
                )
            }
        }

        return createJsonResult(GetActiveFileResult(
            activeFiles = activeFiles
        ))
    }
}
