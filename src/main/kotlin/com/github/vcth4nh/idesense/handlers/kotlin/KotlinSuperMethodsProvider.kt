package com.github.vcth4nh.idesense.handlers.kotlin

import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.handlers.MethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodsData
import com.github.vcth4nh.idesense.handlers.SuperMethodsProvider
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.find.findUsages.FindUsagesHandler
import com.intellij.find.findUsages.FindUsagesHandlerFactory
import com.intellij.find.findUsages.FindUsagesHandlerFactory.OperationMode
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiReference
import com.intellij.psi.SmartPsiElementPointer
import com.intellij.psi.search.SearchScope
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.usageView.UsageInfo
import com.intellij.util.Processor
import java.util.Collections

/**
 * Kotlin super-methods provider. Delegates to
 * `org.jetbrains.kotlin.idea.codeInsight.SuperDeclarationProvider.findSuperDeclarations`
 * — the Analysis-API-based data layer that backs both K2's GotoSuper handler
 * and `KotlinLineMarkerProvider`'s `I↑` gutter icon. Works under both K1 and K2.
 *
 * Loaded reflectively to avoid a compile-time dep on the Kotlin plugin.
 */
class KotlinSuperMethodsProvider : SuperMethodsProvider {

    companion object {
        private val LOG = logger<KotlinSuperMethodsProvider>()

        private const val PROVIDER_FQN = "org.jetbrains.kotlin.idea.codeInsight.SuperDeclarationProvider"
        private const val KT_DECLARATION_FQN = "org.jetbrains.kotlin.psi.KtDeclaration"
        private const val KT_CALLABLE_DECLARATION_FQN = "org.jetbrains.kotlin.psi.KtCallableDeclaration"
        private const val KT_CLASS_OR_OBJECT_FQN = "org.jetbrains.kotlin.psi.KtClassOrObject"
    }

    private val ktDeclarationClass: Class<*>? by lazy {
        try { Class.forName(KT_DECLARATION_FQN) } catch (_: ClassNotFoundException) { null }
    }

    private val ktCallableDeclarationClass: Class<*>? by lazy {
        try { Class.forName(KT_CALLABLE_DECLARATION_FQN) } catch (_: ClassNotFoundException) { null }
    }

    private val ktClassOrObjectClass: Class<*>? by lazy {
        try { Class.forName(KT_CLASS_OR_OBJECT_FQN) } catch (_: ClassNotFoundException) { null }
    }

    private val providerObject: Any? by lazy {
        try {
            val cls = Class.forName(PROVIDER_FQN)
            cls.getDeclaredField("INSTANCE").get(null)
        } catch (_: Throwable) { null }
    }

    private val findMethod: java.lang.reflect.Method? by lazy {
        try {
            val cls = providerObject?.javaClass ?: return@lazy null
            val ktDecl = ktDeclarationClass ?: return@lazy null
            cls.getMethod("findSuperDeclarations", ktDecl)
        } catch (_: Throwable) { null }
    }

    override fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData? {
        val declaration = resolveKtDeclaration(element) ?: return null
        val isClass = ktClassOrObjectClass?.isInstance(declaration) == true

        val file = declaration.containingFile?.virtualFile
        val methodData = MethodData(
            name = (declaration as? com.intellij.psi.PsiNamedElement)?.name ?: "unknown",
            qualifiedName = QualifiedNameUtil.getQualifiedName(declaration),
            kind = LanguageServices.getKind(declaration),
            file = file?.let { getRelativePath(project, it) } ?: "unknown",
            line = getLineNumber(project, declaration) ?: 0,
            column = getColumnNumber(project, declaration) ?: 0,
        )

        return SuperMethodsData(method = methodData, hierarchy = buildHierarchy(project, declaration, recurse = !isClass))
    }

    private fun resolveKtDeclaration(element: PsiElement): PsiElement? {
        val ktClassOrObject = ktClassOrObjectClass
        if (ktClassOrObject != null && ktClassOrObject.isInstance(element)) return element
        val ktCallable = ktCallableDeclarationClass ?: return null
        if (ktCallable.isInstance(element)) return element
        // Walk up: prefer KtClassOrObject first (class-level anchor), then KtCallableDeclaration
        @Suppress("UNCHECKED_CAST")
        val nearestCallable = PsiTreeUtil.getParentOfType(element, ktCallable as Class<out PsiElement>)
        if (ktClassOrObject != null) {
            @Suppress("UNCHECKED_CAST")
            val nearestClass = PsiTreeUtil.getParentOfType(element, ktClassOrObject as Class<out PsiElement>)
            if (nearestClass != null && nearestCallable != null) {
                // Return whichever is the closer ancestor (smaller depth from element)
                return if (PsiTreeUtil.isAncestor(nearestCallable, nearestClass, false)) nearestClass else nearestCallable
            }
            if (nearestClass != null) return nearestClass
        }
        return nearestCallable
    }

    /**
     * The declarations that [element] overrides or implements, when [element] itself is a
     * `KtCallableDeclaration` (a function, a property, a parameter or a constructor): the
     * declarations of [walkSuperDeclarations], all levels, in the same order as the hierarchy of
     * [findSuperMethods]. Empty for any other element, also for an element inside a declaration:
     * this method does not walk up as [resolveKtDeclaration] does (#175).
     */
    override fun findBaseDeclarations(element: PsiElement): List<PsiElement> {
        if (ktCallableDeclarationClass?.isInstance(element) != true) return emptyList()
        return walkSuperDeclarations(element)
    }

    /**
     * The references to [element] itself, when [element] is a `KtCallableDeclaration` with a super
     * declaration: the references of the usages that `processElementUsages` of the Kotlin
     * find-usages handler gives for [element], each one time, in the order of arrival. The handler
     * comes from the first factory that can find the usages of [element], in the mode
     * [OperationMode.HIGHLIGHT_USAGES], which asks no question. The options are a clone of the
     * options of the handler, with [scope] and with no text occurrences. Null for any other element
     * and for a declaration with no super declaration: the search then takes the find-usages
     * handler, as before. Null also when no factory or no handler is available.
     *
     * The search does not take `primaryElements` and `findReferencesToHighlight` of the Kotlin
     * handler for an override (#175). Both send the search to the super declarations, and
     * `primaryElements` throws off the EDT. `processElementUsages` searches the given declaration
     * itself.
     */
    override fun findDirectReferences(element: PsiElement, scope: SearchScope): Collection<PsiReference>? {
        if (ktCallableDeclarationClass?.isInstance(element) != true) return null
        if (walkSuperDeclarations(element, recurse = false).isEmpty()) return null
        val factory = FindUsagesHandlerFactory.EP_NAME.getExtensions(element.project)
            .firstOrNull { it.canFindUsages(element) } ?: return null
        val handler = factory.createFindUsagesHandler(element, OperationMode.HIGHLIGHT_USAGES)
        if (handler == null || handler === FindUsagesHandler.NULL_HANDLER) return null
        // Never mutate the options object of the handler: the factory shares it.
        val options = handler.findUsagesOptions.clone()
        options.searchScope = scope
        options.isSearchForTextOccurrences = false
        val references = Collections.synchronizedSet(LinkedHashSet<PsiReference>())
        handler.processElementUsages(element, Processor<UsageInfo> { info ->
            info.reference?.let(references::add)
            true
        }, options)
        return synchronized(references) { references.toList() }
    }

    private fun buildHierarchy(project: Project, declaration: PsiElement, recurse: Boolean): List<SuperMethodData> =
        walkSuperDeclarations(declaration, recurse = recurse).map { superPsi ->
            val file = superPsi.containingFile?.virtualFile
            SuperMethodData(
                name = (superPsi as? com.intellij.psi.PsiNamedElement)?.name ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(superPsi),
                kind = LanguageServices.getKind(superPsi),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, superPsi),
                column = getColumnNumber(project, superPsi),
            )
        }

    /**
     * The walk of [buildHierarchy], [findBaseDeclarations] and [findDirectReferences]: the super
     * declarations of [declaration] from `SuperDeclarationProvider.findSuperDeclarations`, in the
     * order of the call. When [recurse] is true, the super declarations of each super declaration
     * follow it (all levels, depth first); else the walk gives the first level only. A super
     * declaration with the key of an earlier one (its qualified name, else its class and identity)
     * is skipped, together with its super declarations.
     */
    private fun walkSuperDeclarations(
        declaration: PsiElement,
        visited: MutableSet<String> = mutableSetOf(),
        recurse: Boolean = true,
    ): List<PsiElement> {
        val invoker = findMethod ?: return emptyList()
        val instance = providerObject ?: return emptyList()

        @Suppress("UNCHECKED_CAST")
        val rawSupers: List<Any> = try {
            invoker.invoke(instance, declaration) as? List<Any> ?: return emptyList()
        } catch (t: Throwable) {
            LOG.debug("SuperDeclarationProvider.findSuperDeclarations failed", t)
            return emptyList()
        }

        val out = mutableListOf<PsiElement>()
        for (superDecl in rawSupers) {
            val superPsi = extractPsiFromSuperDeclaration(superDecl) ?: continue
            val key = QualifiedNameUtil.getQualifiedName(superPsi)
                ?: "${superPsi.javaClass.simpleName}@${System.identityHashCode(superPsi)}"
            if (!visited.add(key)) continue
            out.add(superPsi)
            // Recurse to walk transitive chain (analogous to Java's findSuperMethods recursion).
            // Disabled for class anchors — direct supertypes only (one level up).
            if (recurse) out.addAll(walkSuperDeclarations(superPsi, visited))
        }
        return out
    }

    /**
     * Unpacks a `SuperDeclaration` sealed instance. All four variants
     * (`Function` / `Property` / `Parameter` / `Class`) carry a
     * `declarationPointer: SmartPsiElementPointer<*>` — extract via reflection.
     */
    private fun extractPsiFromSuperDeclaration(superDecl: Any): PsiElement? {
        return try {
            // Try common accessor names; the sealed-class pattern in Kotlin
            // exposes one of these depending on variant.
            for (accessor in listOf("getDeclarationPointer", "getDeclaration")) {
                val m = runCatching { superDecl.javaClass.getMethod(accessor) }.getOrNull() ?: continue
                val raw = m.invoke(superDecl)
                val psi = when (raw) {
                    is SmartPsiElementPointer<*> -> raw.element
                    is PsiElement -> raw
                    else -> null
                }
                if (psi != null) return psi
            }
            null
        } catch (t: Throwable) {
            LOG.debug("Failed to extract PSI from SuperDeclaration $superDecl", t)
            null
        }
    }

    private fun getRelativePath(project: Project, file: VirtualFile): String =
        ProjectUtils.getToolFilePath(project, file)

    private fun getLineNumber(project: Project, element: PsiElement): Int? {
        val psiFile = element.containingFile ?: return null
        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile) ?: return null
        return document.getLineNumber(element.textOffset) + 1
    }

    private fun getColumnNumber(project: Project, element: PsiElement): Int? {
        val psiFile = element.containingFile ?: return null
        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile) ?: return null
        val lineNumber = document.getLineNumber(element.textOffset)
        return element.textOffset - document.getLineStartOffset(lineNumber) + 1
    }
}
