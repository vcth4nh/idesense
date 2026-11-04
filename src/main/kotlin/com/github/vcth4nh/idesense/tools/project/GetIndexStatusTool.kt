package com.github.vcth4nh.idesense.tools.project

import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.AllProjectsTool
import com.github.vcth4nh.idesense.tools.models.AllProjectsIndexStatusResult
import com.github.vcth4nh.idesense.tools.models.IndexStatusResult
import com.github.vcth4nh.idesense.tools.models.ProjectIndexStatus
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import kotlinx.serialization.json.JsonObject

class GetIndexStatusTool : AbstractMcpTool(), AllProjectsTool {

    // This tool only checks status, no PSI operations needed
    override val requiresPsiSync: Boolean = false

    override val name = "ide_index_status"

    override val description = """
        Check whether the IDE has finished indexing and is ready for code-intelligence operations.
        Call this before batch operations or when other tools return index_not_ready errors; prefer
        this over retrying blindly.

        Returns: isDumbMode (true = indexing in progress, most tools will fail).
        When isDumbMode is true, wait and retry — indexing will complete automatically.

        Without project_path while several projects are open, returns the status of each open
        project in projects (name, path, isDumbMode); the top-level isDumbMode is then true when any
        project is indexing.

        Gotchas: read-only and very fast; after project resolution and argument validation it succeeds in both smart and dumb mode.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val dumbService = DumbService.getInstance(project)
        val isDumb = dumbService.isDumb

        return createJsonResult(IndexStatusResult(
            isDumbMode = isDumb
        ))
    }

    override suspend fun executeForAllProjects(projects: List<Project>): ToolCallResult {
        val statuses = projects.map {
            ProjectIndexStatus(name = it.name, path = it.basePath ?: "", isDumbMode = DumbService.getInstance(it).isDumb)
        }
        return createJsonResult(AllProjectsIndexStatusResult(isDumbMode = statuses.any { it.isDumbMode }, projects = statuses))
    }
}
