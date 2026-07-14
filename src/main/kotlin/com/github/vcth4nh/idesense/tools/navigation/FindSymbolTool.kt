package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScope
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScopeResolver
import com.github.vcth4nh.idesense.handlers.PopupFaithfulSymbolSearch
import com.github.vcth4nh.idesense.handlers.SymbolData
import com.github.vcth4nh.idesense.handlers.SymbolDataConverter
import com.github.vcth4nh.idesense.server.PaginationService
import com.github.vcth4nh.idesense.server.ProjectResolver
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.FindSymbolResult
import com.github.vcth4nh.idesense.tools.models.SymbolMatch
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.project.Project
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.util.PsiModificationTracker
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.jsonPrimitive

/**
 * Tool for searching code symbols by name.
 *
 * Works in any supported JetBrains IDE. Drives the headless Go to Symbol popup stack via
 * [PopupFaithfulSymbolSearch], so matching and ranking follow IntelliJ's own Go to Symbol popup.
 */
class FindSymbolTool : AbstractMcpTool() {

    companion object {
        private val LOG = logger<FindSymbolTool>()
        private const val DEFAULT_PAGE_SIZE = 25
        private const val MAX_PAGE_SIZE = PaginationService.MAX_PAGE_SIZE
    }

    override val name = ToolNames.FIND_SYMBOL

    override val description = """
        Search for any code symbol (classes, methods, fields, functions) by name using the IDE's
        Go to Symbol popup (Ctrl+Alt+Shift+N). Use when you need symbols beyond classes — prefer
        ide_find_class when you only need class-like types (faster). Supports qualified queries
        like "BasicSolver.run".

        Exact match by default (case-insensitive). Set fuzzySearch=true for camelCase + substring
        matching. Note: when methods share a name through inheritance, results collapse to the topmost
        super — use ide_find_implementations for the full override set.

        Returns: symbols with qualified names, file paths, line/column numbers, and kind. Paginated
        — pass the returned cursor for the next page.

        Gotchas: disabled by default — must be enabled in Settings → Tools → IdeSense. Requires
        smart mode.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .stringProperty(ParamNames.QUERY, "Symbol name pattern, including qualified queries (e.g. \"BasicSolver.run\"). Required for fresh search; ignored when cursor is provided.")
        .scopeProperty("Search scope. Default: project_files.")
        .stringProperty(ParamNames.LANGUAGE, "Filter results by language (e.g., \"Kotlin\", \"Java\", \"Python\"). Case-insensitive. Optional.")
        .booleanProperty(ParamNames.FUZZY_SEARCH, "When true, use the IDE's Go to Symbol fuzzy matching (camelCase + substring). When false (default), match the symbol name exactly, case-insensitively. Default: false.")
        .intProperty(ParamNames.LIMIT, "Maximum results per page (deprecated, use pageSize). Default: $DEFAULT_PAGE_SIZE, max: $MAX_PAGE_SIZE.")
        .stringProperty("cursor", "Pagination cursor from a previous response. When provided, returns the next page of results. Search parameters are ignored; project_path and pageSize may still be provided.")
        .intProperty("pageSize", "Results per page. Default: $DEFAULT_PAGE_SIZE, max: $MAX_PAGE_SIZE.")
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val cursor = arguments["cursor"]?.jsonPrimitive?.content
        if (cursor != null) {
            val pageSize = resolveExplicitPageSize(arguments, aliases = arrayOf("limit"))
            return buildPaginatedResult<SymbolMatch, FindSymbolResult>(getPageFromCache(cursor, pageSize, project)) { items, page ->
                FindSymbolResult(
                    symbols = items,
                    query = page.metadata["query"] ?: "",
                    nextCursor = page.nextCursor,
                    hasMore = page.hasMore,
                    totalCollected = page.totalCollected,
                    offset = page.offset,
                    pageSize = page.pageSize,
                    stale = page.stale
                )
            }
        }

        val query = arguments[ParamNames.QUERY]?.jsonPrimitive?.content
            ?: return createMissingRequiredParamError(ParamNames.QUERY)
        val scope = try {
            BuiltInSearchScopeResolver.parse(arguments, BuiltInSearchScope.PROJECT_FILES)
        } catch (_: IllegalArgumentException) {
            return createInvalidScopeError(arguments[ParamNames.SCOPE], BuiltInSearchScope.supportedWireValues())
        } catch (_: IllegalStateException) {
            return createInvalidScopeError(arguments[ParamNames.SCOPE], BuiltInSearchScope.supportedWireValues())
        }
        val languageFilter = arguments[ParamNames.LANGUAGE]?.jsonPrimitive?.content
        val fuzzySearch = arguments[ParamNames.FUZZY_SEARCH]?.jsonPrimitive?.booleanOrNull ?: false
        val pageSize = resolvePageSize(arguments, DEFAULT_PAGE_SIZE, aliases = arrayOf("limit"))
        val collectLimit = maxOf(PaginationService.DEFAULT_OVERCOLLECT, pageSize)

        if (query.isBlank()) {
            return createErrorResult("Query cannot be empty")
        }

        requireSmartMode(project)

        val token = suspendingReadAction {
            val searchScope = BuiltInSearchScopeResolver.resolveGlobalScope(project, scope)
            val nativeLanguageFilter = languageFilter?.takeIf { it.isNotBlank() }?.let { setOf(it) }
            val symbols = searchAndConvertSymbols(
                project = project,
                pattern = query,
                scope = searchScope,
                limit = collectLimit,
                languageFilter = nativeLanguageFilter,
                fuzzySearch = fuzzySearch
            )

            val matches = symbols.map { it.toSymbolMatch() }

            val searchExtender: suspend (Set<String>, Int) -> List<PaginationService.SerializedResult> = { seenKeys, limit ->
                suspendingReadAction {
                    extendSearchSymbols(project, query, scope, languageFilter, fuzzySearch, seenKeys, limit)
                }
            }

            val serializedResults = matches.map { sym ->
                PaginationService.SerializedResult(
                    key = sym.paginationKey(),
                    data = json.encodeToJsonElement(sym)
                )
            }

            val paginationService = ApplicationManager.getApplication().getService(PaginationService::class.java)
            paginationService.createCursor(
                toolName = name,
                results = serializedResults,
                seenKeys = serializedResults.map { it.key }.toSet(),
                searchExtender = searchExtender,
                psiModCount = PsiModificationTracker.getInstance(project).modificationCount,
                projectBasePath = ProjectResolver.normalizePath(project.basePath ?: ""),
                metadata = mapOf("query" to query)
            )
        }

        return buildPaginatedResult<SymbolMatch, FindSymbolResult>(getPageFromCache(token, pageSize, project)) { items, page ->
            FindSymbolResult(
                symbols = items,
                query = page.metadata["query"] ?: "",
                nextCursor = page.nextCursor,
                hasMore = page.hasMore,
                totalCollected = page.totalCollected,
                offset = page.offset,
                pageSize = page.pageSize,
                stale = page.stale
            )
        }
    }

    /**
     * Drive the headless Go to Symbol popup stack and convert results to [SymbolData].
     *
     * Owns the over-fetch loop: [PopupFaithfulSymbolSearch] returns NavigationItems, some of
     * which get filtered out by [SymbolDataConverter] (scope mismatch, language mismatch,
     * dedup, and (when fuzzySearch is false) the exact-name filter). When that happens, we
     * re-request with a larger limit, doubling each iteration up
     * to a cap of `max(limit * 8, limit + 200)`, until we have enough results, the popup
     * exhausts, or we hit the cap.
     *
     * Failures from the popup search log at WARN with diagnostic context (pattern, scope,
     * popupLimit) and propagate to the caller. [ProcessCanceledException] propagates without
     * logging — IDE cancellation is not an error.
     */
    private fun searchAndConvertSymbols(
        project: Project,
        pattern: String,
        scope: GlobalSearchScope,
        limit: Int,
        languageFilter: Set<String>?,
        fuzzySearch: Boolean
    ): List<SymbolData> {
        if (pattern.isBlank()) return emptyList()
        var popupLimit = limit
        val popupLimitCap = maxOf(limit * 8, limit + 200)
        while (true) {
            val popupResults = try {
                PopupFaithfulSymbolSearch.search(project, pattern, scope, popupLimit)
            } catch (e: ProcessCanceledException) {
                throw e
            } catch (e: Exception) {
                LOG.warn(
                    "Symbol search failed: pattern='$pattern' scope=${scope.javaClass.simpleName} popupLimit=$popupLimit",
                    e
                )
                throw e
            }
            val results = popupResults.candidates
                .mapNotNull { SymbolDataConverter.convert(it.item, project, scope, languageFilter) }
                .filter { fuzzySearch || it.name.equals(popupResults.localPattern, ignoreCase = true) }
                .distinctBy { "${it.file}:${it.line}:${it.column}:${it.name}" }
            if (results.size >= limit ||
                popupResults.candidates.size < popupLimit ||
                popupLimit >= popupLimitCap
            ) {
                return results.take(limit)
            }
            popupLimit = minOf(popupLimitCap, popupLimit * 2)
        }
    }

    /**
     * Re-executes the popup-backed search to collect more results beyond the initial cache.
     * Skips already-seen keys in the caller's cache — O(total_results) per extension because
     * the popup APIs don't support offset-based iteration.
     */
    private fun extendSearchSymbols(
        project: Project,
        query: String,
        scope: BuiltInSearchScope,
        languageFilter: String?,
        fuzzySearch: Boolean,
        seenKeys: Set<String>,
        limit: Int
    ): List<PaginationService.SerializedResult> {
        val searchScope = BuiltInSearchScopeResolver.resolveGlobalScope(project, scope)
        val nativeLanguageFilter = languageFilter?.takeIf { it.isNotBlank() }?.let { setOf(it) }
        val symbols = searchAndConvertSymbols(
            project = project,
            pattern = query,
            scope = searchScope,
            limit = limit + seenKeys.size,
            languageFilter = nativeLanguageFilter,
            fuzzySearch = fuzzySearch
        )

        return symbols.asSequence()
            .map { it.toSymbolMatch() }
            .filter { sym -> sym.paginationKey() !in seenKeys }
            .take(limit)
            .map { sym ->
                PaginationService.SerializedResult(
                    key = sym.paginationKey(),
                    data = json.encodeToJsonElement(sym)
                )
            }
            .toList()
    }

    private fun SymbolData.toSymbolMatch(): SymbolMatch = SymbolMatch(
        name = name,
        qualifiedName = qualifiedName,
        kind = kind,
        file = file,
        line = line,
        column = column,
    )

    private fun SymbolMatch.paginationKey(): String = "$file:$line:$column:$name"
}
