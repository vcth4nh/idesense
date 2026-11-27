package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.handlers.createFilteredScope
import com.github.vcth4nh.idesense.server.PaginationService
import com.github.vcth4nh.idesense.server.ProjectResolver
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.SearchTextResult
import com.github.vcth4nh.idesense.tools.models.TextMatch
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.github.vcth4nh.idesense.util.LinePreview
import com.intellij.find.FindManager
import com.intellij.find.FindModel
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.search.PsiSearchHelper
import com.intellij.psi.search.TextOccurenceProcessor
import com.intellij.psi.search.UsageSearchContext
import com.intellij.psi.util.PsiModificationTracker
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive

/**
 * Text search using IDE's word index.
 *
 * Uses a pre-built word index for exact word matches.
 *
 * Supports context filtering: search only in code, comments, or string literals.
 */
@Suppress("unused")
class SearchTextTool : AbstractMcpTool() {

    companion object {
        private const val DEFAULT_PAGE_SIZE = 100
        private const val MAX_PAGE_SIZE = PaginationService.MAX_PAGE_SIZE

        /**
         * The occurrence mask for the word index: no context filter, for each `context` value.
         * The index and the `contextType` label are two classifications. The index puts plain
         * text under IN_PLAIN_TEXT, HTML text under IN_PLAIN_TEXT | IN_FOREIGN_LANGUAGES and a
         * JSON string under IN_CODE. So a search with the mask of one context loses matches that
         * have the label of that context (#133). The label alone selects the matches.
         */
        private const val WORD_INDEX_CONTEXT: Short = UsageSearchContext.ANY

        /**
         * The search walks no injected language fragment. A word inside a fragment is text of
         * the host file, so the search reports it once, in the host file. The walk of the
         * fragments gave a second match, with the path and a line of the fragment (#184).
         */
        private const val PROCESS_INJECTED_PSI = false

        /** The `contextType` label that the `context` value keeps. Null keeps each label. */
        internal fun requestedContextType(context: String): String? = when (context.lowercase()) {
            "code" -> "CODE"
            "comments" -> "COMMENT"
            "strings" -> "STRING_LITERAL"
            else -> null
        }
    }

    override val name = ToolNames.SEARCH_TEXT

    override val description = """
        Search for an exact word across the project using the IDE's pre-built word index — O(1) lookup,
        much faster than file scanning. Use for quick literal sweeps when you don't need semantic
        resolution. Prefer ide_find_usages when you need semantic accuracy (aliases, overrides,
        generics); prefer Grep/external tools when you need regex.

        Supports context filtering: search only in code, comments, or string literals.

        Returns: file paths, 1-based line/column, context snippets, and context type (CODE,
        COMMENT, STRING_LITERAL). Paginated — pass the returned cursor for the next page.

        Gotchas: exact word match only — no wildcards or regex. Requires smart mode.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .stringProperty(ParamNames.QUERY, "Exact word to search for (no wildcards or regex). Required for fresh search; ignored when cursor is provided.")
        .enumProperty(ParamNames.CONTEXT, "Where to search: \"comments\" (a comment), \"strings\" (a string literal, or text that the IDE highlights as a string, for example each line of a Markdown code fence), \"code\" (each other match, also in a file that is no program source), \"all\". Default: \"all\".", listOf("code", "comments", "strings", "all"))
        .booleanProperty(ParamNames.CASE_SENSITIVE, "Case sensitive search. Default: true.")
        .intProperty(ParamNames.LIMIT, "Maximum results per page (deprecated, use pageSize). Default: $DEFAULT_PAGE_SIZE, max: $MAX_PAGE_SIZE.")
        .stringProperty("cursor", "Pagination cursor from a previous response. When provided, returns the next page of results. Search parameters are ignored; project_path and pageSize may still be provided.")
        .intProperty("pageSize", "Results per page. Default: $DEFAULT_PAGE_SIZE, max: $MAX_PAGE_SIZE.")
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val cursor = arguments["cursor"]?.jsonPrimitive?.content
        if (cursor != null) {
            val pageSize = resolveExplicitPageSize(arguments, aliases = arrayOf("limit"))
            return buildPaginatedResult<TextMatch, SearchTextResult>(getPageFromCache(cursor, pageSize, project)) { items, page ->
                SearchTextResult(
                    matches = items,
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
        val contextStr = arguments[ParamNames.CONTEXT]?.jsonPrimitive?.content ?: "all"
        val caseSensitive = arguments[ParamNames.CASE_SENSITIVE]?.jsonPrimitive?.boolean ?: true
        val pageSize = resolvePageSize(arguments, DEFAULT_PAGE_SIZE, aliases = arrayOf("limit"))
        val collectLimit = maxOf(PaginationService.DEFAULT_OVERCOLLECT, pageSize)

        if (query.isBlank()) {
            return createErrorResult("Query cannot be empty")
        }

        val requestedType = requestedContextType(contextStr)

        requireSmartMode(project)

        val cursorToken = suspendingReadAction {
            val scope = createFilteredScope(project)
            val matches = searchText(project, query, scope, requestedType, caseSensitive, collectLimit)

            val searchExtender: suspend (Set<String>, Int) -> List<PaginationService.SerializedResult> = extender@{ seenKeys, limit ->
                suspendingReadAction {
                    extendSearchText(project, query, requestedType, caseSensitive, seenKeys, limit)
                }
            }

            val serializedResults = matches.map { match ->
                PaginationService.SerializedResult(
                    key = "${match.file}:${match.line}",
                    data = json.encodeToJsonElement(match)
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

        return buildPaginatedResult<TextMatch, SearchTextResult>(getPageFromCache(cursorToken, pageSize, project)) { items, page ->
            SearchTextResult(
                matches = items,
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

    private fun searchText(
        project: Project,
        word: String,
        scope: com.intellij.psi.search.GlobalSearchScope,
        requestedType: String?,
        caseSensitive: Boolean,
        limit: Int
    ): List<TextMatch> {
        val results = ConcurrentLinkedQueue<TextMatch>()
        val seenLines = ConcurrentHashMap.newKeySet<String>()
        val lastOccurrenceByFile = ConcurrentHashMap<PsiFile, Int>()
        val count = AtomicInteger(0)
        val helper = PsiSearchHelper.getInstance(project)
        val contexts = FindInFilesContexts(project, word, caseSensitive)

        val processor = TextOccurenceProcessor { element, offsetInElement ->
            if (count.get() >= limit) {
                return@TextOccurenceProcessor false
            }
            val occurrence = element.textRange.startOffset + offsetInElement
            val file = element.containingFile ?: return@TextOccurenceProcessor true
            if (lastOccurrenceByFile.put(file, occurrence) == occurrence) {
                // An ancestor call for the occurrence before (see convertToTextMatch).
                return@TextOccurenceProcessor true
            }

            val match = convertToTextMatch(project, element, occurrence, word.length, requestedType, contexts)
            if (match != null) {
                val lineKey = "${match.file}:${match.line}"
                if (seenLines.add(lineKey)) {
                    val slot = count.incrementAndGet()
                    if (slot <= limit) {
                        results.add(match)
                    }
                    slot < limit
                } else {
                    true
                }
            } else {
                true
            }
        }

        helper.processElementsWithWord(
            processor,
            scope,
            word,
            WORD_INDEX_CONTEXT,
            caseSensitive,
            PROCESS_INJECTED_PSI
        )

        return results.toList()
    }

    /**
     * Re-executes the search to collect more results beyond the initial cache.
     * This re-scans from the beginning, skipping already-seen keys — O(total_results) per extension.
     * This is unavoidable: IntelliJ's search APIs (ReferencesSearch, PsiSearchHelper, etc.)
     * don't support offset-based iteration or resumption.
     */
    private fun extendSearchText(
        project: Project,
        word: String,
        requestedType: String?,
        caseSensitive: Boolean,
        seenKeys: Set<String>,
        limit: Int
    ): List<PaginationService.SerializedResult> {
        val scope = createFilteredScope(project)
        val newResults = ConcurrentLinkedQueue<PaginationService.SerializedResult>()
        val seenLines = ConcurrentHashMap.newKeySet<String>()
        seenLines.addAll(seenKeys)
        val lastOccurrenceByFile = ConcurrentHashMap<PsiFile, Int>()
        val count = AtomicInteger(0)
        val helper = PsiSearchHelper.getInstance(project)
        val contexts = FindInFilesContexts(project, word, caseSensitive)

        val processor = TextOccurenceProcessor { element, offsetInElement ->
            if (count.get() >= limit) {
                return@TextOccurenceProcessor false
            }
            val occurrence = element.textRange.startOffset + offsetInElement
            val file = element.containingFile ?: return@TextOccurenceProcessor true
            if (lastOccurrenceByFile.put(file, occurrence) == occurrence) {
                // An ancestor call for the occurrence before (see convertToTextMatch).
                return@TextOccurenceProcessor true
            }

            val match = convertToTextMatch(project, element, occurrence, word.length, requestedType, contexts)
            if (match != null) {
                val lineKey = "${match.file}:${match.line}"
                if (seenLines.add(lineKey)) {
                    val slot = count.incrementAndGet()
                    if (slot <= limit) {
                        newResults.add(PaginationService.SerializedResult(
                            key = lineKey,
                            data = json.encodeToJsonElement(match)
                        ))
                    }
                    slot < limit
                } else {
                    true
                }
            } else {
                true
            }
        }

        helper.processElementsWithWord(
            processor,
            scope,
            word,
            WORD_INDEX_CONTEXT,
            caseSensitive,
            PROCESS_INJECTED_PSI
        )

        return newResults.toList()
    }

    /**
     * Converts one word occurrence to a match. [occurrence] is the occurrence's offset in the file.
     * The platform calls the occurrence processor once per PSI ancestor of an occurrence, innermost
     * first; the callers pass only that first call, because an ancestor would report the context
     * type of a larger element (for example CODE for a word inside a comment). The calls for one
     * occurrence come one after the other, and one job processes each file
     * (`LowLevelSearchUtil.processTreeUp`, `PsiSearchHelperImpl.processPsiFileRoots`), so the
     * callers keep only the last occurrence of each file to find the ancestor calls. Line, column
     * and context come from the occurrence itself, not from the start of [element].
     */
    private fun convertToTextMatch(
        project: Project,
        element: PsiElement,
        occurrence: Int,
        wordLength: Int,
        requestedType: String?,
        contexts: FindInFilesContexts
    ): TextMatch? {
        val containingFile = element.containingFile ?: return null
        val virtualFile = containingFile.virtualFile ?: return null
        val relativePath = getRelativePath(project, virtualFile)

        val document = PsiDocumentManager.getInstance(project).getDocument(containingFile) ?: return null
        if (occurrence > document.textLength) return null
        val lineNumber = document.getLineNumber(occurrence)
        val columnNumber = occurrence - document.getLineStartOffset(lineNumber)

        val contextType = contexts.label(virtualFile, document.charsSequence, occurrence)

        // The context filter. The word index search has none (see WORD_INDEX_CONTEXT).
        if (requestedType != null && contextType != requestedType) {
            return null
        }

        return TextMatch(
            file = relativePath,
            line = lineNumber + 1,
            column = columnNumber + 1,
            context = LinePreview.ofLine(document, lineNumber, columnNumber, wordLength),
            contextType = contextType
        )
    }
}

/**
 * The `contextType` labels of one search, from the per-file matcher of Find in Files
 * ([FindManager.findString] with a [FindModel.SearchContext], as `FindInProjectUtil` calls it).
 * "In Comments" and "In String Literals" are two runs of the matcher. "Except Comments and
 * String Literals" keeps each occurrence that these two runs do not find
 * (`FindExceptCommentsOrLiteralsData`), so the third label is the rest: CODE (#144). A match that
 * both runs find gets COMMENT: a match has one label, and the IDE lists it in both filters.
 *
 * The matcher walks the highlighting lexer of the file. One run for each of the two contexts
 * finds all occurrences of a file, and the result holds for each match of the file.
 */
private class FindInFilesContexts(project: Project, word: String, caseSensitive: Boolean) {
    private val findManager = FindManager.getInstance(project)
    private val comments = model(word, caseSensitive, FindModel.SearchContext.IN_COMMENTS)
    private val strings = model(word, caseSensitive, FindModel.SearchContext.IN_STRING_LITERALS)
    private val startsByFile = ConcurrentHashMap<VirtualFile, Pair<Set<Int>, Set<Int>>>()

    fun label(file: VirtualFile, text: CharSequence, occurrence: Int): String {
        val (commentStarts, stringStarts) = startsByFile.getOrPut(file) {
            starts(text, comments, file) to starts(text, strings, file)
        }
        return when (occurrence) {
            in commentStarts -> "COMMENT"
            in stringStarts -> "STRING_LITERAL"
            else -> "CODE"
        }
    }

    /** The loop of `FindInProjectUtil.processSomeOccurrencesInFile`. */
    private fun starts(text: CharSequence, model: FindModel, file: VirtualFile): Set<Int> {
        val starts = HashSet<Int>()
        var offset = 0
        while (offset < text.length) {
            val result = findManager.findString(text, offset, model, file)
            if (!result.isStringFound) break
            starts.add(result.startOffset)
            val previous = offset
            offset = result.endOffset
            if (previous == offset || offset == result.startOffset) offset++
        }
        return starts
    }

    private companion object {
        // No "Words" option: the word index already gave the occurrence, and the label is the
        // token class of the occurrence.
        fun model(word: String, caseSensitive: Boolean, context: FindModel.SearchContext) = FindModel().apply {
            stringToFind = word
            isCaseSensitive = caseSensitive
            searchContext = context
        }
    }
}
