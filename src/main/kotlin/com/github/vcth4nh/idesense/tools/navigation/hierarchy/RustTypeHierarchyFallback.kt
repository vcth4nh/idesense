package com.github.vcth4nh.idesense.tools.navigation.hierarchy

import com.intellij.ide.hierarchy.HierarchyNodeDescriptor
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement

/**
 * One-off Strategy II fallback: Rust ships no LanguageTypeHierarchy provider
 * (audit 2026-05-04 §3.4 + research-time confirmation). This object adapts the
 * relocated [RustTypeHierarchyImpl] (formerly `RustTypeHierarchyHandler`) to the
 * walker's `Result<HierarchyNodeDescriptor>` return type by synthesizing
 * descriptors for the algorithm's PSI-element children.
 */
internal object RustTypeHierarchyFallback {

    fun walk(
        project: Project,
        element: PsiElement,
        kind: HierarchyKind,
        scope: HierarchyScope,
        maxDepth: Int
    ): Result<HierarchyWalkResult> {
        if (!kind.isType) {
            return Result.failure(IllegalStateException("RustTypeHierarchyFallback called with non-type kind: $kind"))
        }
        val data = RustTypeHierarchyImpl().getTypeHierarchy(element, project, scope)
            ?: return Result.failure(IllegalStateException("Rust type hierarchy: could not extract class info"))

        val rootDescriptor = SyntheticDescriptor(project, element)
        val children = when (kind) {
            HierarchyKind.SUPERTYPES -> data.supertypes
            HierarchyKind.SUBTYPES -> data.subtypes
            else -> error("unreachable")  // guarded by isType check above
        }
        rootDescriptor.setCachedChildren(
            children
                .mapNotNull { entry -> entry.psi?.let { SyntheticDescriptor(project, it) } }
                .toTypedArray<Any>()
        )
        // Synthetic descriptors carry the right PSI element directly, so use the identity resolver.
        return Result.success(HierarchyWalkResult(rootDescriptor, IdentityElementResolver))
    }

    /**
     * Concrete [HierarchyNodeDescriptor] subclass for synthesizing nodes from a
     * raw [PsiElement] — used because [HierarchyNodeDescriptor] is abstract.
     */
    private class SyntheticDescriptor(project: Project, psi: PsiElement) :
        HierarchyNodeDescriptor(project, /* parentDescriptor = */ null, psi, /* isBase = */ true)
}
