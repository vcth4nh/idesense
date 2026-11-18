package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.ErrorMessages
import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.constants.UsageMatch
import com.github.vcth4nh.idesense.constants.UsageTypes
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScope
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScopeResolver
import com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch
import com.github.vcth4nh.idesense.handlers.UsageHit
import com.github.vcth4nh.idesense.server.PaginationService
import com.github.vcth4nh.idesense.server.McpErrors
import com.github.vcth4nh.idesense.server.ProjectResolver
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.SymbolAnchor
import com.github.vcth4nh.idesense.tools.SymbolAnchorResolver
import com.github.vcth4nh.idesense.tools.SymbolResolution
import com.github.vcth4nh.idesense.tools.models.FindUsagesResult
import com.github.vcth4nh.idesense.tools.models.SymbolCandidatesResult
import com.github.vcth4nh.idesense.tools.models.UsageLocation
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.github.vcth4nh.idesense.util.LinePreview
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.PsiUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiComment
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.SmartPointerManager
import com.intellij.psi.util.PsiModificationTracker
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.util.Processor
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.jsonPrimitive

class FindUsagesTool : AbstractMcpTool() {

    companion object {
        private val LOG = logger<FindUsagesTool>()
        private const val DEFAULT_MAX_RESULTS = 100
        private const val MAX_PAGE_SIZE = PaginationService.MAX_PAGE_SIZE

        internal fun searchInfrastructureErrorMessage(error: Throwable): String {
            val detail = error.message?.takeIf { it.isNotBlank() }?.let { ": $it" } ?: ""
            return "Reference search failed due to IDE/plugin API incompatibility (${error::class.simpleName}$detail). " +
                "Try ide_search_text as a fallback and check plugin compatibility against the current IDE build."
        }

        // Shared with ide_explain_symbol so both report the same usageType vocabulary.
        internal fun classifyUsage(element: PsiElement): String {
            val parent = element.parent
            val parentClass = parent?.javaClass?.simpleName ?: "Unknown"

            return when {
                // The rule of the platform's "Usage in comments" group (UsageTypeGroupingRule), all languages (#132).
                PsiTreeUtil.getParentOfType(element, PsiComment::class.java, false) != null -> UsageTypes.COMMENT
                parentClass.contains("MethodCall") -> UsageTypes.METHOD_CALL
                parentClass.contains("Reference") -> UsageTypes.REFERENCE
                parentClass.contains("Field") -> UsageTypes.FIELD_ACCESS
                parentClass.contains("Import") -> UsageTypes.IMPORT
                parentClass.contains("Parameter") -> UsageTypes.PARAMETER
                parentClass.contains("Variable") -> UsageTypes.VARIABLE
                else -> UsageTypes.REFERENCE
            }
        }

        /** The printed name of a declaration in a note: its qualified name, else its name. Shared with ide_explain_symbol. */
        internal fun declarationName(declaration: PsiElement): String =
            QualifiedNameUtil.getQualifiedName(declaration) ?: (declaration as? PsiNamedElement)?.name ?: "unknown"
    }

    override val name = ToolNames.FIND_USAGES

    override val description = """
        Find references to a symbol in the chosen scope — semantic, not text. Prefer this over
        ide_search_text for usages: it resolves through imports, aliases, overrides, and generics
        that text search misses. Anchor on a symbol name or qualified name (symbol), or put the
        caret on the symbol name (file + line + column).

        Returns: file paths, 1-based positions, context snippets, and reference kinds
        (METHOD_CALL, FIELD_ACCESS, IMPORT, PARAMETER, VARIABLE, REFERENCE, COMMENT). Paginated (each cursor collects up to an internal cap; the count is a collected count, not a guaranteed whole-project total) — pass the returned cursor for the next page.
        For a Go, Java, JavaScript, Kotlin, PHP, Python, Rust or TypeScript member that overrides or implements a base declaration, the result also holds the usages of that base declaration, and a notes list on the first page names it. For a PHP method, the result also holds the usages of each method that overrides or implements it, and the notes list names these methods. A usage can have match: BASE (it refers to a base declaration; the call can run this symbol or another implementation), match: OVERRIDE (it refers to a PHP method that overrides or implements this symbol; it is a call on a value whose type has that method) or match: DYNAMIC (only the name matches; the type of the receiver is not known). A usage with no match refers to the symbol itself. The notes list also names each kind of usage that the result leaves out, with the count (for example a Go composite literal key that names a struct field with the same name as the type, or a reference to a PHP class through ${'$'}this, self or static inside the class), and each base method that the search does not search (a method of the Python class object).

        Gotchas: requires smart mode (not indexing). If the language's find-usages handler degrades
        mid-search, a warnings list on the first page flags the partial coverage. For a quick literal
        word sweep use ide_search_text; for "who calls this" as a tree use ide_call_hierarchy.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .stringProperty(
            ParamNames.SYMBOL,
            "Symbol name or qualified name (e.g. \"UserService\", \"demo.UserService\", \"UserService.authenticate\"); an overloaded method needs its parameter list to select one overload (e.g. \"demo.Quirks#parse(java.lang.String)\"), otherwise the overloads come back as candidates. Mutually exclusive with file/line/column; ignored when cursor is provided."
        )
        .file(required = false, description = "Project-relative file path, or a dependency/library absolute path or jar:// URL previously returned by the plugin. Use with line and column; mutually exclusive with symbol. Ignored when cursor is provided.")
        .lineAndColumn(required = false)
        .scopeProperty()
        .intProperty("maxResults", "Maximum results per page (deprecated, use pageSize). Default: $DEFAULT_MAX_RESULTS, max: $MAX_PAGE_SIZE.")
        .stringProperty("cursor", "Pagination cursor from a previous response. When provided, returns the next page of results. Search parameters are ignored; project_path and pageSize may still be provided.")
        .intProperty("pageSize", "Results per page. Default: $DEFAULT_MAX_RESULTS, max: $MAX_PAGE_SIZE.")
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val cursor = arguments["cursor"]?.jsonPrimitive?.content
        if (cursor != null) {
            val pageSize = resolveExplicitPageSize(arguments, aliases = arrayOf("maxResults"))
            return buildPaginatedResult<UsageLocation, FindUsagesResult>(getPageFromCache(cursor, pageSize, project)) { items, page ->
                FindUsagesResult(
                    usages = items,
                    truncated = page.hasMore,
                    nextCursor = page.nextCursor,
                    hasMore = page.hasMore,
                    totalCollected = page.totalCollected,
                    offset = page.offset,
                    pageSize = page.pageSize,
                    stale = page.stale
                )
            }
        }

        val pageSize = resolvePageSize(arguments, DEFAULT_MAX_RESULTS, aliases = arrayOf("maxResults"))
        val collectLimit = maxOf(PaginationService.DEFAULT_OVERCOLLECT, pageSize)
        val scope = try {
            BuiltInSearchScopeResolver.parse(arguments, BuiltInSearchScope.PROJECT_FILES)
        } catch (_: IllegalArgumentException) {
            return createInvalidScopeError(arguments[ParamNames.SCOPE], BuiltInSearchScope.supportedWireValues())
        } catch (_: IllegalStateException) {
            return createInvalidScopeError(arguments[ParamNames.SCOPE], BuiltInSearchScope.supportedWireValues())
        }
        scopeMatchesNoFilesError(project, scope)?.let { return it }
        val anchor = SymbolAnchor.parse(arguments)
        if (anchor is SymbolAnchor.Invalid) {
            return createStructuredErrorResult(McpErrors.generic("invalid_arguments", anchor.message))
        }

        requireSmartMode(project)

        // Filled inside the read action; read after it completes. Non-empty when a
        // FindUsagesHandler stage threw and the search degraded (#81) — surfaced on
        // the first page of a fresh search.
        val handlerWarnings = mutableListOf<String>()
        // Filled the same way: the notes about the base and overriding declarations that the
        // search also covers (#171), the base methods that it does not search and the usages
        // that it leaves out, first page only.
        val handlerNotes = mutableListOf<String>()
        val cursorToken = suspendingReadAction {
            val targetElement = when (anchor) {
                is SymbolAnchor.BySymbol -> when (val resolution = SymbolAnchorResolver.resolve(project, anchor.symbol)) {
                    is SymbolResolution.Resolved -> resolution.element
                    is SymbolResolution.Ambiguous -> return@suspendingReadAction null to createJsonResult(
                        SymbolCandidatesResult(
                            candidates = resolution.candidates,
                            message = "Ambiguous symbol '${anchor.symbol}': ${resolution.matchCount}. Pass a qualified name or a file/line/column position.",
                        )
                    )
                    SymbolResolution.NotFound -> return@suspendingReadAction null to createErrorResult(
                        "Symbol not found in project files: '${anchor.symbol}'. Try a qualified name, or ide_find_symbol with fuzzySearch=true."
                    )
                }
                is SymbolAnchor.ByPosition -> {
                    val element = resolveElementFromArguments(project, arguments, allowLibraryFilesForPosition = true).getOrElse {
                        return@suspendingReadAction null to createErrorResult(it.message ?: ErrorMessages.COULD_NOT_RESOLVE_SYMBOL)
                    }
                    // Symbol-based resolution returns the declaration directly (PsiNamedElement).
                    // Position-based resolution returns a leaf token that needs reference resolution.
                    // We deliberately use resolveReferenceTarget (not resolveTargetElement) — the
                    // GotoDeclarationHandler step would redirect e.g. `new Foo()` cursors to the
                    // constructor / __init__ / class-declaration depending on language, narrowing the
                    // search anchor and dropping legitimate references (type annotations, variable
                    // assignments, etc.). This matches the IDE's Find Usages action (Alt+F7), which
                    // uses TargetElementUtil.FIND_TARGET_FLAGS — those flags do not invoke
                    // GotoDeclarationHandler extensions.
                    element as? PsiNamedElement
                        ?: (PsiUtils.resolveReferenceTarget(element)
                            ?: return@suspendingReadAction null to createErrorResult(
                                ErrorMessages.NO_NAMED_ELEMENT + "." + caretHint(element, arguments)
                            ))
                }
                is SymbolAnchor.Invalid -> error("unreachable: Invalid anchor handled above")
            }

            val usages = ConcurrentLinkedQueue<UsageLocation>()
            val totalFound = AtomicInteger(0)
            val totalCountLimit = collectLimit * 10
            val searchScope = BuiltInSearchScopeResolver.resolveGlobalScope(project, scope)
            val seenLocationKeys = ConcurrentHashMap.newKeySet<String>()

            val collectRef: (UsageHit) -> Boolean = { hit ->
                ProgressManager.checkCanceled()
                val refElement = hit.element
                if (!refElement.isValid) {
                    true
                } else {
                    val refFile = refElement.containingFile?.virtualFile
                    val document = refElement.containingFile?.let {
                        PsiDocumentManager.getInstance(project).getDocument(it)
                    }
                    if (refFile != null && document != null && searchScope.contains(refFile)) {
                        val lineNumber = document.getLineNumber(hit.offset) + 1
                        val columnNumber = hit.offset -
                            document.getLineStartOffset(lineNumber - 1) + 1
                        val key = "${getRelativePath(project, refFile)}:$lineNumber:$columnNumber"

                        if (seenLocationKeys.add(key)) {
                            val total = totalFound.incrementAndGet()
                            if (total <= collectLimit) {
                                usages.add(UsageLocation(
                                    file = getRelativePath(project, refFile),
                                    line = lineNumber,
                                    column = columnNumber,
                                    preview = LinePreview.ofLine(document, lineNumber - 1, columnNumber - 1),
                                    usageType = classifyUsage(refElement),
                                    enclosingScope = PsiUtils.getEnclosingScope(refElement),
                                    match = hit.match
                                ))
                            }
                            total < totalCountLimit
                        } else {
                            true
                        }
                    } else {
                        true
                    }
                }
            }

            val baseDeclarations = mutableListOf<PsiElement>()
            val overridingDeclarations = mutableListOf<PsiElement>()
            val skippedBases = mutableListOf<PsiElement>()
            val dropped = LinkedHashMap<String, Int>()
            try {
                FindUsagesHandlerSearch.processReferences(
                    project = project,
                    element = targetElement,
                    scope = searchScope,
                    processor = Processor { hit -> collectRef(hit) },
                    warnings = handlerWarnings,
                    baseDeclarations = baseDeclarations,
                    overridingDeclarations = overridingDeclarations,
                    skippedBases = skippedBases,
                    dropped = dropped
                )
            } catch (e: LinkageError) {
                LOG.warn("Reference search failed for ${targetElement.javaClass.name}", e)
                return@suspendingReadAction null to createErrorResult(searchInfrastructureErrorMessage(e))
            }

            val usagesList = usages.toList()
                .distinctBy { "${it.file}:${it.line}:${it.column}" }

            val symbolName = (targetElement as? PsiNamedElement)?.name ?: "the symbol"
            val cut = totalFound.get() > usagesList.size
            if (baseDeclarations.isNotEmpty()) {
                handlerNotes.add(BaseDeclarationsNote.build(
                    symbolName = symbolName,
                    bases = baseDeclarations.map { baseDeclarationRef(project, it) },
                    baseUsages = usagesList.count { it.match == UsageMatch.BASE },
                    collected = usagesList.size,
                    cut = cut
                ))
            }
            OverridingDeclarationsNote.build(
                symbolName = symbolName,
                overrides = overridingDeclarations.map { baseDeclarationRef(project, it) },
                overrideUsages = usagesList.count { it.match == UsageMatch.OVERRIDE },
                collected = usagesList.size,
                cut = cut
            )?.let(handlerNotes::add)
            SkippedBasesNote.build(skippedBases.map(::declarationName))?.let(handlerNotes::add)
            // The search stops when the collector returns false: at totalCountLimit usages.
            handlerNotes.addAll(DroppedUsagesNote.build(dropped, cut = totalFound.get() >= totalCountLimit))

            val smartPointer = SmartPointerManager.getInstance(project).createSmartPsiElementPointer(targetElement)

            val searchExtender: suspend (Set<String>, Int) -> List<PaginationService.SerializedResult> = { seenKeys, limit ->
                suspendingReadAction {
                    val el = smartPointer.element
                        ?: throw IllegalStateException("Target element no longer valid")
                    extendFindUsages(project, el, seenKeys, limit, scope)
                }
            }

            val serializedResults = usagesList.map { usage ->
                PaginationService.SerializedResult(
                    key = "${usage.file}:${usage.line}:${usage.column}",
                    data = json.encodeToJsonElement(usage)
                )
            }

            val paginationService = ApplicationManager.getApplication().getService(PaginationService::class.java)
            val token = paginationService.createCursor(
                toolName = name,
                results = serializedResults,
                seenKeys = serializedResults.map { it.key }.toSet(),
                searchExtender = searchExtender,
                psiModCount = PsiModificationTracker.getInstance(project).modificationCount,
                projectBasePath = ProjectResolver.normalizePath(project.basePath ?: "")
            )

            token to null
        }

        val (token, errorResult) = cursorToken
        if (errorResult != null) return errorResult

        return buildPaginatedResult<UsageLocation, FindUsagesResult>(getPageFromCache(token!!, pageSize, project)) { items, page ->
            FindUsagesResult(
                usages = items,
                truncated = page.hasMore,
                nextCursor = page.nextCursor,
                hasMore = page.hasMore,
                totalCollected = page.totalCollected,
                offset = page.offset,
                pageSize = page.pageSize,
                stale = page.stale,
                warnings = handlerWarnings.takeIf { it.isNotEmpty() },
                notes = handlerNotes.takeIf { it.isNotEmpty() }
            )
        }
    }

    /**
     * The name and the place of [base] for [BaseDeclarationsNote] and [OverridingDeclarationsNote]:
     * `path:line:column` in a project file, `file name, library` in another file, no place when
     * [base] has no file.
     */
    private fun baseDeclarationRef(project: Project, base: PsiElement): BaseDeclarationRef {
        val name = declarationName(base)
        val psiFile = base.containingFile
        val file = psiFile?.virtualFile ?: return BaseDeclarationRef(name, null)
        if (!ProjectUtils.isProjectFile(project, file)) return BaseDeclarationRef(name, "${file.name}, library")
        val path = getRelativePath(project, file)
        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile)
            ?: return BaseDeclarationRef(name, path)
        val line = document.getLineNumber(base.textOffset) + 1
        val column = base.textOffset - document.getLineStartOffset(line - 1) + 1
        return BaseDeclarationRef(name, "$path:$line:$column")
    }

    /**
     * Re-executes the search to collect more results beyond the initial cache.
     * This re-scans from the beginning, skipping already-seen keys — O(total_results) per extension.
     * This is unavoidable: IntelliJ's search APIs (ReferencesSearch, PsiSearchHelper, etc.)
     * don't support offset-based iteration or resumption.
     */
    private fun extendFindUsages(
        project: Project,
        targetElement: PsiElement,
        seenKeys: Set<String>,
        limit: Int,
        scope: BuiltInSearchScope
    ): List<PaginationService.SerializedResult> {
        val newResults = ConcurrentLinkedQueue<PaginationService.SerializedResult>()
        val count = AtomicInteger(0)
        val searchScope = BuiltInSearchScopeResolver.resolveGlobalScope(project, scope)
        val seenLocationKeys = ConcurrentHashMap.newKeySet<String>()
        seenLocationKeys.addAll(seenKeys)

        val collectRef: (UsageHit) -> Boolean = { hit ->
            ProgressManager.checkCanceled()
            val refElement = hit.element
            if (!refElement.isValid) {
                true
            } else {
                val refFile = refElement.containingFile?.virtualFile
                val document = refElement.containingFile?.let {
                    PsiDocumentManager.getInstance(project).getDocument(it)
                }
                if (refFile != null && document != null && searchScope.contains(refFile)) {
                    val lineNumber = document.getLineNumber(hit.offset) + 1
                    val columnNumber = hit.offset -
                        document.getLineStartOffset(lineNumber - 1) + 1
                    val key = "${getRelativePath(project, refFile)}:$lineNumber:$columnNumber"

                    if (seenLocationKeys.add(key)) {
                        val slot = count.incrementAndGet()
                        if (slot <= limit) {
                            val usage = UsageLocation(
                                file = getRelativePath(project, refFile),
                                line = lineNumber,
                                column = columnNumber,
                                preview = LinePreview.ofLine(document, lineNumber - 1, columnNumber - 1),
                                usageType = classifyUsage(refElement),
                                enclosingScope = PsiUtils.getEnclosingScope(refElement),
                                match = hit.match
                            )
                            newResults.add(
                                PaginationService.SerializedResult(key, json.encodeToJsonElement(usage))
                            )
                        }
                        slot < limit
                    } else {
                        true
                    }
                } else {
                    true
                }
            }
        }

        try {
            FindUsagesHandlerSearch.processReferences(
                project = project,
                element = targetElement,
                scope = searchScope,
                processor = Processor { hit -> collectRef(hit) }
            )
        } catch (e: LinkageError) {
            LOG.warn("Reference search pagination failed for ${targetElement.javaClass.name}", e)
            throw IllegalStateException(searchInfrastructureErrorMessage(e), e)
        }

        return newResults.toList()
    }
}
