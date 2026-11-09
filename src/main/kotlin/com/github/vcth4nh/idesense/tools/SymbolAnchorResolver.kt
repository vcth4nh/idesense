package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.handlers.BuiltInSearchScope
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScopeResolver
import com.github.vcth4nh.idesense.handlers.PopupFaithfulSymbolSearch
import com.github.vcth4nh.idesense.handlers.SameNameSymbolOrder
import com.github.vcth4nh.idesense.handlers.SymbolData
import com.github.vcth4nh.idesense.handlers.SymbolDataConverter
import com.github.vcth4nh.idesense.tools.models.SymbolMatch
import com.github.vcth4nh.idesense.util.ClassResolver
import com.intellij.navigation.NavigationItem
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement

/** Outcome of [SymbolAnchorResolver.resolve]. */
internal sealed interface SymbolResolution {
    data class Resolved(val element: PsiElement) : SymbolResolution
    data class Ambiguous(val candidates: List<SymbolMatch>) : SymbolResolution
    data object NotFound : SymbolResolution
}

/**
 * Resolves a symbol name to its declaration: exact qualified-name lookup first
 * (ClassResolver, so library FQNs work), then the Go to Symbol popup stack with the
 * same exact-name filter ide_find_symbol applies when fuzzySearch=false.
 *
 * Shared by ide_explain_symbol (#41), the ide_type_hierarchy className shortcut (#59) and
 * the symbol anchor of ide_call_hierarchy / ide_find_usages (#40). Call inside a read action.
 */
internal object SymbolAnchorResolver {
    internal const val MAX_CANDIDATES = 10

    fun resolve(project: Project, symbol: String): SymbolResolution {
        ClassResolver.findClassByName(project, symbol)?.let { return SymbolResolution.Resolved(it) }

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
            .let { SameNameSymbolOrder.sort(it) { match -> match.data } }

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
}
