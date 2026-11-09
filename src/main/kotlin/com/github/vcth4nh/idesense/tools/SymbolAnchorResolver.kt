package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.handlers.BuiltInSearchScope
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScopeResolver
import com.github.vcth4nh.idesense.handlers.PopupFaithfulSymbolSearch
import com.github.vcth4nh.idesense.handlers.SameNameSymbolOrder
import com.github.vcth4nh.idesense.handlers.SymbolData
import com.github.vcth4nh.idesense.handlers.SymbolDataConverter
import com.github.vcth4nh.idesense.tools.models.SymbolMatch
import com.github.vcth4nh.idesense.tools.navigation.hierarchy.ClassLikePsi
import com.github.vcth4nh.idesense.util.ClassResolver
import com.intellij.navigation.NavigationItem
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFileSystemItem
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.search.GlobalSearchScope

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
 *
 * Two provider quirks are corrected on the exact-name path: a file or directory hit (the Java
 * provider's last fallback resolves paths) is not a symbol and falls through to the popup, and
 * a qualified method name without a parameter list that has same-name overloads returns the
 * overloads as candidates instead of the provider's first element.
 */
internal object SymbolAnchorResolver {
    internal const val MAX_CANDIDATES = 10

    private data class Match(val element: PsiElement, val data: SymbolData)

    fun resolve(project: Project, symbol: String): SymbolResolution {
        val scope = BuiltInSearchScopeResolver.resolveGlobalScope(project, BuiltInSearchScope.PROJECT_FILES)

        val exact = ClassResolver.findClassByName(project, symbol)
        if (exact != null && exact !is PsiFileSystemItem) {
            overloadsOf(exact, symbol, project, scope)?.let { return it }
            return SymbolResolution.Resolved(exact)
        }

        val popup = PopupFaithfulSymbolSearch.search(project, symbol, scope, MAX_CANDIDATES * 4)
        val matches = popup.candidates
            .mapNotNull { candidate ->
                val data = SymbolDataConverter.convert(candidate.item, project, scope) ?: return@mapNotNull null
                if (!data.name.equals(popup.localPattern, ignoreCase = true)) return@mapNotNull null
                val element = candidate.item as? PsiElement ?: extractPsiElement(candidate.item) ?: return@mapNotNull null
                Match(element, data)
            }
            .distinctBy { "${it.data.file}:${it.data.line}:${it.data.column}:${it.data.name}" }

        return when (matches.size) {
            0 -> SymbolResolution.NotFound
            1 -> SymbolResolution.Resolved(matches.single().element)
            else -> ambiguous(matches)
        }
    }

    /**
     * Same-name method-like siblings of a qualified-name hit given without a parameter list
     * (e.g. `demo.Quirks#parse`): the provider picked one overload silently, so report them all.
     * A pattern with a parameter list (`demo.Quirks#parse(java.lang.String)`) selects exactly.
     */
    private fun overloadsOf(hit: PsiElement, symbol: String, project: Project, scope: GlobalSearchScope): SymbolResolution? {
        if (symbol.contains('(') || !ClassLikePsi.isMethodLike(hit)) return null
        val name = (hit as? PsiNamedElement)?.name ?: return null
        val siblings = hit.parent?.children.orEmpty().filter {
            it !== hit && it is PsiNamedElement && it.name == name && ClassLikePsi.isMethodLike(it)
        }
        if (siblings.isEmpty()) return null
        val matches = (listOf(hit) + siblings).mapNotNull { element ->
            val item = element as? NavigationItem ?: return@mapNotNull null
            SymbolDataConverter.convert(item, project, scope)?.let { Match(element, it) }
        }
        return if (matches.size > 1) ambiguous(matches) else null
    }

    private fun ambiguous(matches: List<Match>): SymbolResolution.Ambiguous =
        SymbolResolution.Ambiguous(
            SameNameSymbolOrder.sort(matches) { match -> match.data }.take(MAX_CANDIDATES).map { match ->
                SymbolMatch(
                    name = match.data.name,
                    qualifiedName = match.data.qualifiedName,
                    kind = match.data.kind,
                    file = match.data.file,
                    line = match.data.line,
                    column = match.data.column,
                )
            }
        )

    private fun extractPsiElement(item: NavigationItem): PsiElement? = try {
        item.javaClass.getMethod("getElement").invoke(item) as? PsiElement
    } catch (_: Exception) {
        null
    }
}
