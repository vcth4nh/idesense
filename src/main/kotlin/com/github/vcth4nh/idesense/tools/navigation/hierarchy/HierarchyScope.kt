package com.github.vcth4nh.idesense.tools.navigation.hierarchy

import com.github.vcth4nh.idesense.constants.ParamNames
import com.intellij.ide.hierarchy.HierarchyBrowserBaseEx
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectRootManager
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.search.DelegatingGlobalSearchScope
import com.intellij.psi.search.GlobalSearchScope
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * The IDE's native hierarchy-scope vocabulary — the scope-type strings on
 * [HierarchyBrowserBaseEx], used by ide_call_hierarchy / ide_type_hierarchy. Distinct from
 * the search tools' BuiltInSearchScope; each value carries the IDE scope-type string the
 * hierarchy browser reads directly.
 *
 * `production` (SCOPE_PROJECT, "Production") is production-sources-only in most language
 * plugins — empty in projects without production source roots (e.g. JS/TS without module
 * setup), identical to the IDE's "Production" tab.
 */
enum class HierarchyScope(val wireValue: String, val ideScopeType: String) {
    ALL("all", HierarchyBrowserBaseEx.SCOPE_ALL),
    PRODUCTION("production", HierarchyBrowserBaseEx.SCOPE_PROJECT),
    TEST("test", HierarchyBrowserBaseEx.SCOPE_TEST),
    THIS_CLASS("this_class", HierarchyBrowserBaseEx.SCOPE_CLASS),
    THIS_MODULE("this_module", HierarchyBrowserBaseEx.SCOPE_MODULE);

    companion object {
        /** Full native set — ide_call_hierarchy (always browser-backed). */
        val CALL_HIERARCHY_SCOPES: List<HierarchyScope> =
            listOf(ALL, PRODUCTION, TEST, THIS_CLASS, THIS_MODULE)

        /**
         * ide_type_hierarchy: `this_class` is degenerate for a type's own hierarchy, and the
         * hand-rolled Rust type fallback cannot resolve the narrowing scopes to a search scope.
         */
        val TYPE_HIERARCHY_SCOPES: List<HierarchyScope> = listOf(ALL, PRODUCTION, TEST)

        fun fromWireValue(value: String): HierarchyScope? =
            values().firstOrNull { it.wireValue == value }

        fun wireValues(scopes: List<HierarchyScope>): List<String> = scopes.map { it.wireValue }

        /** Reads `arguments["scope"]`; defaults to [ALL]; throws IllegalArgumentException on unknown value. */
        fun parse(arguments: JsonObject, default: HierarchyScope = ALL): HierarchyScope {
            val raw = arguments[ParamNames.SCOPE]?.jsonPrimitive?.content ?: return default
            return fromWireValue(raw) ?: throw IllegalArgumentException(
                "Unsupported scope '$raw'. Supported values: ${wireValues(values().toList()).joinToString(", ")}"
            )
        }

        /**
         * GlobalSearchScope for the hand-rolled Rust type-hierarchy fallback (the only
         * non-browser consumer). Only ALL/PRODUCTION/TEST can reach here (type hierarchy
         * restricts to [TYPE_HIERARCHY_SCOPES]); the narrowing scopes degrade to allScope.
         */
        fun resolveGlobalScope(project: Project, scope: HierarchyScope): GlobalSearchScope =
            when (scope) {
                ALL -> GlobalSearchScope.allScope(project)
                PRODUCTION -> projectContentScope(project) { file ->
                    val idx = ProjectRootManager.getInstance(project).fileIndex
                    idx.isInSourceContent(file) && !idx.isInTestSourceContent(file)
                }
                TEST -> projectContentScope(project) { file ->
                    ProjectRootManager.getInstance(project).fileIndex.isInTestSourceContent(file)
                }
                THIS_CLASS, THIS_MODULE -> GlobalSearchScope.allScope(project)
            }

        private fun projectContentScope(
            project: Project,
            predicate: (VirtualFile) -> Boolean
        ): GlobalSearchScope {
            val base = GlobalSearchScope.projectScope(project)
            return object : DelegatingGlobalSearchScope(base) {
                override fun contains(file: VirtualFile): Boolean = super.contains(file) && predicate(file)
            }
        }
    }
}
