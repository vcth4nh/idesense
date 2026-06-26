package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.handlers.displayLanguageName
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.FileStructureResult
import com.github.vcth4nh.idesense.tools.models.StructureNode
import com.github.vcth4nh.idesense.tools.navigation.structure.UniversalModifiers
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.github.vcth4nh.idesense.util.TreeFormatter
import com.intellij.ide.structureView.StructureViewModel
import com.intellij.ide.structureView.StructureViewTreeElement
import com.intellij.ide.structureView.TreeBasedStructureViewBuilder
import com.intellij.ide.structureView.newStructureView.TreeActionsOwner
import com.intellij.ide.structureView.newStructureView.TreeModelWrapper
import com.intellij.ide.util.treeView.AbstractTreeNode
import com.intellij.ide.util.treeView.smartTree.Group
import com.intellij.ide.util.treeView.smartTree.ProvidingTreeModel
import com.intellij.ide.util.treeView.smartTree.SmartTreeStructure
import com.intellij.ide.util.treeView.smartTree.TreeAction
import com.intellij.lang.LanguageStructureViewBuilder
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive

/**
 * Reports the hierarchical structure of a file, mirroring the IDE's Structure view.
 *
 * Drives the IDE's own structure-view machinery (`LanguageStructureViewBuilder` →
 * `TreeModelWrapper` + `SmartTreeStructure`), so filters, node providers, and groupers
 * registered by each language plugin are honored. The optional `show` parameter selects
 * which named categories are visible; defaults are tuned for agent code-reading rather
 * than the IDE's human-skimming defaults.
 */
class FileStructureTool : AbstractMcpTool() {

    override val name = "ide_file_structure"

    override val description = """
        Get the hierarchical outline of a source file, mirroring the IDE's Structure tool window.
        Use over ide_read_file when you need a quick structural overview (classes, methods, fields)
        without reading all the code; use ide_read_file when you need the actual source text.

        Returns: an indented tree with element names, optional signatures, line numbers, and
        visibility modifiers — driven by the IDE's own StructureViewBuilder for the file's language.

        Supports per-language category filters (show) and visibility sort; see property descriptions
        for per-language filter names.

        Gotchas: disabled by default — must be enabled in Settings → IdeSense. Languages:
        Java, Kotlin, Python, JS/TS, Go, PHP, Rust. Other file types return an error if the IDE has
        no structure view for them.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .file(description = "Path to file relative to project root (e.g., 'src/main/java/com/example/MyClass.java'). REQUIRED.")
        .stringArrayProperty(
            "show",
            "Optional list of filter category names to show. Omit to use language defaults. Pass an " +
                "explicit array to override (anything not listed is hidden). Per-language values " +
                "(* = on by default): python: fields*, inherited; java: anonymous_classes, fields*, " +
                "inherited, lambdas*, non_public*; kotlin: inherited, non_public*, properties*; " +
                "javascript/typescript: fields*, inherited, inherited_from_object*; " +
                "php: anonymous_classes, inherited, lambdas*, constants*, includes*, private_members*, " +
                "properties*, protected_members*; go: package_structure*, private_members*; " +
                "rust: macro_expanded.",
        )
        .enumProperty(
            "sort",
            "Optional sort order. Default: declaration order. 'visibility' groups public/exported " +
                "members before non-public. No-op for Python and JS/TS.",
            listOf("visibility"),
        )
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val file = arguments["file"]?.jsonPrimitive?.content
            ?: return createErrorResult("Missing required parameter: file")

        val showOverride: Set<String>? = (arguments["show"] as? JsonArray)
            ?.mapNotNull { it.jsonPrimitive.contentOrNull }
            ?.toSet()
        val sortOrder: String? = arguments["sort"]?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotBlank() }

        return suspendingReadAction {
            val psiFile = getPsiFile(project, file)
                ?: return@suspendingReadAction createErrorResult("File not found: $file")

            val builder = LanguageStructureViewBuilder.getInstance().getStructureViewBuilder(psiFile)
                ?: return@suspendingReadAction createErrorResult(
                    "No structure view available for language '${psiFile.language.id}'."
                )

            val nodes = extractStructure(builder, psiFile, project, showOverride, sortOrder)

            if (nodes.isEmpty()) {
                return@suspendingReadAction createSuccessResult(
                    "File is empty or has no parseable structure.\n\n" +
                        "File: ${psiFile.name}\n" +
                        "Language: ${psiFile.language.id}"
                )
            }

            createJsonResult(FileStructureResult(
                file = file,
                language = displayLanguageName(psiFile.language.id),
                structure = TreeFormatter.format(nodes, psiFile.name)
            ))
        }
    }

    private fun extractStructure(
        builder: com.intellij.ide.structureView.StructureViewBuilder,
        psiFile: PsiFile,
        project: Project,
        showOverride: Set<String>?,
        sortOrder: String?,
    ): List<StructureNode> {
        // Canonicalize JS/TS dialect ids ("ECMAScript 6", "JSX Harmony", "TypeScript JSX")
        // through `displayLanguageName` so the MATCHERS / DEFAULTS lookup hits a single key.
        val canonicalKey = displayLanguageName(psiFile.language.id).lowercase()

        if (builder !is TreeBasedStructureViewBuilder) {
            // Fallback: full StructureView (rare). No filter support here.
            val view = builder.createStructureView(/* fileEditor = */ null, project)
            try {
                return walkAbstractTreeNode(
                    SmartTreeStructure(project, view.treeModel).rootElement as AbstractTreeNode<*>,
                    project,
                )
            } finally {
                Disposer.dispose(view)
            }
        }

        val model = builder.createStructureViewModel(/* editor = */ null)
        try {
            val effectiveShow = showOverride ?: DEFAULTS[canonicalKey] ?: emptySet()
            val activeIdeNames = computeActiveIdeNames(model, canonicalKey, effectiveShow, sortOrder)
            val owner = ShowBasedActionsOwner(activeIdeNames)
            val wrappedModel = TreeModelWrapper(model, owner)
            val structure = SmartTreeStructure(project, wrappedModel)
            val root = structure.rootElement as? AbstractTreeNode<*> ?: return emptyList()
            return walkAbstractTreeNode(root, project)
        } finally {
            Disposer.dispose(model)
        }
    }

    /**
     * Decide which IDE action names should report `isActionActive == true` to `TreeModelWrapper`.
     *
     * `TreeModelWrapper.getFilters()` returns filters whose name is "active" — those are the
     * filters that get APPLIED. `Filter.isVisible(elem) == false` then HIDES that element. So:
     *
     * - For a hide-style filter (i.e. `Filter` with `isReverted() == true`, the standard
     *   convention for "Show X" toggles): the filter is APPLIED → category HIDDEN. Our `show`
     *   list names the categories the user wants VISIBLE, so we mark the filter active iff
     *   the category is *not* in `show` (active = applied = hidden).
     *
     * - For node providers and groupers (and the rare non-reverted filter): being "active"
     *   means the action runs and ADDS / TRANSFORMS nodes. Listing in `show` should activate.
     *
     * - For sorters: hidden sorters (`isVisible() == false`) always apply silently. Visible
     *   sorters apply only when active. The `sort` argument names a single visible sorter to
     *   activate; we match it by pattern across `model.sorters`.
     */
    private fun computeActiveIdeNames(
        model: StructureViewModel,
        languageId: String,
        show: Set<String>,
        sort: String?,
    ): Set<String> {
        val active = mutableSetOf<String>()
        val matchers = MATCHERS[languageId]
        if (matchers != null) {
            val allActions: Sequence<TreeAction> = sequence {
                yieldAll(model.filters.asSequence())
                (model as? ProvidingTreeModel)?.nodeProviders?.let { yieldAll(it) }
                yieldAll(model.groupers.asSequence())
            }
            for (action in allActions) {
                val ideName = action.name
                val matched = matchers.firstOrNull { matcher ->
                    matcher.patterns.any { ideName.contains(it, ignoreCase = true) }
                } ?: continue
                val isHideFilter = action is com.intellij.ide.util.treeView.smartTree.Filter && action.isReverted()
                val shouldBeActive = if (isHideFilter) {
                    matched.normalized !in show
                } else {
                    matched.normalized in show
                }
                if (shouldBeActive) active.add(ideName)
            }
        }
        if (sort != null) {
            val patterns = SORTER_PATTERNS[sort]
            if (patterns != null) {
                for (sorter in model.sorters) {
                    val ideName = sorter.name
                    if (patterns.any { ideName.contains(it, ignoreCase = true) }) {
                        active.add(ideName)
                    }
                }
            }
        }
        return active
    }

    private fun walkAbstractTreeNode(
        node: AbstractTreeNode<*>,
        project: Project,
    ): List<StructureNode> =
        node.children.mapNotNull { walkChildNode(it, project) }

    private fun walkChildNode(
        node: AbstractTreeNode<*>,
        project: Project,
    ): StructureNode? {
        val (rawValue, presentation, line) = when (val value = node.value) {
            is StructureViewTreeElement -> {
                val l = (value.value as? PsiElement)?.let { lineOf(project, it) } ?: 1
                Triple<Any?, _, _>(value.value, value.presentation, l)
            }
            is Group -> Triple<Any?, _, _>(value, value.presentation, 1)
            else -> return null
        }
        val name = presentation.presentableText?.takeIf { it.isNotBlank() } ?: return null
        return StructureNode(
            name = name,
            modifiers = UniversalModifiers.extract(rawValue),
            signature = presentation.locationString?.takeIf { it.isNotBlank() },
            line = line,
            children = walkAbstractTreeNode(node, project),
        )
    }

    private fun lineOf(project: Project, psi: PsiElement): Int {
        val containingFile = psi.containingFile ?: return 1
        val document = PsiDocumentManager.getInstance(project).getDocument(containingFile) ?: return 1
        val offset = psi.textOffset
        if (offset < 0 || offset > document.textLength) return 1
        return document.getLineNumber(offset) + 1
    }

    private data class FilterCategoryMatcher(val normalized: String, val patterns: List<String>)

    /**
     * `TreeActionsOwner` reports a `TreeAction` as "user-active" when its underlying
     * IDE-side action name is in our derived active-set. The `TreeModelWrapper.isActive`
     * convention then translates this to the right toolbar-style state for filters
     * (with `isReverted=true`), node providers, and groupers — reproducing what the
     * IDE does when the user toggles the corresponding button.
     */
    private class ShowBasedActionsOwner(
        private val activeIdeNames: Set<String>,
    ) : TreeActionsOwner {
        override fun isActionActive(name: String): Boolean = name in activeIdeNames
        override fun setActionActive(name: String, state: Boolean) { /* no-op */ }
    }

    companion object {
        // Keys are `psiFile.language.id.lowercase()` — language IDs vary in case across plugins
        // (`JAVA`, `Python`, `kotlin`, `JavaScript`, `PHP`, `go`, `Rust`) so we normalize on lookup.
        // Match-pattern lists are ordered: more-specific first (e.g., `inherited_from_object`
        // before `inherited`) since the first match wins.
        private val MATCHERS: Map<String, List<FilterCategoryMatcher>> = mapOf(
            "python" to listOf(
                FilterCategoryMatcher("fields", listOf("FIELD")),
                FilterCategoryMatcher("inherited", listOf("INHERITED")),
            ),
            "java" to listOf(
                FilterCategoryMatcher("non_public", listOf("NON_PUBLIC", "non.public")),
                FilterCategoryMatcher("anonymous_classes", listOf("ANONYMOUS")),
                FilterCategoryMatcher("lambdas", listOf("LAMBDA")),
                FilterCategoryMatcher("fields", listOf("FIELD")),
                FilterCategoryMatcher("inherited", listOf("INHERITED")),
            ),
            "kotlin" to listOf(
                FilterCategoryMatcher("non_public", listOf("NON_PUBLIC", "non.public")),
                FilterCategoryMatcher("properties", listOf("PROPERTIES", "PROPERT")),
                FilterCategoryMatcher("inherited", listOf("INHERITED")),
            ),
            "javascript" to listOf(
                FilterCategoryMatcher("inherited_from_object", listOf("OBJECT")),
                FilterCategoryMatcher("fields", listOf("FIELD")),
                FilterCategoryMatcher("inherited", listOf("INHERITED")),
            ),
            "typescript" to listOf(
                FilterCategoryMatcher("inherited_from_object", listOf("OBJECT")),
                FilterCategoryMatcher("fields", listOf("FIELD")),
                FilterCategoryMatcher("inherited", listOf("INHERITED")),
            ),
            "php" to listOf(
                FilterCategoryMatcher("anonymous_classes", listOf("ANONYMOUS")),
                FilterCategoryMatcher("private_members", listOf("PRIVATE")),
                FilterCategoryMatcher("protected_members", listOf("PROTECTED")),
                FilterCategoryMatcher("constants", listOf("CONSTANT")),
                FilterCategoryMatcher("includes", listOf("INCLUDE")),
                FilterCategoryMatcher("lambdas", listOf("LAMBDA")),
                FilterCategoryMatcher("properties", listOf("PROPERTIES", "PROPERT")),
                FilterCategoryMatcher("inherited", listOf("INHERITED")),
            ),
            "go" to listOf(
                FilterCategoryMatcher("package_structure", listOf("PACKAGE")),
                FilterCategoryMatcher("private_members", listOf("PRIVATE")),
            ),
            "rust" to listOf(
                FilterCategoryMatcher("macro_expanded", listOf("MACRO_EXPANDED")),
            ),
        )

        // Sorter name patterns indexed by user-facing key. Patterns match across all
        // languages because the IDE settled on a small handful of conventional ids:
        //   Java/PHP  → VISIBILITY_SORTER
        //   Kotlin    → KOTLIN_VISIBILITY_SORTER
        //   Go        → EXPORTABILITY_SORTER (Go's flavor of "visibility")
        //   Rust      → STRUCTURE_VIEW_VISIBILITY_SORTER
        // Python and JS/TS don't ship a visibility sorter, so 'visibility' is a no-op there.
        private val SORTER_PATTERNS: Map<String, List<String>> = mapOf(
            "visibility" to listOf("VISIBILITY", "EXPORTABILITY"),
        )

        private val DEFAULTS: Map<String, Set<String>> = mapOf(
            "python" to setOf("fields"),
            "java" to setOf("non_public", "fields", "lambdas"),
            "kotlin" to setOf("non_public", "properties"),
            "javascript" to setOf("fields", "inherited_from_object"),
            "typescript" to setOf("fields", "inherited_from_object"),
            "php" to setOf(
                "constants", "includes", "lambdas", "private_members", "properties", "protected_members"
            ),
            "go" to setOf("package_structure", "private_members"),
            // Rust intentionally absent — no filters
        )
    }
}
