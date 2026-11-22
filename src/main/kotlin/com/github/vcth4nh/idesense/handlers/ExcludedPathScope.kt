package com.github.vcth4nh.idesense.handlers

import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectFileIndex
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtilCore
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.search.DelegatingGlobalSearchScope
import com.intellij.psi.search.GlobalSearchScope

/**
 * A [GlobalSearchScope] that delegates to [baseScope] but rejects files in excluded
 * directories (venv, node_modules, build output, worktrees).
 *
 * The rules of [isExcludedPath] test the path of a file relative to [baseDir], the folder of the
 * project base path. A file outside that folder is tested with its path relative to the content
 * root that holds it, so a folder above the content root does not change the result (#148). A
 * file in neither has no path that the rules can test, so the rules do not apply to it.
 *
 * Applying the filter at the scope level means IntelliJ's search infrastructure
 * never resolves PSI or allocates buffer slots for excluded files — unlike the
 * post-filter approach which requires over-fetching to compensate.
 */
class ExcludedPathScope(
    baseScope: GlobalSearchScope,
    private val baseDir: VirtualFile?,
    private val fileIndex: ProjectFileIndex,
) : DelegatingGlobalSearchScope(baseScope) {

    override fun contains(file: VirtualFile): Boolean {
        if (!super.contains(file)) return false
        val relativePath = baseDir?.let { VfsUtilCore.getRelativePath(file, it) }
            ?: fileIndex.getContentRootForFile(file)?.let { VfsUtilCore.getRelativePath(file, it) }
            ?: return true
        return !isExcludedPath(relativePath)
    }
}

/**
 * Wraps [GlobalSearchScope.projectScope] or [GlobalSearchScope.allScope] with
 * excluded-path filtering so that venv, node_modules, and worktree files are
 * never processed by IntelliJ's search APIs.
 */
fun createFilteredScope(project: Project, includeLibraries: Boolean = false): GlobalSearchScope {
    val baseDir = project.basePath?.let { LocalFileSystem.getInstance().findFileByPath(it) }
    val baseScope = if (includeLibraries) {
        GlobalSearchScope.allScope(project)
    } else {
        GlobalSearchScope.projectScope(project)
    }
    return ExcludedPathScope(baseScope, baseDir, ProjectFileIndex.getInstance(project))
}
