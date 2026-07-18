package com.github.vcth4nh.idesense.handlers

import com.intellij.find.findUsages.FindUsagesHandler
import com.intellij.find.findUsages.FindUsagesHandlerFactory
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.search.SearchScope
import com.intellij.util.Processor

/**
 * Routes find-usages through IntelliJ's [FindUsagesHandlerFactory] extension — the
 * same path the IDE's Find Usages action takes. This gives language-plugin parity:
 * Python skeleton ↔ typeshed, Java `.class` ↔ source, Kotlin light classes, etc.
 *
 * Plain [com.intellij.psi.search.searches.ReferencesSearch] only finds references to
 * the exact target PSI element, missing equivalent declarations. The per-language
 * handler's `primaryElements` / `secondaryElements` expands to the full equivalence
 * class before searching.
 */
internal object FindUsagesHandlerSearch {

    private val LOG = logger<FindUsagesHandlerSearch>()

    /**
     * Attempts to find references to [element] via the appropriate [FindUsagesHandler].
     *
     * Uses `findReferencesToHighlight` rather than `processElementUsages` — it's the
     * code path the IDE's Ctrl+click-on-declaration and highlight-usages actions use.
     * Both do per-language expansion via `getPrimaryElements`/`getSecondaryElements`
     * and hand the expanded set to [com.intellij.psi.search.searches.ReferencesSearch]
     * with language-appropriate `createSearchParameters`. `processElementUsages` runs
     * additional machinery (text occurrences, progress UI, language-specific helpers)
     * that asserts EDT inside `JavaFindUsagesHelper` on IntelliJ 2025.1.
     *
     * Returns `true` if a handler was found (result may be empty). Returns `false`
     * if no factory claims the element; callers should fall back to plain
     * [com.intellij.psi.search.searches.ReferencesSearch].
     *
     * When a handler stage throws and is swallowed (see the per-stage catches below),
     * a human-readable message is added to [warnings] so callers can surface the
     * partial coverage instead of returning a silently smaller result (#81).
     */
    fun processReferences(
        project: Project,
        element: PsiElement,
        scope: SearchScope,
        processor: Processor<PsiElement>,
        warnings: MutableCollection<String>? = null
    ): Boolean {
        val factory = FindUsagesHandlerFactory.EP_NAME.getExtensions(project)
            .firstOrNull { safeCanFindUsages(it, element) } ?: return false

        val handler = try {
            factory.createFindUsagesHandler(element, false)
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.warn("FindUsagesHandlerFactory ${factory.javaClass.name} threw while creating handler", e)
            return false
        } ?: return false

        if (handler === FindUsagesHandler.NULL_HANDLER) return false

        // `getPrimaryElements`/`getSecondaryElements` can show modal UI on some handlers
        // (e.g. JavaFindUsagesHandler for PsiMethod triggers SuperMethodWarningUtil dialogs,
        // PsiParameter triggers ProgressManager.runProcessWithProgressSynchronously).
        // Both assert EDT. Fall back to the original element when expansion fails.
        val primary = try {
            handler.primaryElements.toList()
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.warn("FindUsagesHandler ${handler.javaClass.name} threw on primaryElements", e)
            addStageWarning(warnings, handler, "primaryElements", "searched the anchor element only")
            listOf(element)
        }
        val secondary = try {
            handler.secondaryElements.toList()
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.warn("FindUsagesHandler ${handler.javaClass.name} threw on secondaryElements", e)
            addStageWarning(warnings, handler, "secondaryElements", "secondary targets skipped")
            emptyList()
        }

        for (target in (primary + secondary).distinct()) {
            ProgressManager.checkCanceled()
            if (!target.isValid) continue
            val refs = try {
                handler.findReferencesToHighlight(target, scope)
            } catch (e: ProcessCanceledException) {
                throw e
            } catch (e: LinkageError) {
                throw e
            } catch (e: Throwable) {
                LOG.warn("FindUsagesHandler ${handler.javaClass.name} threw on findReferencesToHighlight", e)
                addStageWarning(warnings, handler, "findReferencesToHighlight", "skipped a search target")
                continue
            }
            for (ref in refs) {
                val refElement = ref.element
                if (refElement.isValid && !processor.process(refElement)) return true
            }
        }
        return true
    }

    private fun addStageWarning(
        warnings: MutableCollection<String>?,
        handler: FindUsagesHandler,
        stage: String,
        consequence: String
    ) {
        if (warnings == null) return
        val message =
            "Find-usages handler ${handler.javaClass.simpleName} threw on $stage; $consequence — usages may be incomplete."
        if (message !in warnings) warnings.add(message)
    }

    private fun safeCanFindUsages(factory: FindUsagesHandlerFactory, element: PsiElement): Boolean =
        try {
            factory.canFindUsages(element)
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (_: Throwable) {
            false
        }
}
