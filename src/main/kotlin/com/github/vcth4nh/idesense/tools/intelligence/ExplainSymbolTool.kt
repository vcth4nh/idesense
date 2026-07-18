package com.github.vcth4nh.idesense.tools.intelligence

import com.github.vcth4nh.idesense.constants.ErrorMessages
import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScope
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScopeResolver
import com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch
import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.handlers.PopupFaithfulSymbolSearch
import com.github.vcth4nh.idesense.handlers.SymbolData
import com.github.vcth4nh.idesense.handlers.SymbolDataConverter
import com.github.vcth4nh.idesense.server.McpErrors
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.DefinitionResult
import com.github.vcth4nh.idesense.tools.models.ExplainSymbolResult
import com.github.vcth4nh.idesense.tools.models.ImplementationLocation
import com.github.vcth4nh.idesense.tools.models.ProblemInfo
import com.github.vcth4nh.idesense.tools.models.SuperMethodInfo
import com.github.vcth4nh.idesense.tools.models.SymbolMatch
import com.github.vcth4nh.idesense.tools.models.UsageLocation
import com.github.vcth4nh.idesense.tools.navigation.FindDefinitionTool
import com.github.vcth4nh.idesense.tools.navigation.FindUsagesTool
import com.github.vcth4nh.idesense.tools.navigation.ImplementationLocations
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.github.vcth4nh.idesense.util.HtmlToText
import com.github.vcth4nh.idesense.util.PsiUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.codeInsight.documentation.DocumentationManager
import com.intellij.navigation.NavigationItem
import com.intellij.platform.backend.documentation.DocumentationData
import com.intellij.platform.backend.documentation.PsiDocumentationTargetProvider
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.search.searches.DefinitionsScopedSearch
import com.intellij.psi.search.searches.ReferencesSearch
import com.intellij.util.Processor
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonPrimitive

/**
 * Fused "what is this thing?" tool (#41): definition + signature + quick documentation +
 * supers + implementations + usage summary in one round-trip, composing the same engines
 * the discrete tools use, inside a single read action. Accepts a symbol name in addition
 * to an exact position so agents can skip the find-coordinates-first step.
 */
class ExplainSymbolTool : AbstractMcpTool() {

    companion object {
        private val LOG = logger<ExplainSymbolTool>()
        internal const val MAX_IMPLEMENTATIONS = 10
        internal const val MAX_TOP_USAGES = 5
        internal const val MAX_USAGE_COUNT = 200
        internal const val MAX_DOC_LENGTH = 4000
        internal const val MAX_CANDIDATES = 10
        private const val MAX_DECLARATION_PROBLEMS = 50
    }

    override val name = ToolNames.EXPLAIN_SYMBOL

    override val description = """
        Explain a symbol in one round-trip: declaration + signature + quick documentation +
        supers + implementations + usage summary, fused from the IDE's navigation and
        documentation engines. Prefer this over chaining ide_find_definition /
        ide_find_super_methods / ide_find_implementations / ide_find_usages when the question
        is "what is this thing?".

        Anchor with either symbol (name or qualified name, e.g. "UserService" or
        "demo.UserService.authenticate") or an exact file+line+column position. An ambiguous
        name returns a candidates list instead of guessing. Set includeDiagnostics=true to add
        code problems overlapping the declaration (runs a file analysis pass — slower).

        Returns: symbol (declaration location, kind, preview), signature, documentation (plain
        text), supers, implementations (capped at $MAX_IMPLEMENTATIONS), usageCount (project files,
        counted up to $MAX_USAGE_COUNT) with topUsages ($MAX_TOP_USAGES), problems (only with
        includeDiagnostics), and warnings naming any degraded facet.

        Gotchas: requires smart mode. Facets are capped summaries — page through the dedicated
        tools for full result sets.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .stringProperty(
            ParamNames.SYMBOL,
            "Symbol name or qualified name (e.g. \"UserService\", \"demo.UserService\", \"UserService.authenticate\"). Mutually exclusive with file/line/column."
        )
        .file(required = false, description = "Project-relative file path, or a dependency/library absolute path or jar:// URL previously returned by the plugin. Use with line and column; mutually exclusive with symbol.")
        .lineAndColumn(required = false)
        .booleanProperty(
            ParamNames.INCLUDE_DIAGNOSTICS,
            "Also analyze the declaration's file and return problems overlapping the declaration. Default: false (the analysis pass is slower)."
        )
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val anchor = ExplainAnchor.parse(arguments)
        if (anchor is ExplainAnchor.Invalid) {
            return createStructuredErrorResult(McpErrors.generic("invalid_arguments", anchor.message))
        }
        val includeDiagnostics = arguments[ParamNames.INCLUDE_DIAGNOSTICS]?.jsonPrimitive?.booleanOrNull ?: false
        requireSmartMode(project)

        val (core, earlyResult) = suspendingReadAction {
            val target = when (anchor) {
                is ExplainAnchor.BySymbol -> when (val resolution = resolveSymbolAnchor(project, anchor.symbol)) {
                    is SymbolResolution.Resolved -> resolution.element
                    is SymbolResolution.Ambiguous -> return@suspendingReadAction null to createJsonResult(
                        ExplainSymbolResult(
                            candidates = resolution.candidates,
                            message = "Ambiguous symbol '${anchor.symbol}': ${resolution.candidates.size} matches. " +
                                "Pass a qualified name or a file/line/column position.",
                        )
                    )
                    SymbolResolution.NotFound -> return@suspendingReadAction null to createErrorResult(
                        "Symbol not found in project files: '${anchor.symbol}'. Try a qualified name, or ide_find_symbol with fuzzySearch=true."
                    )
                }
                is ExplainAnchor.ByPosition -> {
                    val element = resolveElementFromArguments(project, arguments, allowLibraryFilesForPosition = true).getOrElse {
                        return@suspendingReadAction null to createErrorResult(it.message ?: ErrorMessages.COULD_NOT_RESOLVE_SYMBOL)
                    }
                    element as? PsiNamedElement
                        ?: PsiUtils.resolveTargetElement(element)
                        ?: return@suspendingReadAction null to createErrorResult(ErrorMessages.SYMBOL_NOT_RESOLVED)
                }
                is ExplainAnchor.Invalid -> error("unreachable: Invalid anchor handled above")
            }
            buildCore(project, FindDefinitionTool.effectiveDeclarationTarget(target))
        }
        if (earlyResult != null) return earlyResult
        checkNotNull(core)

        if (!includeDiagnostics) {
            return createJsonResult(core.result.copy(warnings = core.warnings.ifEmpty { null }))
        }

        val warnings = core.warnings.toMutableList()
        var problems: List<ProblemInfo>? = null
        val declarationFile = core.declarationFile
        if (!declarationFile.isInLocalFileSystem) {
            warnings += "Diagnostics skipped: declaration is not in a local project file."
        } else {
            try {
                val analysis = DiagnosticsAnalysisService.getInstance(project).analyzeFile(
                    virtualFile = declarationFile,
                    filePath = core.result.symbol?.file ?: "",
                    severity = "all",
                    startLine = core.declarationStartLine,
                    endLine = core.declarationEndLine,
                    maxProblems = MAX_DECLARATION_PROBLEMS,
                )
                problems = analysis.problems
                analysis.analysisMessage?.let { warnings += it }
                if (analysis.analysisTimedOut && analysis.analysisMessage == null) {
                    warnings += "Diagnostics analysis timed out; problems may be incomplete."
                }
            } catch (e: ProcessCanceledException) {
                throw e
            } catch (e: Exception) {
                LOG.warn("explain_symbol diagnostics facet failed", e)
                warnings += "Diagnostics facet failed: ${e.message}"
            }
        }
        return createJsonResult(core.result.copy(problems = problems, warnings = warnings.ifEmpty { null }))
    }

    private sealed interface SymbolResolution {
        data class Resolved(val element: PsiElement) : SymbolResolution
        data class Ambiguous(val candidates: List<SymbolMatch>) : SymbolResolution
        data object NotFound : SymbolResolution
    }

    /**
     * Resolves a symbol name to its declaration: exact qualified-name lookup first
     * (ClassResolver, so library FQNs work), then the Go to Symbol popup stack with the
     * same exact-name filter ide_find_symbol applies when fuzzySearch=false.
     */
    private fun resolveSymbolAnchor(project: Project, symbol: String): SymbolResolution {
        findClassByName(project, symbol)?.let { return SymbolResolution.Resolved(it) }

        val scope = BuiltInSearchScopeResolver.resolveGlobalScope(project, BuiltInSearchScope.PROJECT_FILES)
        val popup = PopupFaithfulSymbolSearch.search(project, symbol, scope, MAX_CANDIDATES * 4)
        data class Match(val element: PsiElement, val data: SymbolData)
        val matches = popup.candidates
            .mapNotNull { candidate ->
                val data = SymbolDataConverter.convert(candidate.item, project, scope) ?: return@mapNotNull null
                if (!data.name.equals(popup.localPattern, ignoreCase = true)) return@mapNotNull null
                val element = candidate.item as? PsiElement ?: extractPsiElement(candidate.item) ?: return@mapNotNull null
                Match(element, data)
            }
            .distinctBy { "${it.data.file}:${it.data.line}:${it.data.column}:${it.data.name}" }

        return when {
            matches.isEmpty() -> SymbolResolution.NotFound
            matches.size == 1 -> SymbolResolution.Resolved(matches.single().element)
            else -> SymbolResolution.Ambiguous(matches.take(MAX_CANDIDATES).map { match ->
                SymbolMatch(
                    name = match.data.name,
                    qualifiedName = match.data.qualifiedName,
                    kind = match.data.kind,
                    file = match.data.file,
                    line = match.data.line,
                    column = match.data.column,
                )
            })
        }
    }

    private fun extractPsiElement(item: NavigationItem): PsiElement? = try {
        item.javaClass.getMethod("getElement").invoke(item) as? PsiElement
    } catch (_: Exception) {
        null
    }

    private data class CoreData(
        val result: ExplainSymbolResult,
        val warnings: List<String>,
        val declarationFile: VirtualFile,
        val declarationStartLine: Int?,
        val declarationEndLine: Int?,
    )

    /**
     * Collects every read-action facet for [target]. Each facet degrades independently:
     * a failure lands in warnings and leaves the facet null instead of failing the call
     * (cancellation always propagates so the read action can retry).
     */
    private fun buildCore(project: Project, target: PsiElement): Pair<CoreData?, ToolCallResult?> {
        val targetFile = target.containingFile?.virtualFile
            ?: return null to createErrorResult(ErrorMessages.DEFINITION_FILE_NOT_FOUND)
        val document = PsiDocumentManager.getInstance(project).getDocument(target.containingFile)
            ?: return null to createErrorResult(ErrorMessages.DEFINITION_DOCUMENT_NOT_FOUND)

        val warnings = mutableListOf<String>()

        val line = document.getLineNumber(target.textOffset) + 1
        val column = target.textOffset - document.getLineStartOffset(line - 1) + 1
        val preview = document.getText(
            TextRange(document.getLineStartOffset(line - 1), document.getLineEndOffset(line - 1))
        ).trim()
        val qualifiedName = QualifiedNameUtil.getQualifiedName(target)
        val definition = DefinitionResult(
            file = getRelativePath(project, targetFile),
            line = line,
            column = column,
            name = (target as? PsiNamedElement)?.name ?: target.text.take(50),
            kind = LanguageServices.getKind(target),
            preview = preview,
            qualifiedName = qualifiedName,
            enclosingScope = if (qualifiedName == null) PsiUtils.getEnclosingScope(target) else null,
        )

        var signature: String? = null
        var documentation: String? = null
        var documentationTruncated: Boolean? = null
        try {
            val provider = DocumentationManager.getProviderFromElement(target)
            var signatureHtml = provider.getQuickNavigateInfo(target, target)
            var docHtml = provider.generateDoc(target, target)
            if (signatureHtml == null || docHtml == null) {
                // Languages on the newer documentation stack (e.g. Kotlin K2) serve quick doc
                // through the DocumentationTarget EP, not the classic DocumentationProvider.
                // Async DocumentationResult variants are skipped — the facet stays null.
                for (targetProvider in PsiDocumentationTargetProvider.EP_NAME.extensionList) {
                    val docTarget = targetProvider.documentationTargets(target, target).firstOrNull() ?: continue
                    if (signatureHtml == null) signatureHtml = docTarget.computeDocumentationHint()
                    if (docHtml == null) {
                        docHtml = (docTarget.computeDocumentation() as? DocumentationData)?.html
                    }
                    if (signatureHtml != null && docHtml != null) break
                }
            }
            signature = signatureHtml?.let { HtmlToText.convert(it) }?.takeIf { it.isNotBlank() }
            val doc = docHtml?.let { HtmlToText.convert(it) }?.takeIf { it.isNotBlank() }
            if (doc != null && doc.length > MAX_DOC_LENGTH) {
                documentation = doc.take(MAX_DOC_LENGTH)
                documentationTruncated = true
            } else {
                documentation = doc
            }
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: Exception) {
            LOG.warn("explain_symbol documentation facet failed for ${target.javaClass.name}", e)
            warnings += "Documentation facet failed: ${e.message}"
        }

        var supers: List<SuperMethodInfo>? = null
        try {
            supers = LanguageServices.findSuperMethods(target, project)?.hierarchy?.map { superMethod ->
                SuperMethodInfo(
                    name = superMethod.name,
                    qualifiedName = superMethod.qualifiedName,
                    kind = superMethod.kind,
                    file = superMethod.file,
                    line = superMethod.line,
                    column = superMethod.column,
                )
            }
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: Exception) {
            LOG.warn("explain_symbol supers facet failed for ${target.javaClass.name}", e)
            warnings += "Supers facet failed: ${e.message}"
        }

        val searchScope = BuiltInSearchScopeResolver.resolveGlobalScope(project, BuiltInSearchScope.PROJECT_FILES)

        var implementations: List<ImplementationLocation>? = null
        var implementationsTruncated: Boolean? = null
        try {
            val collected = mutableListOf<ImplementationLocation>()
            DefinitionsScopedSearch.search(target, searchScope, true).forEach(Processor { impl ->
                ProgressManager.checkCanceled()
                ImplementationLocations.convert(impl, project)?.let { collected.add(it) }
                collected.size <= MAX_IMPLEMENTATIONS
            })
            implementationsTruncated = collected.size > MAX_IMPLEMENTATIONS
            implementations = collected.take(MAX_IMPLEMENTATIONS)
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: Exception) {
            LOG.warn("explain_symbol implementations facet failed for ${target.javaClass.name}", e)
            warnings += "Implementations facet failed: ${e.message}"
        }

        var usageCount: Int? = null
        var usagesTruncated: Boolean? = null
        var topUsages: List<UsageLocation>? = null
        try {
            val seen = HashSet<String>()
            val top = mutableListOf<UsageLocation>()
            val collectRef: (PsiElement) -> Boolean = { refElement ->
                ProgressManager.checkCanceled()
                if (refElement.isValid) {
                    val refFile = refElement.containingFile?.virtualFile
                    val refDocument = refElement.containingFile?.let {
                        PsiDocumentManager.getInstance(project).getDocument(it)
                    }
                    if (refFile != null && refDocument != null && searchScope.contains(refFile)) {
                        val refLine = refDocument.getLineNumber(refElement.textOffset) + 1
                        val refColumn = refElement.textOffset - refDocument.getLineStartOffset(refLine - 1) + 1
                        val path = getRelativePath(project, refFile)
                        if (seen.add("$path:$refLine:$refColumn") && top.size < MAX_TOP_USAGES) {
                            val lineText = refDocument.getText(
                                TextRange(
                                    refDocument.getLineStartOffset(refLine - 1),
                                    refDocument.getLineEndOffset(refLine - 1)
                                )
                            ).trim()
                            top.add(UsageLocation(
                                file = path,
                                line = refLine,
                                column = refColumn,
                                preview = lineText,
                                usageType = FindUsagesTool.classifyUsage(refElement),
                                enclosingScope = PsiUtils.getEnclosingScope(refElement),
                            ))
                        }
                    }
                }
                seen.size < MAX_USAGE_COUNT
            }
            val handlerProcessed = FindUsagesHandlerSearch.processReferences(
                project = project,
                element = target,
                scope = searchScope,
                processor = Processor { refElement -> collectRef(refElement) }
            )
            if (!handlerProcessed) {
                ReferencesSearch.search(target, searchScope).forEach(Processor { reference ->
                    collectRef(reference.element)
                })
            }
            usageCount = seen.size
            usagesTruncated = seen.size >= MAX_USAGE_COUNT
            topUsages = top
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            LOG.warn("explain_symbol usages facet failed for ${target.javaClass.name}", e)
            warnings += "Usages facet failed: ${FindUsagesTool.searchInfrastructureErrorMessage(e)}"
        } catch (e: Exception) {
            LOG.warn("explain_symbol usages facet failed for ${target.javaClass.name}", e)
            warnings += "Usages facet failed: ${e.message}"
        }

        val declarationRange = target.textRange
        return CoreData(
            result = ExplainSymbolResult(
                symbol = definition,
                signature = signature,
                documentation = documentation,
                documentationTruncated = documentationTruncated,
                supers = supers,
                implementations = implementations,
                implementationsTruncated = implementationsTruncated,
                usageCount = usageCount,
                usagesTruncated = usagesTruncated,
                topUsages = topUsages,
            ),
            warnings = warnings,
            declarationFile = targetFile,
            declarationStartLine = declarationRange?.let { document.getLineNumber(it.startOffset) + 1 },
            declarationEndLine = declarationRange?.let {
                document.getLineNumber(it.endOffset.coerceAtMost(document.textLength)) + 1
            },
        ) to null
    }
}
