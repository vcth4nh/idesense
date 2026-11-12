package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.handlers.go.GoFindUsages
import com.intellij.find.findUsages.FindUsagesHandler
import com.intellij.find.findUsages.FindUsagesHandlerFactory
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.search.SearchScope
import com.intellij.usageView.UsageInfo
import com.intellij.util.Processor

/** One usage: the PSI element that holds it and the file offset where the usage text starts. */
internal class UsageHit(val element: PsiElement, val offset: Int)

/**
 * Routes find-usages through IntelliJ's [FindUsagesHandlerFactory] extension, which gives
 * the handler of the language plugin. This gives language-plugin parity:
 * Python skeleton ↔ typeshed, Java `.class` ↔ source, Kotlin light classes, etc.
 *
 * Plain [com.intellij.psi.search.searches.ReferencesSearch] only finds references to
 * the exact target PSI element, missing equivalent declarations. The per-language
 * handler's `primaryElements` / `secondaryElements` expands to the full equivalence
 * class before searching.
 *
 * The search of the handler takes one of two paths:
 * - Go: `processElementUsages`, the search of the IDE's Find Usages action. In GoLand only
 *   this path adds the usages of the interface methods that a method implements (#130) and
 *   the usages in comments (#132); the `findReferencesToHighlight` of the Go plugin has neither.
 * - All other languages: `findReferencesToHighlight`, the path of highlight usages. Their
 *   `processElementUsages` can assert EDT (see [processReferences]).
 */
internal object FindUsagesHandlerSearch {

    private val LOG = logger<FindUsagesHandlerSearch>()

    /**
     * Attempts to find the usages of [element] via the appropriate [FindUsagesHandler] and
     * gives each one to [processor] as a [UsageHit].
     *
     * The handler comes in the mode of the IDE's Find Usages action without its dialog
     * ([FindUsagesHandlerFactory.OperationMode.USAGES_WITH_DEFAULT_OPTIONS], the mode of
     * `FindUsagesManager.findUsages` when `showDialog` is false). For a Go method with a
     * super method, the mode `DEFAULT` opens a dialog, which asserts EDT (#130). Both paths
     * do per-language expansion via `getPrimaryElements`/`getSecondaryElements` first.
     *
     * - Go handler (`com.goide.usages.GoFindUsagesHandler`, see [GoFindUsages.isGoHandler]):
     *   `processElementUsages` with a clone of the default options of the handler, as the
     *   Find Usages action of GoLand runs it (#130, #132). `GoFindUsagesHandler` returns one
     *   options object per project, which its Find Usages dialog also reads, so only the clone
     *   gets [scope] and no text occurrences. The search is
     *   [com.intellij.psi.search.searches.ReferencesSearch], comment references included. When
     *   the options have `findBaseMethods` (a Go method), it also covers the references to the
     *   interface methods that the method implements, and [notes] gets
     *   [GoFindUsages.BASE_METHODS_NOTE]. The offset of a hit is `UsageInfo.navigationOffset`,
     *   so a usage in a comment points at the word.
     * - Any other handler: `findReferencesToHighlight` — it's the code path the IDE's
     *   Ctrl+click-on-declaration and highlight-usages actions use. It hands the expanded
     *   set to [com.intellij.psi.search.searches.ReferencesSearch] with language-appropriate
     *   `createSearchParameters`. `processElementUsages` runs additional machinery (text
     *   occurrences, progress UI, language-specific helpers) that asserts EDT inside
     *   `JavaFindUsagesHelper` on IntelliJ 2025.1. The offset of a hit is the `textOffset`
     *   of the reference element.
     *
     * Returns `true` if a handler was found (result may be empty). Returns `false`
     * if no factory claims the element or the factory throws; callers should fall back to plain
     * [com.intellij.psi.search.searches.ReferencesSearch].
     *
     * When the factory or a handler stage throws and is swallowed (see the catches below),
     * a human-readable message is added to [warnings] so callers can surface the
     * partial coverage instead of returning a silently smaller result (#81).
     */
    fun processReferences(
        project: Project,
        element: PsiElement,
        scope: SearchScope,
        processor: Processor<UsageHit>,
        warnings: MutableCollection<String>? = null,
        notes: MutableCollection<String>? = null,
    ): Boolean {
        val factory = FindUsagesHandlerFactory.EP_NAME.getExtensions(project)
            .firstOrNull { safeCanFindUsages(it, element) } ?: return false

        val handler = try {
            factory.createFindUsagesHandler(element, FindUsagesHandlerFactory.OperationMode.USAGES_WITH_DEFAULT_OPTIONS)
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.warn("FindUsagesHandlerFactory ${factory.javaClass.name} threw while creating handler", e)
            if (warnings != null) {
                val message = "Find-usages handler factory ${factory.javaClass.simpleName} threw while creating the handler; " +
                    "searched the references to the anchor element only — usages may be incomplete."
                if (message !in warnings) warnings.add(message)
            }
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

        if (GoFindUsages.isGoHandler(handler)) {
            // Never mutate the options object of the handler: GoLand shares it with its dialog.
            val options = handler.findUsagesOptions.clone()
            options.searchScope = scope
            options.isSearchForTextOccurrences = false
            if (notes != null && GoFindUsages.searchesBaseMethods(options) &&
                GoFindUsages.BASE_METHODS_NOTE !in notes
            ) {
                notes.add(GoFindUsages.BASE_METHODS_NOTE)
            }
            for (target in (primary + secondary).distinct()) {
                ProgressManager.checkCanceled()
                if (!target.isValid) continue
                // The caller's processor runs inside processElementUsages. Its exception goes to
                // the caller, as on the highlight path; only an exception of the handler is a stage warning.
                var callerFailure: Throwable? = null
                val completed = try {
                    handler.processElementUsages(target, Processor<UsageInfo> { info ->
                        val usageElement = info.element
                        val offset = info.navigationOffset
                        if (usageElement == null || !usageElement.isValid || offset < 0) true
                        else try {
                            processor.process(UsageHit(usageElement, offset))
                        } catch (e: Throwable) {
                            callerFailure = e
                            throw e
                        }
                    }, options)
                } catch (e: ProcessCanceledException) {
                    throw e
                } catch (e: LinkageError) {
                    throw e
                } catch (e: Throwable) {
                    callerFailure?.let { throw it }
                    LOG.warn("FindUsagesHandler ${handler.javaClass.name} threw on processElementUsages", e)
                    addStageWarning(warnings, handler, "processElementUsages", "skipped a search target")
                    continue
                }
                if (!completed) return true
            }
            return true
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
                if (refElement.isValid && !processor.process(UsageHit(refElement, refElement.textOffset))) return true
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
