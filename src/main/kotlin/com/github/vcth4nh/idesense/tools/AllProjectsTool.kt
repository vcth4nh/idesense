package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.intellij.openapi.project.Project

/**
 * A tool that can answer for every open project at once. When `project_path` is omitted and
 * several projects are open, the JSON-RPC handler calls [executeForAllProjects] instead of
 * returning `multiple_projects_open`.
 */
interface AllProjectsTool {
    suspend fun executeForAllProjects(projects: List<Project>): ToolCallResult
}
