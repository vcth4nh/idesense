package com.github.vcth4nh.idesense.tools.refactoring

import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.util.PsiTreeUtil
import java.util.concurrent.atomic.AtomicBoolean

private const val WAIT_FOR_INDEXING =
    "Wait for the end of the indexing (${ToolNames.INDEX_STATUS} shows isDumbMode: false), then call again."

/** The `index_not_ready` text of `ide_refactor_rename` when the rename met dumb mode (#295). */
internal const val RENAME_STOPPED_BY_DUMB_MODE =
    "The IDE went into dumb mode before the rename ran, and nothing changed. $WAIT_FOR_INDEXING"

/** The `index_not_ready` text of `ide_move_file` when the move met dumb mode (#295). */
internal const val MOVE_STOPPED_BY_DUMB_MODE =
    "The IDE went into dumb mode before the move ran, and nothing changed. $WAIT_FOR_INDEXING"

/** The text after "Rename failed: " or "Move failed: " when a refactoring made no change and met no dumb mode. */
internal const val NOTHING_CHANGED = "nothing changed, and the IDE gave no reason."

/**
 * Runs [refactoring] on the EDT and returns true when the IDE entered dumb mode during it, or is in
 * dumb mode at its end. A refactoring processor of the platform that meets dumb mode shows the dumb
 * mode notification of the IDE and returns with no change and no exception
 * (`BaseRefactoringProcessor.doRun`, #295). The IDE publishes [DumbService.DUMB_MODE] on the EDT
 * when it enters dumb mode (`DumbServiceImpl.incrementDumbCounter`, ideaIC-2025.1.3).
 */
internal fun metDumbModeDuring(project: Project, refactoring: () -> Unit): Boolean {
    val entered = AtomicBoolean()
    val connection = project.messageBus.connect()
    try {
        connection.subscribe(DumbService.DUMB_MODE, object : DumbService.DumbModeListener {
            override fun enteredDumbMode() {
                entered.set(true)
            }
        })
        refactoring()
    } finally {
        connection.disconnect()
    }
    return entered.get() || DumbService.isDumb(project)
}

/**
 * Abstract base class for all refactoring tools.
 *
 * Provides common utilities for:
 * - Finding named elements at positions
 * - Tracking affected files
 *
 * ## Two-Phase Refactoring Pattern
 *
 * All refactoring tools should follow this pattern to avoid UI freezes:
 *
 * 1. **Background Phase (Read Action)**: Collect all data needed for the refactoring
 *    - Find elements, search for references, etc.
 *    - This can be slow and runs in background
 *
 * 2. **EDT Phase (Write Action)**: Apply pre-computed changes
 *    - Use `withContext(Dispatchers.EDT)` + `WriteCommandAction`
 *    - Should be fast - only apply changes, no searching
 *
 * Example:
 * ```kotlin
 * override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
 *     // Phase 1: Background - collect data
 *     val data = readAction { collectData(project, ...) }
 *
 *     // Phase 2: EDT - apply changes quickly
 *     withContext(Dispatchers.EDT) {
 *         WriteCommandAction.writeCommandAction(project)
 *             .run<Throwable> { applyChanges(data) }
 *     }
 * }
 * ```
 */
abstract class AbstractRefactoringTool : AbstractMcpTool() {

    /**
     * Finds the named element at the given position (or its parent if the element is not named).
     */
    protected fun findNamedElement(
        project: Project,
        file: String,
        line: Int,
        column: Int
    ): PsiNamedElement? {
        val element = findPsiElement(project, file, line, column) ?: return null
        return findNamedElement(element)
    }

    /**
     * Finds the named element from the given PSI element (traverses up if needed).
     * Excludes PsiFile to prevent accidental file deletion when targeting whitespace/comments.
     */
    protected fun findNamedElement(element: PsiElement): PsiNamedElement? {
        if (element is PsiNamedElement && element !is PsiFile && element.name != null) {
            return element
        }
        val parent = PsiTreeUtil.getParentOfType(element, PsiNamedElement::class.java)
        // Don't return PsiFile as a deletable element, and ensure it has a name
        return if (parent is PsiFile || parent?.name == null) null else parent
    }

    /**
     * Tracks a file as affected by the refactoring.
     */
    protected fun trackAffectedFile(
        project: Project,
        file: VirtualFile,
        collector: MutableSet<String>
    ) {
        collector.add(getRelativePath(project, file))
    }
}
