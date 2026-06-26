package com.github.vcth4nh.idesense.tools.navigation.hierarchy

import com.github.vcth4nh.idesense.handlers.TypeElementData
import com.github.vcth4nh.idesense.handlers.TypeHierarchyData
import com.github.vcth4nh.idesense.handlers.shouldIncludeNavigationElement
import com.github.vcth4nh.idesense.util.PluginDetectors
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.search.searches.DefinitionsScopedSearch
import com.intellij.psi.search.searches.ReferencesSearch
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.util.Processor

/**
 * Relocated algorithm from the former RustTypeHierarchyHandler.
 *
 * Handles Rust-specific type relationships:
 * - **For Traits**: Shows supertraits and implementing types
 * - **For Structs/Enums**: Shows implemented traits (via impl blocks)
 * - **For Impl Blocks**: Shows the trait/type relationship
 *
 * Note: Rust does NOT have class inheritance. Composition and trait
 * implementations are the primary mechanisms for code reuse.
 *
 * Self-contained: all Rust PSI reflection utilities are inlined here
 * (previously inherited from BaseRustHandler which was deleted).
 */
internal class RustTypeHierarchyImpl {

    companion object {
        private const val MAX_HIERARCHY_DEPTH = 50
        private val LOG = logger<RustTypeHierarchyImpl>()
    }

    // Lazy-loaded Rust PSI classes via reflection

    private val rsStructItemClass: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsStructItem") }
    val rsTraitItemClass: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsTraitItem") }
    private val rsImplItemClass: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsImplItem") }
    private val rsEnumItemClass: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsEnumItem") }
    private val rsFunctionClass: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsFunction") }
    private val rsModItemClass: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsModItem") }

    private val rsNamedElementIndexClass: Class<*>? by lazy {
        loadClass("org.rust.lang.core.psi.ext.RsNamedElementIndex")
    }

    private fun loadClass(className: String): Class<*>? {
        return try {
            Class.forName(className)
        } catch (_: ClassNotFoundException) {
            LOG.debug("$className not found")
            null
        }
    }

    // Type checking helpers

    private fun isRustLanguage(element: PsiElement): Boolean = element.language.id == "Rust"
    private fun isRsTrait(element: PsiElement): Boolean = rsTraitItemClass?.isInstance(element) == true
    private fun isRsStruct(element: PsiElement): Boolean = rsStructItemClass?.isInstance(element) == true
    private fun isRsEnum(element: PsiElement): Boolean = rsEnumItemClass?.isInstance(element) == true
    private fun isRsImpl(element: PsiElement): Boolean = rsImplItemClass?.isInstance(element) == true
    private fun isRsFunction(element: PsiElement): Boolean = rsFunctionClass?.isInstance(element) == true
    private fun isRsMod(element: PsiElement): Boolean = rsModItemClass?.isInstance(element) == true

    // Navigation helpers

    private fun findContainingRsTrait(element: PsiElement): PsiElement? {
        if (isRsTrait(element)) return element
        val cls = rsTraitItemClass ?: return null
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, cls as Class<out PsiElement>)
    }

    private fun findContainingRsImpl(element: PsiElement): PsiElement? {
        if (isRsImpl(element)) return element
        val cls = rsImplItemClass ?: return null
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, cls as Class<out PsiElement>)
    }

    private fun findContainingRsStruct(element: PsiElement): PsiElement? {
        if (isRsStruct(element)) return element
        val cls = rsStructItemClass ?: return null
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, cls as Class<out PsiElement>)
    }

    private fun findContainingRsEnum(element: PsiElement): PsiElement? {
        if (isRsEnum(element)) return element
        val cls = rsEnumItemClass ?: return null
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, cls as Class<out PsiElement>)
    }

    // Reflection-based API calls

    private fun getName(element: PsiElement): String? {
        return try {
            element.javaClass.getMethod("getName").invoke(element) as? String
        } catch (_: Exception) {
            null
        }
    }

    private fun getTraitRef(implItem: PsiElement): PsiElement? {
        return try {
            implItem.javaClass.getMethod("getTraitRef").invoke(implItem) as? PsiElement
        } catch (_: Exception) {
            null
        }
    }

    private fun getTypeReference(implItem: PsiElement): PsiElement? {
        return try {
            implItem.javaClass.getMethod("getTypeReference").invoke(implItem) as? PsiElement
        } catch (_: Exception) {
            null
        }
    }

    private fun getSuperTraits(traitItem: PsiElement): List<PsiElement>? {
        return try {
            @Suppress("UNCHECKED_CAST")
            traitItem.javaClass.getMethod("getSuperTraits").invoke(traitItem) as? List<PsiElement>
        } catch (_: Exception) {
            try {
                @Suppress("UNCHECKED_CAST")
                traitItem.javaClass.getMethod("getTypeParamBounds").invoke(traitItem) as? List<PsiElement>
            } catch (_: Exception) {
                null
            }
        }
    }

    /**
     * Resolves a reference to its target element.
     *
     * Tries three strategies in order:
     *  1. `element.getReference().resolve()` -- direct path resolution.
     *  2. `element.resolve()` -- for elements that expose resolve directly.
     *  3. `element.getPath().getReference().resolve()` -- navigates through the
     *     embedded `RsPath` for wrapper PSI like `RsTraitRef` and `RsTypeReference`.
     */
    private fun resolveReference(element: PsiElement): PsiElement? {
        runCatching {
            val ref = element.javaClass.getMethod("getReference").invoke(element) as? com.intellij.psi.PsiReference
            ref?.resolve()
        }.getOrNull()?.let { return it }

        runCatching {
            element.javaClass.getMethod("resolve").invoke(element) as? PsiElement
        }.getOrNull()?.let { return it }

        runCatching {
            val path = element.javaClass.getMethod("getPath").invoke(element) as? PsiElement
            path?.let { p ->
                val pathRef = p.javaClass.getMethod("getReference").invoke(p) as? com.intellij.psi.PsiReference
                pathRef?.resolve()
            }
        }.getOrNull()?.let { return it }

        return null
    }

    // Utility methods

    private fun getRelativePath(project: Project, file: VirtualFile): String {
        return ProjectUtils.getToolFilePath(project, file)
    }

    private fun getLineNumber(project: Project, element: PsiElement): Int? {
        val psiFile = element.containingFile ?: return null
        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile) ?: return null
        return document.getLineNumber(element.textOffset) + 1
    }

    private fun determineElementKind(element: PsiElement): String {
        return when {
            isRsTrait(element) -> "TRAIT"
            isRsStruct(element) -> "STRUCT"
            isRsEnum(element) -> "ENUM"
            isRsImpl(element) -> "IMPL"
            isRsFunction(element) -> "FUNCTION"
            isRsMod(element) -> "MODULE"
            else -> "SYMBOL"
        }
    }

    // Public API

    fun canHandle(element: PsiElement): Boolean {
        return isAvailable() && isRustLanguage(element)
    }

    fun isAvailable(): Boolean = PluginDetectors.rust.isAvailable && rsTraitItemClass != null

    fun getTypeHierarchy(
        element: PsiElement,
        project: Project,
        scope: HierarchyScope
    ): TypeHierarchyData? {
        LOG.debug("Getting type hierarchy for Rust element at ${element.containingFile?.name}")
        val searchScope = HierarchyScope.resolveGlobalScope(project, scope)

        // Handle traits
        val trait = findContainingRsTrait(element)
        if (trait != null) {
            LOG.debug("Getting hierarchy for trait: ${getName(trait)}")
            return getTraitHierarchy(project, trait, searchScope)
        }

        // Handle structs
        val struct = findContainingRsStruct(element)
        if (struct != null) {
            LOG.debug("Getting hierarchy for struct: ${getName(struct)}")
            return getTypeImplHierarchy(project, struct, searchScope)
        }

        // Handle enums
        val enum = findContainingRsEnum(element)
        if (enum != null) {
            LOG.debug("Getting hierarchy for enum: ${getName(enum)}")
            return getTypeImplHierarchy(project, enum, searchScope)
        }

        // Handle impl blocks
        val impl = findContainingRsImpl(element)
        if (impl != null) {
            LOG.debug("Getting hierarchy for impl block")
            return getImplHierarchy(project, impl, searchScope)
        }

        return null
    }

    private fun getTraitHierarchy(
        project: Project,
        trait: PsiElement,
        searchScope: GlobalSearchScope
    ): TypeHierarchyData {
        val supertypes = getSupertraitHierarchy(project, trait, mutableSetOf(), searchScope = searchScope)
        val subtypes = getImplementingTypes(project, trait, searchScope)

        LOG.debug("Found ${supertypes.size} supertraits and ${subtypes.size} implementing types")

        return TypeHierarchyData(
            element = TypeElementData(
                name = getName(trait) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(trait),
                file = trait.containingFile?.virtualFile?.let { getRelativePath(project, it) },
                line = getLineNumber(project, trait),
                kind = "TRAIT",
                language = "Rust",
                psi = trait
            ),
            supertypes = supertypes,
            subtypes = subtypes
        )
    }

    private fun getSupertraitHierarchy(
        project: Project,
        trait: PsiElement,
        visited: MutableSet<String>,
        depth: Int = 0,
        searchScope: GlobalSearchScope
    ): List<TypeElementData> {
        if (depth > MAX_HIERARCHY_DEPTH) return emptyList()

        val traitName = getName(trait) ?: return emptyList()
        if (traitName in visited) return emptyList()
        visited.add(traitName)

        val supertypes = mutableListOf<TypeElementData>()

        try {
            val superTraits = getSuperTraits(trait) ?: emptyList()
            for (superTraitRef in superTraits) {
                val resolved = resolveReference(superTraitRef)
                if (
                    resolved != null &&
                    isRsTrait(resolved) &&
                    shouldIncludeNavigationElement(searchScope, resolved)
                ) {
                    val resolvedName = getName(resolved) ?: continue
                    if (resolvedName !in visited) {
                        val nestedSupertypes = getSupertraitHierarchy(project, resolved, visited, depth + 1, searchScope)
                        supertypes.add(TypeElementData(
                            name = resolvedName,
                            qualifiedName = QualifiedNameUtil.getQualifiedName(resolved),
                            file = resolved.containingFile?.virtualFile?.let { getRelativePath(project, it) },
                            line = getLineNumber(project, resolved),
                            kind = "TRAIT",
                            language = "Rust",
                            supertypes = nestedSupertypes.takeIf { it.isNotEmpty() },
                            psi = resolved
                        ))
                    }
                }
            }
        } catch (e: Exception) {
            LOG.debug("Error getting supertraits: ${e.message}")
        }

        return supertypes
    }

    /**
     * Looks up a Rust struct by name via RsNamedElementIndex.
     *
     * Used as a fallback when reference resolution fails on an impl's type reference,
     * to avoid tagging clearly-named types as kind: IMPL.
     */
    private fun lookupStructByName(project: Project, name: String): PsiElement? {
        val indexClass = rsNamedElementIndexClass ?: return null
        return try {
            val getInstanceMethod = indexClass.getMethod("getInstance")
            val instance = getInstanceMethod.invoke(null)
            val findMethod = instance.javaClass.getMethod("findElementsByName", Project::class.java, String::class.java)
            val results = findMethod.invoke(instance, project, name) as? Collection<*>
            results?.filterIsInstance<PsiElement>()?.firstOrNull { isRsStruct(it) }
        } catch (_: Exception) {
            null
        }
    }

    private fun getImplementingTypes(
        project: Project,
        trait: PsiElement,
        searchScope: GlobalSearchScope
    ): List<TypeElementData> {
        val results = mutableListOf<TypeElementData>()

        try {
            DefinitionsScopedSearch.search(trait, searchScope).forEach(Processor { definition ->
                if (isRsImpl(definition) && shouldIncludeNavigationElement(searchScope, definition)) {
                    val typeRef = getTypeReference(definition)
                    if (typeRef != null) {
                        var resolvedType = resolveReference(typeRef)
                        val typeName = resolvedType?.let { getName(it) } ?: typeRef.text?.trim()

                        if (resolvedType == null && typeName != null) {
                            resolvedType = lookupStructByName(project, typeName)
                        }

                        if (typeName != null && resolvedType != null) {
                            results.add(TypeElementData(
                                name = typeName,
                                qualifiedName = QualifiedNameUtil.getQualifiedName(resolvedType),
                                file = resolvedType.containingFile?.virtualFile?.let { getRelativePath(project, it) },
                                line = getLineNumber(project, resolvedType),
                                kind = determineElementKind(resolvedType),
                                language = "Rust",
                                psi = resolvedType
                            ))
                        }
                    }
                }
                results.size < 100
            })

            LOG.debug("Found ${results.size} implementing types via DefinitionsScopedSearch")
        } catch (e: Exception) {
            LOG.debug("Error getting implementing types: ${e.message}")
        }

        return results
    }

    private fun getTypeImplHierarchy(
        project: Project,
        type: PsiElement,
        searchScope: GlobalSearchScope
    ): TypeHierarchyData {
        val implementedTraits = findImplementedTraits(project, type, searchScope)

        return TypeHierarchyData(
            element = TypeElementData(
                name = getName(type) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(type),
                file = type.containingFile?.virtualFile?.let { getRelativePath(project, it) },
                line = getLineNumber(project, type),
                kind = determineElementKind(type),
                language = "Rust",
                psi = type
            ),
            supertypes = implementedTraits,
            subtypes = emptyList()
        )
    }

    private fun findImplementedTraits(
        project: Project,
        type: PsiElement,
        searchScope: GlobalSearchScope
    ): List<TypeElementData> {
        val results = mutableListOf<TypeElementData>()

        try {
            ReferencesSearch.search(type, searchScope).forEach(Processor { reference ->
                val impl = findContainingRsImpl(reference.element)
                if (impl != null && shouldIncludeNavigationElement(searchScope, impl)) {
                    val traitRef = getTraitRef(impl)
                    if (traitRef != null) {
                        val resolvedTrait = resolveReference(traitRef)
                        if (resolvedTrait != null) {
                            val traitName = getName(resolvedTrait)
                            if (traitName != null && results.none { it.name == traitName }) {
                                results.add(TypeElementData(
                                    name = traitName,
                                    qualifiedName = QualifiedNameUtil.getQualifiedName(resolvedTrait),
                                    file = resolvedTrait.containingFile?.virtualFile?.let { getRelativePath(project, it) },
                                    line = getLineNumber(project, resolvedTrait),
                                    kind = "TRAIT",
                                    language = "Rust",
                                    psi = resolvedTrait
                                ))
                            }
                        }
                    }
                }
                results.size < 100
            })
        } catch (e: Exception) {
            LOG.debug("Error finding implemented traits: ${e.message}")
        }

        return results
    }

    private fun getImplHierarchy(
        project: Project,
        impl: PsiElement,
        searchScope: GlobalSearchScope
    ): TypeHierarchyData {
        val traitRef = getTraitRef(impl)
        val typeRef = getTypeReference(impl)

        val supertypes = mutableListOf<TypeElementData>()
        val subtypes = mutableListOf<TypeElementData>()

        if (traitRef != null) {
            val resolvedTrait = resolveReference(traitRef)
            if (resolvedTrait != null && shouldIncludeNavigationElement(searchScope, resolvedTrait)) {
                val traitName = getName(resolvedTrait)
                if (traitName != null) {
                    supertypes.add(TypeElementData(
                        name = traitName,
                        qualifiedName = QualifiedNameUtil.getQualifiedName(resolvedTrait),
                        file = resolvedTrait.containingFile?.virtualFile?.let { getRelativePath(project, it) },
                        line = getLineNumber(project, resolvedTrait),
                        kind = "TRAIT",
                        language = "Rust",
                        psi = resolvedTrait
                    ))
                }
            }
        }

        if (typeRef != null) {
            val resolvedType = resolveReference(typeRef)
            if (resolvedType != null && shouldIncludeNavigationElement(searchScope, resolvedType)) {
                val typeName = getName(resolvedType)
                if (typeName != null) {
                    subtypes.add(TypeElementData(
                        name = typeName,
                        qualifiedName = QualifiedNameUtil.getQualifiedName(resolvedType),
                        file = resolvedType.containingFile?.virtualFile?.let { getRelativePath(project, it) },
                        line = getLineNumber(project, resolvedType),
                        kind = determineElementKind(resolvedType),
                        language = "Rust",
                        psi = resolvedType
                    ))
                }
            }
        }

        val implName = buildImplName(traitRef, typeRef)

        return TypeHierarchyData(
            element = TypeElementData(
                name = implName,
                qualifiedName = null,
                file = impl.containingFile?.virtualFile?.let { getRelativePath(project, it) },
                line = getLineNumber(project, impl),
                kind = "IMPL",
                language = "Rust",
                psi = impl
            ),
            supertypes = supertypes,
            subtypes = subtypes
        )
    }

    private fun buildImplName(traitRef: PsiElement?, typeRef: PsiElement?): String {
        val traitName = traitRef?.text?.trim()
        val typeName = typeRef?.text?.trim()

        return when {
            traitName != null && typeName != null -> "impl $traitName for $typeName"
            typeName != null -> "impl $typeName"
            else -> "impl"
        }
    }
}
