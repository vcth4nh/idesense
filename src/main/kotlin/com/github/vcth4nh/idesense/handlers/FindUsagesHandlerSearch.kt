package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.constants.UsageMatch
import com.github.vcth4nh.idesense.handlers.go.GoFindUsages
import com.github.vcth4nh.idesense.handlers.javascript.JavaScriptFindUsages
import com.github.vcth4nh.idesense.handlers.markdown.MarkdownFindUsages
import com.intellij.find.findUsages.FindUsagesHandler
import com.intellij.find.findUsages.FindUsagesHandlerFactory
import com.intellij.find.findUsages.FindUsagesHandlerFactory.OperationMode
import com.intellij.find.findUsages.FindUsagesOptions
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiPolyVariantReference
import com.intellij.psi.PsiReference
import com.intellij.psi.search.SearchScope
import com.intellij.psi.search.searches.ReferencesSearch
import com.intellij.usageView.UsageInfo
import com.intellij.util.Processor

/**
 * One usage: the PSI element that holds it, the file offset where the usage text starts, and its
 * mark ([UsageMatch.BASE] or [UsageMatch.DYNAMIC]). A sure usage has no mark (null).
 */
internal class UsageHit(val element: PsiElement, val offset: Int, val match: String? = null)

/**
 * Routes find-usages through IntelliJ's [FindUsagesHandlerFactory] extension, which gives
 * the handler of the language plugin. This gives language-plugin parity:
 * Python skeleton ↔ typeshed, Java `.class` ↔ source, Kotlin light classes, etc.
 *
 * Plain [ReferencesSearch] only finds references to the exact target PSI element, missing
 * equivalent declarations. The per-language handler's `primaryElements` / `secondaryElements`
 * expands to the full equivalence class before searching.
 *
 * The search has two passes (#171). The direct pass searches the symbol. The base pass searches
 * each base declaration that the symbol overrides or implements
 * ([SuperMethodsProvider.findBaseDeclarations]), because a call through a base declaration can
 * run the symbol. The result is the union of the two passes. A usage of the base pass has the mark
 * [UsageMatch.BASE]. A usage of which the reference does not resolve has the mark
 * [UsageMatch.DYNAMIC] ([isDynamicReference]). A usage with no mark is a sure usage of the symbol.
 *
 * Each target (the symbol and each base declaration) first goes to
 * [SuperMethodsProvider.findDirectReferences] of the provider of its language. When the provider
 * gives references, the search of that target takes them and uses no handler (#175): the Java and
 * Kotlin handlers send the search of a member to its base declarations, so they cannot search the
 * member itself.
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
     * Finds the usages of [element] and of its base declarations, and gives each one to
     * [processor] as a [UsageHit] with its mark. The base declarations go to [baseDeclarations]
     * before the search starts. When the processor returns false, the whole search stops: no
     * later target and no later pass runs.
     *
     * For [element] and for each base declaration, the search first asks the provider of the
     * language of that target for [SuperMethodsProvider.findDirectReferences]. When the result is
     * not null, the search gives these references to [processor] and asks no factory for a handler
     * of that target: no `primaryElements`, no `secondaryElements`, no `findReferencesToHighlight`
     * and no warning. When the result is null, the search of that target takes the handler, as
     * below. A provider that throws gives null; a cancellation leaves the search.
     *
     * The handler of the direct pass comes in the mode of the IDE's Find Usages action without
     * its dialog ([OperationMode.USAGES_WITH_DEFAULT_OPTIONS], the mode of
     * `FindUsagesManager.findUsages` when `showDialog` is false) when [element] has no base
     * declaration. For a member with a base declaration, that mode asks the question "find the
     * usages of the base member?" in some languages: a dialog, which asserts EDT (#130, #171).
     * Thus the direct pass then uses [OperationMode.HIGHLIGHT_USAGES], which asks no question, and
     * the base pass gives the usages of the answer "Yes". The base pass asks for the handler of
     * each base declaration in [OperationMode.USAGES_WITH_DEFAULT_OPTIONS] first, then in
     * [OperationMode.HIGHLIGHT_USAGES]. Each handler does per-language expansion via
     * `getPrimaryElements`/`getSecondaryElements` first.
     *
     * - Go handler (`com.goide.usages.GoFindUsagesHandler`, see [GoFindUsages.isGoHandler]):
     *   `processElementUsages` with a clone of the options of the handler in the mode
     *   [OperationMode.USAGES_WITH_DEFAULT_OPTIONS], as the Find Usages action of GoLand runs it
     *   (#130, #132). The routing looks at the handler of the direct pass first: the Go factory
     *   gives a Go handler in each mode (`GoFindUsagesHandlerFactory.createFindUsagesHandlerInner`,
     *   `plugins/go-plugin/lib/intellij.go.impl.jar`, build 262.8665). Thus a factory of another
     *   language is never asked for a member with a base declaration in the mode that can ask the
     *   question. `GoFindUsagesHandler` returns one options object per project, which its Find
     *   Usages dialog also reads, so only the clones get [scope] and no text occurrences. When
     *   [element] has a base declaration and the options have the field `findBaseMethods`, the
     *   search has two passes, whatever the value of the field is in the options of the handler:
     *   the direct pass with `findBaseMethods` false, then the base pass with `findBaseMethods`
     *   true. `GoMethodFindUsagesHandler.processElementUsages` then gives the references to the
     *   interface methods first and the references to the method after them; the caller keeps
     *   the first hit at a location, so a usage of the direct pass keeps no mark.
     *   Else one pass runs with the options as they are. The mark of a hit is
     *   [UsageMatch.DYNAMIC] when `UsageInfo.isDynamicUsage` is true, or when the hit is a symbol
     *   name in a code span of a Markdown file ([MarkdownFindUsages.isDynamicUsage]). The offset
     *   of a hit is `UsageInfo.navigationOffset`, so a usage in a comment points at the word.
     * - Any other handler: `findReferencesToHighlight` — it's the code path the IDE's
     *   Ctrl+click-on-declaration and highlight-usages actions use. It hands the expanded
     *   set to [ReferencesSearch] with language-appropriate `createSearchParameters`.
     *   `processElementUsages` runs additional machinery (text occurrences, progress UI,
     *   language-specific helpers) that asserts EDT inside `JavaFindUsagesHelper` on IntelliJ
     *   2025.1. The offset of a hit is the `textOffset` of the reference element.
     *
     * When no factory claims a target, or when no mode gives a handler, the search of that
     * target is a plain [ReferencesSearch].
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
        baseDeclarations: MutableCollection<PsiElement>? = null,
    ) {
        val bases = baseDeclarationsOf(element)
        baseDeclarations?.addAll(bases)

        val directReferences = directReferencesOf(element, scope)
        if (directReferences != null) {
            if (!processDirectReferences(element, directReferences, null, processor)) return
        } else {
            val directModes =
                if (bases.isEmpty()) listOf(OperationMode.USAGES_WITH_DEFAULT_OPTIONS) else listOf(OperationMode.HIGHLIGHT_USAGES)
            val direct = createHandler(project, element, directModes)
            val directHandler = direct.handler
            if (directHandler != null && GoFindUsages.isGoHandler(directHandler)) {
                val goHandler = if (bases.isEmpty()) directHandler
                else createHandler(project, element, listOf(OperationMode.USAGES_WITH_DEFAULT_OPTIONS)).handler
                if (goHandler != null && GoFindUsages.isGoHandler(goHandler)) {
                    searchGo(goHandler, element, bases.isNotEmpty(), scope, processor, warnings)
                    return
                }
            }

            if (!searchTarget(element, direct, scope, null, processor, warnings)) return
        }
        for (base in bases) {
            ProgressManager.checkCanceled()
            val baseReferences = directReferencesOf(base, scope)
            val completed = if (baseReferences != null) {
                processDirectReferences(base, baseReferences, UsageMatch.BASE, processor)
            } else {
                val choice = createHandler(
                    project, base, listOf(OperationMode.USAGES_WITH_DEFAULT_OPTIONS, OperationMode.HIGHLIGHT_USAGES)
                )
                searchTarget(base, choice, scope, UsageMatch.BASE, processor, warnings)
            }
            if (!completed) return
        }
    }

    /**
     * Language hook for the DYNAMIC mark: true when the usage of [reference] is a dynamic usage.
     * [targets] are the elements that the handler searches.
     *
     * The rule of the platform: `UsageInfo(PsiReference)` sets `myDynamicUsage` to
     * `multiResolve(false).length == 0` for a [PsiPolyVariantReference], else to
     * `resolve() == null` (`com.intellij.usageView.UsageInfo`, `lib/intellij.platform.core.jar`,
     * build 262.8665). `NonCodeUsageGroupingRule` puts a usage with `isDynamicUsage()` into the
     * group "Dynamic usages" (`lib/intellij.platform.usageView.impl.jar`).
     *
     * The rule of WebStorm for a reference in a JavaScript dialect file
     * ([JavaScriptFindUsages.isDynamicUsage]) also gives true. The rule of the Markdown plugin for
     * a symbol name in a code span of a Markdown file ([MarkdownFindUsages.isDynamicUsage]) also
     * gives true. The search asks the JavaScript check first, then the Markdown check, then the
     * platform rule. The two checks stop at once for other files, and the platform rule resolves
     * the reference. An exception gives false.
     */
    internal fun isDynamicReference(reference: PsiReference, targets: Collection<PsiElement>): Boolean =
        try {
            JavaScriptFindUsages.isDynamicUsage(reference, targets) == true ||
                MarkdownFindUsages.isDynamicUsage(reference.element) ||
                if (reference is PsiPolyVariantReference) reference.multiResolve(false).isEmpty()
                else reference.resolve() == null
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (_: Throwable) {
            false
        }

    /**
     * The base declarations of [element] from the provider of its language: not [element] itself,
     * only valid elements, each one time, in the order of the provider. Empty when the provider
     * throws.
     */
    private fun baseDeclarationsOf(element: PsiElement): List<PsiElement> {
        val provider = SuperMethodsProvider.EP.forLanguage(element.language) ?: return emptyList()
        val found = try {
            provider.findBaseDeclarations(element)
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.debug("SuperMethodsProvider ${provider.javaClass.name} threw on findBaseDeclarations", e)
            return emptyList()
        }
        return found.filter { it != element && it.isValid }.distinct()
    }

    /**
     * The references to [target] itself from [SuperMethodsProvider.findDirectReferences] of the
     * provider of the language of [target]. Null when no provider is registered, when the provider
     * gives null or when it throws: the search of [target] then takes the find-usages handler.
     */
    private fun directReferencesOf(target: PsiElement, scope: SearchScope): Collection<PsiReference>? {
        val provider = SuperMethodsProvider.EP.forLanguage(target.language) ?: return null
        return try {
            provider.findDirectReferences(target, scope)
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.debug("SuperMethodsProvider ${provider.javaClass.name} threw on findDirectReferences", e)
            null
        }
    }

    /**
     * Gives each reference of [references], the direct references of [target], to [processor] with
     * the mark [UsageMatch.DYNAMIC] or [passMark]. False when the processor stopped the search.
     */
    private fun processDirectReferences(
        target: PsiElement,
        references: Collection<PsiReference>,
        passMark: String?,
        processor: Processor<UsageHit>,
    ): Boolean {
        val targets = listOf(target)
        for (ref in references) {
            if (!processReference(ref, targets, passMark, processor)) return false
        }
        return true
    }

    /**
     * The handler for one target: [handler] is null when no factory claims the target or when no
     * mode gives a handler. [failure] is the first exception of a mode, null when no mode threw.
     */
    private class HandlerChoice(
        val factory: FindUsagesHandlerFactory?,
        val handler: FindUsagesHandler?,
        val failure: Throwable?,
    )

    /**
     * Asks the first factory that can find the usages of [target] for a handler in each mode of
     * [modes], in turn. The first handler that is not null and not [FindUsagesHandler.NULL_HANDLER]
     * wins. A mode that throws is skipped.
     */
    private fun createHandler(project: Project, target: PsiElement, modes: List<OperationMode>): HandlerChoice {
        val factory = FindUsagesHandlerFactory.EP_NAME.getExtensions(project)
            .firstOrNull { safeCanFindUsages(it, target) } ?: return HandlerChoice(null, null, null)
        var failure: Throwable? = null
        for (mode in modes) {
            val handler = try {
                factory.createFindUsagesHandler(target, mode)
            } catch (e: ProcessCanceledException) {
                throw e
            } catch (e: LinkageError) {
                throw e
            } catch (e: Throwable) {
                LOG.debug("FindUsagesHandlerFactory ${factory.javaClass.name} threw while creating handler in mode $mode", e)
                if (failure == null) failure = e
                null
            }
            if (handler != null && handler !== FindUsagesHandler.NULL_HANDLER) return HandlerChoice(factory, handler, failure)
        }
        return HandlerChoice(factory, null, failure)
    }

    /**
     * Searches [target] with the handler of [choice] (the path of the languages other than Go)
     * and gives each hit the mark [UsageMatch.DYNAMIC] or [passMark]. False when the processor
     * stopped the search.
     */
    private fun searchTarget(
        target: PsiElement,
        choice: HandlerChoice,
        scope: SearchScope,
        passMark: String?,
        processor: Processor<UsageHit>,
        warnings: MutableCollection<String>?,
    ): Boolean {
        val handler = choice.handler
        if (handler == null) {
            val failure = choice.failure
            if (failure != null && choice.factory != null) {
                LOG.warn("FindUsagesHandlerFactory ${choice.factory.javaClass.name} threw while creating handler", failure)
                if (warnings != null) {
                    val message = "Find-usages handler factory ${choice.factory.javaClass.simpleName} threw while creating the handler; " +
                        "searched the references to the anchor element only — usages may be incomplete."
                    if (message !in warnings) warnings.add(message)
                }
            }
            val targets = listOf(target)
            return ReferencesSearch.search(target, scope).forEach(Processor { ref ->
                processReference(ref, targets, passMark, processor)
            })
        }

        val targets = expandedTargets(handler, target, warnings)
        for (expandedTarget in targets) {
            ProgressManager.checkCanceled()
            if (!expandedTarget.isValid) continue
            val refs = try {
                handler.findReferencesToHighlight(expandedTarget, scope)
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
                if (!processReference(ref, targets, passMark, processor)) return false
            }
        }
        return true
    }

    private fun processReference(
        ref: PsiReference,
        targets: Collection<PsiElement>,
        passMark: String?,
        processor: Processor<UsageHit>,
    ): Boolean {
        val refElement = ref.element
        if (!refElement.isValid) return true
        val match = if (isDynamicReference(ref, targets)) UsageMatch.DYNAMIC else passMark
        return processor.process(UsageHit(refElement, refElement.textOffset, match))
    }

    /**
     * The Go path: `processElementUsages` of [handler] on each expanded target, in one pass or in
     * two passes (see [processReferences]).
     */
    private fun searchGo(
        handler: FindUsagesHandler,
        element: PsiElement,
        hasBases: Boolean,
        scope: SearchScope,
        processor: Processor<UsageHit>,
        warnings: MutableCollection<String>?,
    ) {
        val targets = expandedTargets(handler, element, warnings)
        // Never mutate the options object of the handler: GoLand shares it with its dialog.
        val handlerOptions = handler.findUsagesOptions
        fun passOptions(findBaseMethods: Boolean?): FindUsagesOptions = handlerOptions.clone().also {
            it.searchScope = scope
            it.isSearchForTextOccurrences = false
            if (findBaseMethods != null) GoFindUsages.setFindBaseMethods(it, findBaseMethods)
        }
        val options = passOptions(null)
        // setFindBaseMethods is false when the options have no field findBaseMethods: the options stay as they are.
        val passes: List<Pair<FindUsagesOptions, String?>> =
            if (hasBases && GoFindUsages.setFindBaseMethods(options, false)) listOf(options to null, passOptions(true) to UsageMatch.BASE)
            else listOf(options to null)

        for ((passOptions, passMark) in passes) {
            for (target in targets) {
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
                            val dynamic = info.isDynamicUsage || MarkdownFindUsages.isDynamicUsage(usageElement)
                            val match = if (dynamic) UsageMatch.DYNAMIC else passMark
                            processor.process(UsageHit(usageElement, offset, match))
                        } catch (e: Throwable) {
                            callerFailure = e
                            throw e
                        }
                    }, passOptions)
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
                if (!completed) return
            }
        }
    }

    /**
     * The targets of [handler]: its primary and secondary elements, each one time. When a stage
     * throws, [warnings] gets a message and the search uses [anchor] for the primary elements or
     * no secondary element.
     */
    private fun expandedTargets(
        handler: FindUsagesHandler,
        anchor: PsiElement,
        warnings: MutableCollection<String>?,
    ): List<PsiElement> {
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
            listOf(anchor)
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
        return (primary + secondary).distinct()
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
