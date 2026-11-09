package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.ErrorMessages
import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.server.McpErrors
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.SymbolAnchor
import com.github.vcth4nh.idesense.tools.SymbolAnchorResolver
import com.github.vcth4nh.idesense.tools.SymbolResolution
import com.github.vcth4nh.idesense.tools.models.CallElement
import com.github.vcth4nh.idesense.tools.models.CallHierarchyResult
import com.github.vcth4nh.idesense.tools.models.SymbolCandidatesResult
import com.github.vcth4nh.idesense.tools.navigation.hierarchy.ClassLikePsi
import com.github.vcth4nh.idesense.tools.navigation.hierarchy.HierarchyKind
import com.github.vcth4nh.idesense.tools.navigation.hierarchy.HierarchyScope
import com.github.vcth4nh.idesense.tools.navigation.hierarchy.HierarchyTreeWalker
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.PsiUtils
import com.intellij.ide.hierarchy.HierarchyNodeDescriptor
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiNamedElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive

/**
 * Tool for analyzing method call relationships across multiple languages.
 *
 * Supports: Java, Kotlin, Python, JavaScript, TypeScript, Go, PHP, Rust
 *
 * Delegates to the IDE's LanguageCallHierarchy extension point via [HierarchyTreeWalker].
 */
class CallHierarchyTool : AbstractMcpTool() {

    override val name = "ide_call_hierarchy"

    override val description = """
        Build a call hierarchy tree for a method/function — who calls it (callers) or what it calls
        (callees). Use over ide_find_usages when you need the full call chain as a tree rather than
        a flat reference list. Anchor on a symbol name or qualified name (symbol), or on the
        declaration position (file + line + column). A class name anchors on its constructor where
        the IDE's provider supports that (Java, Kotlin, Python, Rust); elsewhere the error names the
        class — pass a method/function name instead.

        Returns: recursive tree with method names, qualified names, file locations (line/column),
        and nested call relationships up to maxDepth (default 3).

        Gotchas: requires smart mode. Languages: Java, Kotlin, Python, JS/TS, Go, PHP, Rust. Rust
        "callees" may be incomplete due to PSI resolution limits. The tree holds at most $MAX_NODES
        nodes, filled depth-first. When the walk reaches this limit, the result has truncated=true,
        and the nodes after that point show no children, even if they have some. Then lower
        maxDepth, start from one caller, or use ide_find_usages (paginated) for the full flat list
        of direct callers.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .stringProperty(
            ParamNames.SYMBOL,
            "Symbol name or qualified name (e.g. \"UserService\", \"demo.UserService\", \"UserService.authenticate\"); an overloaded method needs its parameter list to select one overload (e.g. \"demo.Quirks#parse(java.lang.String)\"), otherwise the overloads come back as candidates. Mutually exclusive with file/line/column."
        )
        .file(required = false, description = "Project-relative file path, or a dependency/library absolute path or jar:// URL previously returned by the plugin. Use with line and column; mutually exclusive with symbol.")
        .lineAndColumn(required = false)
        .enumProperty("direction", "Direction: 'callers' (methods that call this method) or 'callees' (methods this method calls)", listOf("callers", "callees"), required = true)
        .intProperty("maxDepth", "How many levels deep to traverse the call hierarchy (default: $DEFAULT_DEPTH, max: $MAX_DEPTH)")
        .hierarchyScopeProperty(
            "Hierarchy scope. Default: all. (production = production sources only — empty in projects without production roots, same as the IDE.)",
            HierarchyScope.wireValues(HierarchyScope.CALL_HIERARCHY_SCOPES)
        )
        .build()

    companion object {
        private const val DEFAULT_DEPTH = 3
        private const val MAX_DEPTH = 20
        // Bounds the response: a callers tree of a frequently called function can hold thousands of nodes.
        private const val MAX_NODES = 200
    }

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val direction = arguments["direction"]?.jsonPrimitive?.content
            ?: return createErrorResult("Missing required parameter: direction")
        val depth = (arguments["maxDepth"]?.jsonPrimitive?.int ?: DEFAULT_DEPTH).coerceIn(1, MAX_DEPTH)
        val scope = try {
            HierarchyScope.parse(arguments)
        } catch (_: IllegalArgumentException) {
            return createInvalidScopeError(arguments[ParamNames.SCOPE], HierarchyScope.wireValues(HierarchyScope.CALL_HIERARCHY_SCOPES))
        }
        val kind = when (direction) {
            "callers" -> HierarchyKind.CALLERS
            "callees" -> HierarchyKind.CALLEES
            else -> return createErrorResult("direction must be 'callers' or 'callees'")
        }
        val anchor = SymbolAnchor.parse(arguments)
        if (anchor is SymbolAnchor.Invalid) {
            return createStructuredErrorResult(McpErrors.generic("invalid_arguments", anchor.message))
        }

        requireSmartMode(project)

        return suspendingReadAction {
            ProgressManager.checkCanceled()

            val element = when (anchor) {
                is SymbolAnchor.BySymbol -> when (val resolution = SymbolAnchorResolver.resolve(project, anchor.symbol)) {
                    is SymbolResolution.Resolved -> resolution.element
                    is SymbolResolution.Ambiguous -> return@suspendingReadAction createJsonResult(
                        SymbolCandidatesResult(
                            candidates = resolution.candidates,
                            message = "Ambiguous symbol '${anchor.symbol}': ${resolution.candidates.size} matches. Pass a qualified name or a file/line/column position.",
                        )
                    )
                    SymbolResolution.NotFound -> return@suspendingReadAction createErrorResult(
                        "Symbol not found in project files: '${anchor.symbol}'. Try a qualified name, or ide_find_symbol with fuzzySearch=true."
                    )
                }
                is SymbolAnchor.ByPosition -> {
                    val element = resolveElementFromArguments(project, arguments, allowLibraryFilesForPosition = true).getOrElse {
                        return@suspendingReadAction createErrorResult(it.message ?: ErrorMessages.COULD_NOT_RESOLVE_SYMBOL)
                    }
                    // Tool-layer gate: reject position-based invocations where the caret is not on a
                    // resolvable navigation target (comment, whitespace, literal).
                    if (PsiUtils.resolveTargetElement(element) == null) {
                        return@suspendingReadAction createErrorResult(
                            "No method/function found at position." + caretHint(element, arguments)
                        )
                    }
                    element
                }
                is SymbolAnchor.Invalid -> error("unreachable: Invalid anchor handled above")
            }

            ProgressManager.checkCanceled()

            val walkResult = HierarchyTreeWalker.walk(project, element, kind, scope, depth, MAX_NODES).getOrElse {
                if (anchor is SymbolAnchor.BySymbol && ClassLikePsi.isClassLike(element)) {
                    return@suspendingReadAction createErrorResult(
                        "No method/function found for symbol '${anchor.symbol}': it is a class-like declaration and this language's call hierarchy does not accept a class. Pass a method/function name (e.g. '${anchor.symbol}.method') or a file/line/column position."
                    )
                }
                return@suspendingReadAction createErrorResult(it.message ?: "Failed to build call hierarchy")
            }

            val rootCallElement = convertDescriptorToCallElement(walkResult.root, walkResult.resolver, depth)
                ?: return@suspendingReadAction createErrorResult(
                    if (anchor is SymbolAnchor.BySymbol) "No method/function found for symbol '${anchor.symbol}'."
                    else "No method/function found at position." + caretHint(element, arguments)
                )

            createJsonResult(CallHierarchyResult(
                element = rootCallElement.copy(children = null),
                calls = rootCallElement.children ?: emptyList(),
                truncated = walkResult.truncated
            ))
        }
    }

    /**
     * Converts an IDE [HierarchyNodeDescriptor] tree (as returned by [HierarchyTreeWalker])
     * into our wire-format [CallElement] tree. Recursive; bounded by [remainingDepth].
     * Returns null if the descriptor's PSI element couldn't be resolved or has no source location.
     */
    private fun convertDescriptorToCallElement(
        descriptor: HierarchyNodeDescriptor,
        resolver: com.github.vcth4nh.idesense.tools.navigation.hierarchy.LogicalElementResolver,
        remainingDepth: Int
    ): CallElement? {
        val psi = resolver.resolve(descriptor) ?: return null
        val virtualFile = psi.containingFile?.virtualFile ?: return null
        val document = PsiDocumentManager.getInstance(psi.project)
            .getDocument(psi.containingFile) ?: return null
        val offset = PsiUtils.identifierOffset(psi)
        val line = document.getLineNumber(offset) + 1
        val column = offset - document.getLineStartOffset(line - 1) + 1

        val children = if (remainingDepth <= 0) emptyList() else descriptor.cachedChildren
            ?.filterIsInstance<HierarchyNodeDescriptor>()
            ?.mapNotNull { convertDescriptorToCallElement(it, resolver, remainingDepth - 1) }
            ?: emptyList()

        val qualifiedName = com.github.vcth4nh.idesense.tools.navigation.hierarchy.ClassLikePsi
            .describeQualifiedName(psi)

        return CallElement(
            name = com.github.vcth4nh.idesense.tools.navigation.hierarchy.ClassLikePsi
                .descriptorDisplayName(descriptor, psi),
            qualifiedName = qualifiedName,
            enclosingScope = if (qualifiedName == null) PsiUtils.getEnclosingScope(psi) else null,
            kind = com.github.vcth4nh.idesense.handlers.LanguageServices.getKind(psi),
            file = ProjectUtils.getRelativePath(psi.project, virtualFile),
            line = line,
            column = column,
            children = if (children.isEmpty()) null else children
        )
    }

}
