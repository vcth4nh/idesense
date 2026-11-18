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
import java.util.concurrent.ConcurrentHashMap

/**
 * One usage: the PSI element that holds it, the file offset where the usage text starts, and its
 * mark ([UsageMatch.BASE], [UsageMatch.OVERRIDE] or [UsageMatch.DYNAMIC]). A sure usage has no mark (null).
 */
internal class UsageHit(val element: PsiElement, val offset: Int, val match: String? = null)

/**
 * The rules of [provider], the provider of the language of [anchor], for each usage: the drop
 * ([SuperMethodsProvider.droppedUsageKind]) and the mark ([SuperMethodsProvider.usageMark]).
 * Each dropped position (file and offset) adds 1 to [dropped] one time. The search can call the
 * processor from more than one thread, thus the set of positions is concurrent and each change
 * of [dropped] holds its lock.
 */
internal class UsageRules(
    private val provider: SuperMethodsProvider?,
    private val anchor: PsiElement,
    private val dropped: MutableMap<String, Int>?,
) {
    private val droppedPositions = ConcurrentHashMap.newKeySet<Pair<Any, Int>>()

    private companion object {
        val LOG = logger<UsageRules>()
    }

    /** True when the search leaves out the usage at [usageElement] and [offset]. A provider that throws gives false. */
    fun drops(usageElement: PsiElement, offset: Int): Boolean {
        val provider = provider ?: return false
        val kind = try {
            provider.droppedUsageKind(usageElement, anchor)
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.debug("SuperMethodsProvider ${provider.javaClass.name} threw on droppedUsageKind", e)
            null
        } ?: return false
        val file: Any = usageElement.containingFile?.virtualFile ?: usageElement.containingFile ?: usageElement
        if (dropped != null && droppedPositions.add(file to offset)) synchronized(dropped) { dropped.merge(kind, 1, Int::plus) }
        return true
    }

    /** The mark of [reference], a usage that is no dynamic usage, in a pass with [passMark]. A provider that throws gives [passMark]. */
    fun mark(reference: PsiReference, passMark: String?): String? {
        val provider = provider ?: return passMark
        return try {
            provider.usageMark(reference, anchor, passMark)
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.debug("SuperMethodsProvider ${provider.javaClass.name} threw on usageMark", e)
            passMark
        }
    }
}

/**
 * Routes find-usages through IntelliJ's [FindUsagesHandlerFactory] extension, which gives
 * the handler of the language plugin. This gives language-plugin parity:
 * Python skeleton ↔ typeshed, Java `.class` ↔ source, Kotlin light classes, etc.
 *
 * Plain [ReferencesSearch] only finds references to the exact target PSI element, missing
 * equivalent declarations. The per-language handler's `primaryElements` / `secondaryElements`
 * expands to the full equivalence class before searching.
 *
 * The search has up to three passes (#171). The direct pass searches the symbol. The base pass
 * searches each base declaration that the symbol overrides or implements
 * ([SuperMethodsProvider.findBaseDeclarations]), because a call through a base declaration can
 * run the symbol. The override pass searches each declaration that overrides or implements the
 * symbol ([SuperMethodsProvider.findOverridingDeclarations]); the Go path has no override pass.
 * The result is the union of the passes. A usage of the base pass has the mark [UsageMatch.BASE],
 * a usage of the override pass the mark [UsageMatch.OVERRIDE]. A usage of which the reference does
 * not resolve has the mark [UsageMatch.DYNAMIC] ([isDynamicReference]). A usage with no mark is a
 * sure usage of the symbol.
 *
 * The provider of the language of the symbol can change the mark of a usage that is no dynamic
 * usage ([SuperMethodsProvider.usageMark]) and can leave out a usage
 * ([SuperMethodsProvider.droppedUsageKind]). A usage that is left out never goes to the caller;
 * the search counts it one time for each position (file and offset), and the tools give the count
 * in a note: no silent drop.
 *
 * Each target (the symbol and each base and overriding declaration) first goes to
 * [SuperMethodsProvider.findDirectReferences] of the provider of its language. When the provider
 * gives references, the search of that target takes them and uses no handler (#175): the Java and
 * Kotlin handlers send the search of a member to its base declarations, so they cannot search the
 * member itself. The PHP factory asks a question for a method with a base method (#182).
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
     * Finds the usages of [element], of its base declarations and of its overriding declarations,
     * and gives each one to [processor] as a [UsageHit] with its mark. The base declarations go to
     * [baseDeclarations] and the base declarations that the provider leaves out on purpose
     * ([SuperMethodsProvider.skippedBaseDeclarations]) go to [skippedBases] before the search
     * starts. The overriding declarations go to [overridingDeclarations] before the direct pass,
     * only when the override pass runs (not on the Go path). When the processor returns false, the
     * whole search stops: no later target and no later pass runs.
     *
     * Before the processor, each usage goes to [SuperMethodsProvider.droppedUsageKind] of the
     * provider of the language of [element]. When it gives a kind, the processor does not get the
     * usage, and [dropped] gets 1 more for that kind when the position (file and offset) is new.
     * [dropped] gets the kinds in the order in which they first occur when it keeps the insertion
     * order. The drop does not depend on [dropped]: with null, the search also leaves the usage out.
     * A reference that is no dynamic usage gets the mark of [SuperMethodsProvider.usageMark].
     * A hook that throws changes nothing: no drop, the mark of the pass, no overriding
     * declaration, no skipped base. A cancellation leaves the search.
     *
     * For [element] and for each base and overriding declaration, the search first asks the provider of the
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
     * the base pass gives the usages of the answer "Yes". The base pass and the override pass ask
     * for the handler of each declaration in [OperationMode.USAGES_WITH_DEFAULT_OPTIONS] first,
     * then in [OperationMode.HIGHLIGHT_USAGES]. Each handler does per-language expansion via
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
        overridingDeclarations: MutableCollection<PsiElement>? = null,
        skippedBases: MutableCollection<PsiElement>? = null,
        dropped: MutableMap<String, Int>? = null,
    ) {
        val provider = SuperMethodsProvider.EP.forLanguage(element.language)
        val bases = declarationsOf(provider, element, "findBaseDeclarations") { it.findBaseDeclarations(element) }
        baseDeclarations?.addAll(bases)
        skippedBases?.addAll(declarationsOf(provider, element, "skippedBaseDeclarations") { it.skippedBaseDeclarations(element) })
        val rules = UsageRules(provider, element, dropped)

        val directReferences = directReferencesOf(element, scope)
        val directPass: () -> Boolean = if (directReferences != null) {
            { processDirectReferences(element, directReferences, null, rules, processor) }
        } else {
            val directModes =
                if (bases.isEmpty()) listOf(OperationMode.USAGES_WITH_DEFAULT_OPTIONS) else listOf(OperationMode.HIGHLIGHT_USAGES)
            val direct = createHandler(project, element, directModes)
            val directHandler = direct.handler
            if (directHandler != null && GoFindUsages.isGoHandler(directHandler)) {
                val goHandler = if (bases.isEmpty()) directHandler
                else createHandler(project, element, listOf(OperationMode.USAGES_WITH_DEFAULT_OPTIONS)).handler
                if (goHandler != null && GoFindUsages.isGoHandler(goHandler)) {
                    searchGo(goHandler, element, bases.isNotEmpty(), scope, rules, processor, warnings)
                    return
                }
            }
            { searchTarget(element, direct, scope, null, rules, processor, warnings) }
        }

        val overrides = declarationsOf(provider, element, "findOverridingDeclarations") { it.findOverridingDeclarations(element) }
        overridingDeclarations?.addAll(overrides)

        if (!directPass()) return
        for (base in bases) {
            if (!searchDeclaration(project, base, scope, UsageMatch.BASE, rules, processor, warnings)) return
        }
        for (override in overrides) {
            if (!searchDeclaration(project, override, scope, UsageMatch.OVERRIDE, rules, processor, warnings)) return
        }
    }

    /**
     * Searches [target], a base declaration or an overriding declaration of the symbol, with the
     * mark [passMark]: the direct references of the provider of its language first, else its
     * handler. False when the processor stopped the search.
     */
    private fun searchDeclaration(
        project: Project,
        target: PsiElement,
        scope: SearchScope,
        passMark: String,
        rules: UsageRules,
        processor: Processor<UsageHit>,
        warnings: MutableCollection<String>?,
    ): Boolean {
        ProgressManager.checkCanceled()
        val references = directReferencesOf(target, scope)
        if (references != null) return processDirectReferences(target, references, passMark, rules, processor)
        val choice = createHandler(
            project, target, listOf(OperationMode.USAGES_WITH_DEFAULT_OPTIONS, OperationMode.HIGHLIGHT_USAGES)
        )
        return searchTarget(target, choice, scope, passMark, rules, processor, warnings)
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
     * The declarations that [find] gives for [element] from [provider], the provider of its
     * language (the base, skipped base or overriding declarations, named by [hook]): not [element]
     * itself, only valid elements, each one time, in the order of the provider. Empty when no
     * provider is registered or when the provider throws.
     */
    private fun declarationsOf(
        provider: SuperMethodsProvider?,
        element: PsiElement,
        hook: String,
        find: (SuperMethodsProvider) -> List<PsiElement>,
    ): List<PsiElement> {
        if (provider == null) return emptyList()
        val found = try {
            find(provider)
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.debug("SuperMethodsProvider ${provider.javaClass.name} threw on $hook", e)
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
     * the mark [UsageMatch.DYNAMIC] or the mark of [rules] for [passMark]. False when the processor
     * stopped the search.
     */
    private fun processDirectReferences(
        target: PsiElement,
        references: Collection<PsiReference>,
        passMark: String?,
        rules: UsageRules,
        processor: Processor<UsageHit>,
    ): Boolean {
        val targets = listOf(target)
        for (ref in references) {
            if (!processReference(ref, targets, passMark, rules, processor)) return false
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
     * and gives each hit the mark [UsageMatch.DYNAMIC] or the mark of [rules] for [passMark].
     * False when the processor stopped the search.
     */
    private fun searchTarget(
        target: PsiElement,
        choice: HandlerChoice,
        scope: SearchScope,
        passMark: String?,
        rules: UsageRules,
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
                processReference(ref, targets, passMark, rules, processor)
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
                if (!processReference(ref, targets, passMark, rules, processor)) return false
            }
        }
        return true
    }

    private fun processReference(
        ref: PsiReference,
        targets: Collection<PsiElement>,
        passMark: String?,
        rules: UsageRules,
        processor: Processor<UsageHit>,
    ): Boolean {
        val refElement = ref.element
        if (!refElement.isValid) return true
        val offset = refElement.textOffset
        if (rules.drops(refElement, offset)) return true
        val match = if (isDynamicReference(ref, targets)) UsageMatch.DYNAMIC else rules.mark(ref, passMark)
        return processor.process(UsageHit(refElement, offset, match))
    }

    /**
     * The Go path: `processElementUsages` of [handler] on each expanded target, in one pass or in
     * two passes (see [processReferences]). The drop of [rules] applies to `UsageInfo.element`.
     */
    private fun searchGo(
        handler: FindUsagesHandler,
        element: PsiElement,
        hasBases: Boolean,
        scope: SearchScope,
        rules: UsageRules,
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
                            if (rules.drops(usageElement, offset)) true
                            else {
                                val dynamic = info.isDynamicUsage || MarkdownFindUsages.isDynamicUsage(usageElement)
                                val match = if (dynamic) UsageMatch.DYNAMIC else passMark
                                processor.process(UsageHit(usageElement, offset, match))
                            }
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
