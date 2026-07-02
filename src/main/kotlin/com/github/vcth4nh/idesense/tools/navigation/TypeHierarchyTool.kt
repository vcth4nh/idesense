package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.TypeElement
import com.github.vcth4nh.idesense.tools.models.TypeHierarchyResult
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
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Tool for retrieving type hierarchies across multiple languages.
 *
 * Supports: Java, Kotlin, Python, JavaScript, TypeScript, Go, PHP, Rust
 *
 * Delegates to the IDE's LanguageTypeHierarchy extension point via [HierarchyTreeWalker].
 */
class TypeHierarchyTool : AbstractMcpTool() {

    override val name = "ide_type_hierarchy"

    override val description = """
        Get a depth-limited inheritance hierarchy for a class or interface (up to maxDepth, default 5 / max 20) — supertypes, subtypes, or both. Use
        when you need the tree of ancestors or descendants; prefer ide_find_super_methods for a
        single element's direct super (cheaper), or ide_find_implementations for a flat list of
        implementors.

        Returns: root class info, recursive supertypes chain, and flat subtypes list — per direction.
        "both" unions the two walks rather than producing the IDE's combined tree view.

        Gotchas: requires smart mode. Languages: Java, Kotlin, Python, JS/TS, Go, PHP, Rust. Rust
        does not support the className shortcut — use file + line + column. Kotlin K2: direction=both/
        supertypes requires EDT context; may show empty for some Kotlin classes.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .stringProperty("className", "Fully qualified class name (e.g., 'com.example.MyClass' for Java or 'App\\\\Models\\\\User' for PHP). RECOMMENDED where supported - use this if you know the class name. Not supported for Rust (use file + line + column).")
        .file(required = false, description = "Path to file relative to project root (e.g., 'src/main/java/com/example/MyClass.java'). Use with line and column.")
        .intProperty("line", "1-based line number where the class is defined. Required if using file parameter.")
        .intProperty("column", "1-based column number. Required if using file parameter.")
        .hierarchyScopeProperty(
            "Hierarchy scope. Default: all. (production = production sources only — empty in projects without production roots, same as the IDE.)",
            HierarchyScope.wireValues(HierarchyScope.TYPE_HIERARCHY_SCOPES)
        )
        .enumProperty(
            ParamNames.DIRECTION,
            "Which direction to traverse: 'supertypes' (ancestors), 'subtypes' (descendants), or 'both'. Default: both. 'both' returns the union of the supertypes and subtypes walks, not the IDE's single merged Type Hierarchy tree.",
            listOf("supertypes", "subtypes", "both")
        )
        .intProperty("maxDepth", "How many levels deep to traverse the hierarchy (default: 5, max: 20).")
        .build()

    companion object {
        private const val DEFAULT_DEPTH = 5
        private const val MAX_DEPTH = 20
        private const val DIRECTION_SUPERTYPES = "supertypes"
        private const val DIRECTION_SUBTYPES = "subtypes"
        private const val DIRECTION_BOTH = "both"
    }

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        requireSmartMode(project)

        val className = arguments["className"]?.jsonPrimitive?.content
        val file = arguments["file"]?.jsonPrimitive?.content
        val direction = arguments[ParamNames.DIRECTION]?.jsonPrimitive?.content ?: DIRECTION_BOTH
        val maxDepth = (arguments["maxDepth"]?.jsonPrimitive?.int ?: DEFAULT_DEPTH).coerceIn(1, MAX_DEPTH)
        val rawScope = rawScopeValue(arguments[ParamNames.SCOPE])
        val scope = try {
            HierarchyScope.parse(arguments)
        } catch (_: IllegalArgumentException) {
            return createInvalidScopeError(rawScope)
        }

        val includeSupertypes = direction != DIRECTION_SUBTYPES
        val includeSubtypes = direction != DIRECTION_SUPERTYPES

        return suspendingReadAction {
            ProgressManager.checkCanceled()

            val element = resolveTargetElement(project, arguments) ?: run {
                val errorMsg = when {
                    className != null -> "Class '$className' not found in project '${project.name}'. Verify the fully qualified name is correct and the class is part of this project."
                    file != null -> "No class found at the specified file/line/column position."
                    else -> "Provide either 'className' (e.g., 'com.example.MyClass') or 'file' + 'line' + 'column'."
                }
                return@suspendingReadAction createErrorResult(errorMsg)
            }

            ProgressManager.checkCanceled()

            // Walk only the requested direction(s). `both` (default) preserves the original
            // behavior: supertypes recurse up to maxDepth, subtypes are flattened.
            val superResult = if (includeSupertypes) {
                HierarchyTreeWalker
                    .walk(project, element, HierarchyKind.SUPERTYPES, scope, maxDepth)
                    .getOrElse {
                        return@suspendingReadAction createErrorResult(it.message ?: "Failed to build supertype hierarchy")
                    }
            } else null

            val subResult = if (includeSubtypes) {
                HierarchyTreeWalker
                    .walk(project, element, HierarchyKind.SUBTYPES, scope, maxDepth)
                    .getOrElse {
                        return@suspendingReadAction createErrorResult(it.message ?: "Failed to build subtype hierarchy")
                    }
            } else null

            val supertypes = superResult?.let { sr ->
                sr.root.cachedChildren
                    ?.filterIsInstance<HierarchyNodeDescriptor>().orEmpty()
                    .mapNotNull {
                        convertDescriptorToTypeElement(it, sr.resolver, recurseSupertypes = true, remainingDepth = maxDepth)
                    }
            } ?: emptyList()

            val subtypes = mutableListOf<TypeElement>()
            if (subResult != null) {
                val resolver = subResult.resolver
                fun collectSubtypes(desc: HierarchyNodeDescriptor) {
                    convertDescriptorToTypeElement(desc, resolver, recurseSupertypes = false, remainingDepth = 0)
                        ?.let { subtypes.add(it) }
                    desc.cachedChildren
                        ?.filterIsInstance<HierarchyNodeDescriptor>()
                        ?.forEach { collectSubtypes(it) }
                }
                subResult.root.cachedChildren
                    ?.filterIsInstance<HierarchyNodeDescriptor>()
                    ?.forEach { collectSubtypes(it) }
            }

            // Root descriptor comes from whichever walk ran (at least one always does).
            val rootDescriptor = (superResult ?: subResult)!!.root
            val rootElement = ClassLikePsi.walkUpToClassLike(element) ?: element
            val rootTypeElement = buildRootTypeElement(rootDescriptor, rootElement)
                ?: return@suspendingReadAction createErrorResult("Could not extract class info from element")

            createJsonResult(TypeHierarchyResult(
                element = rootTypeElement,
                supertypes = supertypes,
                subtypes = subtypes
            ))
        }
    }

    private fun rawScopeValue(scopeElement: JsonElement?): String = when (scopeElement) {
        null -> ""
        is JsonPrimitive -> scopeElement.content
        else -> scopeElement.toString()
    }

    private fun createInvalidScopeError(provided: String): ToolCallResult =
        createStructuredErrorResult(buildJsonObject {
            put("error", JsonPrimitive("invalid_scope"))
            put("parameter", JsonPrimitive(ParamNames.SCOPE))
            put("provided", JsonPrimitive(provided))
            put("supportedValues", buildJsonArray {
                HierarchyScope.wireValues(HierarchyScope.TYPE_HIERARCHY_SCOPES).forEach { add(JsonPrimitive(it)) }
            })
        })

    private fun resolveTargetElement(project: Project, arguments: JsonObject): PsiElement? {
        // Try className first (Java/Kotlin specific)
        val className = arguments["className"]?.jsonPrimitive?.content
        if (className != null) {
            return findClassByName(project, className)
        }

        // Otherwise use file/line/column (works for all languages)
        val file = arguments["file"]?.jsonPrimitive?.content ?: return null
        val line = arguments["line"]?.jsonPrimitive?.int ?: return null
        val column = arguments["column"]?.jsonPrimitive?.int ?: return null

        return findPsiElement(project, file, line, column)
    }

    /**
     * Converts a [HierarchyNodeDescriptor] to a wire-format [TypeElement]. When [recurseSupertypes]
     * is true, recursively walks the descriptor's cached children into the [TypeElement.supertypes]
     * field (used for the supertypes branch). When false, [TypeElement.supertypes] is left null
     * (used for the flat subtypes list).
     */
    private fun convertDescriptorToTypeElement(
        descriptor: HierarchyNodeDescriptor,
        resolver: com.github.vcth4nh.idesense.tools.navigation.hierarchy.LogicalElementResolver,
        recurseSupertypes: Boolean,
        remainingDepth: Int
    ): TypeElement? {
        val psi = resolver.resolve(descriptor) ?: return null
        val virtualFile = psi.containingFile?.virtualFile

        val supertypes = if (recurseSupertypes && remainingDepth > 0) {
            descriptor.cachedChildren
                ?.filterIsInstance<HierarchyNodeDescriptor>()
                ?.mapNotNull { convertDescriptorToTypeElement(it, resolver, recurseSupertypes = true, remainingDepth = remainingDepth - 1) }
                ?.takeIf { it.isNotEmpty() }
        } else null

        val qualifiedName = ClassLikePsi.describeQualifiedName(psi)
        val (line, column) = computeLineColumn(psi)

        return TypeElement(
            name = ClassLikePsi.descriptorDisplayName(descriptor, psi),
            qualifiedName = qualifiedName,
            enclosingScope = if (qualifiedName == null) PsiUtils.getEnclosingScope(psi) else null,
            kind = ClassLikePsi.describeKind(psi),
            file = virtualFile?.let { ProjectUtils.getRelativePath(psi.project, it) },
            line = line,
            column = column,
            supertypes = supertypes
        )
    }

    private fun computeLineColumn(psi: PsiElement): Pair<Int?, Int?> {
        val containingFile = psi.containingFile ?: return null to null
        val document = PsiDocumentManager.getInstance(psi.project)
            .getDocument(containingFile) ?: return null to null
        val offset = PsiUtils.identifierOffset(psi)
        val line = document.getLineNumber(offset) + 1
        val column = offset - document.getLineStartOffset(line - 1) + 1
        return line to column
    }


    private fun buildRootTypeElement(descriptor: HierarchyNodeDescriptor, psi: PsiElement): TypeElement? {
        val name = ClassLikePsi.descriptorDisplayName(descriptor, psi)
        if (name.isBlank()) return null
        val virtualFile = psi.containingFile?.virtualFile
        val qualifiedName = ClassLikePsi.describeQualifiedName(psi)
        val (line, column) = computeLineColumn(psi)
        return TypeElement(
            name = name,
            qualifiedName = qualifiedName,
            enclosingScope = if (qualifiedName == null) PsiUtils.getEnclosingScope(psi) else null,
            kind = ClassLikePsi.describeKind(psi),
            file = virtualFile?.let { ProjectUtils.getRelativePath(psi.project, it) },
            line = line,
            column = column,
            supertypes = null
        )
    }
}
