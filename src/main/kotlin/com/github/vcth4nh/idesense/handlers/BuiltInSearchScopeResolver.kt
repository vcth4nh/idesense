package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.constants.ParamNames
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectFileIndex
import com.intellij.openapi.roots.ProjectRootManager
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.search.DelegatingGlobalSearchScope
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.search.SearchScope
import com.intellij.util.concurrency.annotations.RequiresReadLock
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive

internal object BuiltInSearchScopeResolver {

    fun parse(arguments: JsonObject, defaultScope: BuiltInSearchScope): BuiltInSearchScope {
        val rawScope = arguments[ParamNames.SCOPE]?.jsonPrimitive?.content ?: return defaultScope
        return BuiltInSearchScope.fromWireValue(rawScope) ?: throw IllegalArgumentException(
            "Unsupported scope '$rawScope'. Supported values: ${BuiltInSearchScope.supportedWireValues().joinToString(", ")}"
        )
    }

    fun resolveGlobalScope(project: Project, scope: BuiltInSearchScope): GlobalSearchScope = when (scope) {
        BuiltInSearchScope.PROJECT_FILES -> GlobalSearchScope.projectScope(project)
        BuiltInSearchScope.PROJECT_AND_LIBRARIES -> GlobalSearchScope.allScope(project)
        BuiltInSearchScope.PROJECT_PRODUCTION_FILES -> {
            val fileIndex = ProjectRootManager.getInstance(project).fileIndex
            projectContentScope(project) { file -> isProductionFile(fileIndex, file) }
        }
        BuiltInSearchScope.PROJECT_TEST_FILES -> {
            val fileIndex = ProjectRootManager.getInstance(project).fileIndex
            projectContentScope(project) { file -> isTestFile(fileIndex, file) }
        }
    }

    /**
     * Why [scope] can match no file, or null when it can match files. The production and test
     * scopes need source roots: in a project without production (or test) source roots, the scope
     * is empty, as the IDE's "Project Production Files" scope is. An empty result would then read
     * as "no matches", so tools report this reason instead. Uses the same predicates as the scopes.
     */
    @RequiresReadLock
    fun missingRootsReason(project: Project, scope: BuiltInSearchScope): String? {
        val rootManager = ProjectRootManager.getInstance(project)
        val fileIndex = rootManager.fileIndex
        val roots = rootManager.contentSourceRoots
        return when (scope) {
            BuiltInSearchScope.PROJECT_PRODUCTION_FILES ->
                if (roots.any { isProductionFile(fileIndex, it) }) null
                else "the project has no production source roots (no folder is marked as a non-test source root)"
            BuiltInSearchScope.PROJECT_TEST_FILES ->
                if (roots.any { isTestFile(fileIndex, it) }) null
                else "the project has no test source roots (no folder is marked as a test source root)"
            else -> null
        }
    }

    private fun isProductionFile(fileIndex: ProjectFileIndex, file: VirtualFile): Boolean =
        fileIndex.isInSourceContent(file) && !fileIndex.isInTestSourceContent(file)

    private fun isTestFile(fileIndex: ProjectFileIndex, file: VirtualFile): Boolean =
        fileIndex.isInTestSourceContent(file)

    fun resolveSearchScope(project: Project, scope: BuiltInSearchScope): SearchScope =
        resolveGlobalScope(project, scope)

    private fun projectContentScope(
        project: Project,
        predicate: (VirtualFile) -> Boolean
    ): GlobalSearchScope {
        val baseScope = GlobalSearchScope.projectScope(project)
        return object : DelegatingGlobalSearchScope(baseScope) {
            override fun contains(file: VirtualFile): Boolean = super.contains(file) && predicate(file)
        }
    }
}
