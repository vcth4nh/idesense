package com.github.vcth4nh.idesense.handlers

import com.intellij.ide.util.gotoByName.ChooseByNameInScopeItemProvider
import com.intellij.ide.util.gotoByName.ChooseByNameModel
import com.intellij.ide.util.gotoByName.ChooseByNameModelEx
import com.intellij.ide.util.gotoByName.ChooseByNamePopup
import com.intellij.ide.util.gotoByName.ChooseByNameViewModel
import com.intellij.ide.util.gotoByName.GotoSymbolModel2
import com.intellij.navigation.NavigationItem
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.progress.util.ProgressIndicatorBase
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.util.registry.Registry
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.util.Processor
import com.intellij.util.indexing.FindSymbolParameters
import com.intellij.util.indexing.IdFilter

internal data class PopupSearchCandidate(
    val item: NavigationItem,
    val fullName: String?
)

internal data class PopupSearchResult(
    val candidates: List<PopupSearchCandidate>,
    val isQualifiedQuery: Boolean
)

/**
 * Collects the items of a popup search. With [accept], only an accepted item is kept and counts
 * for [limit]: the popup gives its items in the order of its ranks, and the items with an exact
 * name can come after any number of other items (#131).
 */
internal class PopupCandidateCollector(private val limit: Int, private val accept: ((NavigationItem) -> Boolean)?) {
    val items = mutableListOf<NavigationItem>()

    /** Returns false when the search must stop. */
    fun offer(item: NavigationItem): Boolean {
        if (accept == null || accept(item)) items.add(item)
        return items.size < limit
    }
}

/**
 * Headless wrapper around the same model/provider stack used by IntelliJ's Go to Symbol popup.
 *
 * This preserves popup query parsing, full-name matching, and result ordering while staying usable
 * from MCP tool execution without constructing any UI.
 */
internal object PopupFaithfulSymbolSearch {

    private val LOG = logger<PopupFaithfulSymbolSearch>()

    /**
     * The item filter of [searchExactName]. It accepts an item whose name is [localPattern]. It
     * accepts each item one time: GoLand gives a symbol two times.
     */
    internal fun exactNameFilter(
        localPattern: String,
        ignoreCase: Boolean,
        nameOf: (NavigationItem) -> String?
    ): (NavigationItem) -> Boolean {
        val seen = HashSet<NavigationItem>()
        return { item -> nameOf(item).equals(localPattern, ignoreCase) && seen.add(item) }
    }

    /**
     * True when the items of the index name [indexName] can have the name [localPattern]. An index
     * name can have a qualifier or a prefix before the name of its items, and another case:
     * `caddypki.CA` in GoLand, `$count`, `getFoo`.
     */
    internal fun canHoldExactName(indexName: String, localPattern: String): Boolean =
        indexName.endsWith(localPattern, ignoreCase = true)

    /**
     * Gives [search] only the index names that can hold [localPattern]. The platform records for
     * each contributor the names for which the processor answers true, and it asks a contributor
     * only for the items of a recorded name. It continues with the next name after each answer
     * (`ContributorsBasedGotoByModel.processContributorNames`).
     */
    internal fun exactNameProcessor(localPattern: String, search: Processor<in String>): Processor<String> =
        Processor { name -> canHoldExactName(name, localPattern) && search.process(name) }

    fun search(
        project: Project,
        pattern: String,
        scope: GlobalSearchScope,
        limit: Int
    ): PopupSearchResult = search(project, pattern, scope, limit, exactNameIgnoreCase = null)

    /**
     * The items whose name is exactly the local pattern of [pattern] (the text after the last
     * qualifier separator), at most [limit]. The popup ranks its items by a fuzzy match, so the
     * items with the exact name can come after any number of other items: GoLand knows a symbol as
     * `package.name`, and the text `PKI` matches each symbol of the package `caddypki` (#131).
     * This search takes each item with the exact name, wherever the popup ranks it. It reads only
     * the index names that can hold the exact name, so a short name stays fast.
     */
    fun searchExactName(
        project: Project,
        pattern: String,
        scope: GlobalSearchScope,
        limit: Int,
        ignoreCase: Boolean
    ): PopupSearchResult = search(project, pattern, scope, limit, exactNameIgnoreCase = ignoreCase)

    /** [exactNameIgnoreCase] is null for the fuzzy search of the popup. */
    private fun search(
        project: Project,
        pattern: String,
        scope: GlobalSearchScope,
        limit: Int,
        exactNameIgnoreCase: Boolean?
    ): PopupSearchResult {
        val disposable = Disposer.newDisposable("PopupFaithfulSymbolSearch")
        try {
            val exactNameModel = exactNameIgnoreCase?.let { ExactNameSymbolModel(project, disposable) }
            val model = exactNameModel ?: GotoSymbolModel2(project, disposable)
            val context = resolveSearchContext(project)
            val provider = ChooseByNameModelEx.getItemProvider(model, context)
            val viewModel = HeadlessChooseByNameViewModel(project, model, limit)
            val transformedPattern = viewModel.transformPattern(pattern)
            val localPattern = buildLocalPattern(model, transformedPattern)
            val isQualifiedQuery = hasQualifiedSeparator(model, transformedPattern)
            val idFilter = IdFilter.getProjectIdFilter(project, scope.isSearchInLibraries)
            @Suppress("DEPRECATION")
            val parameters = FindSymbolParameters(pattern, localPattern, scope, idFilter)
            exactNameModel?.localPattern = localPattern
            val collector = PopupCandidateCollector(
                limit,
                exactNameIgnoreCase?.let { exactNameFilter(localPattern, it, SymbolDataConverter::nameOf) }
            )
            val indicator = ProgressIndicatorBase()

            if (provider is ChooseByNameInScopeItemProvider) {
                provider.filterElementsWithWeights(viewModel, parameters, indicator) { found ->
                    val item = found.item as? NavigationItem ?: return@filterElementsWithWeights true
                    collector.offer(item)
                }
            } else {
                provider.filterElements(viewModel, pattern, scope.isSearchInLibraries, indicator) { item ->
                    val navigationItem = item as? NavigationItem ?: return@filterElements true
                    collector.offer(navigationItem)
                }
            }

            return PopupSearchResult(
                candidates = collector.items.map { PopupSearchCandidate(item = it, fullName = model.getFullName(it)) },
                isQualifiedQuery = isQualifiedQuery
            )
        } finally {
            Disposer.dispose(disposable)
        }
    }

    private fun resolveSearchContext(project: Project): PsiElement? = runCatching {
        if (!ApplicationManager.getApplication().isDispatchThread) {
            return@runCatching null
        }

        val editor = FileEditorManager.getInstance(project).selectedTextEditor ?: return@runCatching null
        val psiFile = PsiDocumentManager.getInstance(project).getPsiFile(editor.document) ?: return@runCatching null
        val safeOffset = editor.caretModel.offset.coerceIn(0, psiFile.textLength)
        psiFile.findElementAt(safeOffset) ?: psiFile
    }.onFailure { error ->
        LOG.debug("Failed to resolve current editor context for popup-backed symbol search", error)
    }.getOrNull()

    private fun buildLocalPattern(model: ChooseByNameModel, transformedPattern: String): String {
        var lastSeparatorOccurrence = 0

        for (separator in model.separators) {
            var index = transformedPattern.lastIndexOf(separator)
            if (index == transformedPattern.length - separator.length) {
                index = transformedPattern.lastIndexOf(separator, index - 1)
            }
            lastSeparatorOccurrence = maxOf(lastSeparatorOccurrence, if (index == -1) index else index + separator.length)
        }

        return transformedPattern.substring(lastSeparatorOccurrence)
    }

    private fun hasQualifiedSeparator(model: ChooseByNameModel, transformedPattern: String): Boolean {
        return model.separators.any { separator ->
            val index = transformedPattern.lastIndexOf(separator)
            index >= 0 && index < transformedPattern.length - separator.length
        }
    }

    /** The Go to Symbol model, with only the index names that can hold the exact name. */
    private class ExactNameSymbolModel(project: Project, parent: Disposable) : GotoSymbolModel2(project, parent) {
        lateinit var localPattern: String

        override fun processNames(nameProcessor: Processor<in String>, parameters: FindSymbolParameters) {
            super.processNames(exactNameProcessor(localPattern, nameProcessor), parameters)
        }
    }

    private class HeadlessChooseByNameViewModel(
        private val project: Project,
        private val model: ChooseByNameModel,
        private val maximumListSizeLimit: Int
    ) : ChooseByNameViewModel {

        override fun getProject(): Project = project

        override fun getModel(): ChooseByNameModel = model

        override fun isSearchInAnyPlace(): Boolean =
            Registry.`is`("ide.goto.middle.matching") && model.useMiddleMatching()

        override fun transformPattern(pattern: String): String =
            ChooseByNamePopup.getTransformedPattern(pattern, model)

        override fun canShowListForEmptyPattern(): Boolean = false

        override fun getMaximumListSizeLimit(): Int = maximumListSizeLimit
    }
}
