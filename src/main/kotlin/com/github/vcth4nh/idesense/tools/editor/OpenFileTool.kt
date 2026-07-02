package com.github.vcth4nh.idesense.tools.editor

import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.OpenFileResult
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive

class OpenFileTool : AbstractMcpTool() {

    override val requiresPsiSync: Boolean = false

    override val name = ToolNames.OPEN_FILE

    override val description = """
        Open a file in the IDE editor, optionally jumping to a specific line and column. Use when
        you want to surface a file to the user or pre-position the caret before a subsequent
        operation that requires an open editor (e.g. ide_diagnostics intentions).

        Returns: the opened file's project-relative path and a confirmation message.

        Gotchas: disabled by default — must be enabled in Settings → Tools → IdeSense. column
        requires line to be specified.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .file(description = "File path relative to project root, or absolute path.")
        .intProperty("line", "1-based line number to navigate to.")
        .intProperty("column", "1-based column number to navigate to. Requires line to be specified.")
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val filePath = arguments["file"]?.jsonPrimitive?.content
            ?: return createErrorResult("Missing required parameter: file")

        val line = arguments["line"]?.jsonPrimitive?.int
        val column = arguments["column"]?.jsonPrimitive?.int

        if (column != null && line == null) {
            return createErrorResult("Parameter 'column' requires 'line' to be specified.")
        }

        if (line != null && line < 1) {
            return createErrorResult("Parameter 'line' must be >= 1, got $line.")
        }

        if (column != null && column < 1) {
            return createErrorResult("Parameter 'column' must be >= 1, got $column.")
        }

        val virtualFile = resolveFile(project, filePath)
            ?: return createErrorResult("File not found: $filePath")

        val relativePath = getRelativePath(project, virtualFile)

        edtAction {
            if (line != null) {
                val lineIndex = line - 1
                val columnIndex = if (column != null) column - 1 else 0
                val descriptor = OpenFileDescriptor(project, virtualFile, lineIndex, columnIndex)
                FileEditorManager.getInstance(project).openTextEditor(descriptor, true)
            } else {
                FileEditorManager.getInstance(project).openFile(virtualFile, true)
            }
        }

        val message = if (line != null && column != null) {
            "Opened $relativePath at line $line, column $column."
        } else if (line != null) {
            "Opened $relativePath at line $line."
        } else {
            "Opened $relativePath."
        }

        return createJsonResult(OpenFileResult(
            file = relativePath,
            opened = true,
            message = message
        ))
    }
}
