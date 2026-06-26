package com.github.vcth4nh.idesense.handlers.kotlin

import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.handlers.MethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodsData
import com.github.vcth4nh.idesense.handlers.SuperMethodsProvider
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.SmartPsiElementPointer
import com.intellij.psi.util.PsiTreeUtil

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

    private fun buildHierarchy(
        project: Project,
        declaration: PsiElement,
        visited: MutableSet<String> = mutableSetOf(),
        recurse: Boolean = true,
    ): List<SuperMethodData> {
        val invoker = findMethod ?: return emptyList()
        val instance = providerObject ?: return emptyList()

        @Suppress("UNCHECKED_CAST")
        val rawSupers: List<Any> = try {
            invoker.invoke(instance, declaration) as? List<Any> ?: return emptyList()
        } catch (t: Throwable) {
            LOG.debug("SuperDeclarationProvider.findSuperDeclarations failed", t)
            return emptyList()
        }

        val out = mutableListOf<SuperMethodData>()
        for (superDecl in rawSupers) {
            val superPsi = extractPsiFromSuperDeclaration(superDecl) ?: continue
            val key = QualifiedNameUtil.getQualifiedName(superPsi)
                ?: "${superPsi.javaClass.simpleName}@${System.identityHashCode(superPsi)}"
            if (!visited.add(key)) continue

            val file = superPsi.containingFile?.virtualFile
            out.add(SuperMethodData(
                name = (superPsi as? com.intellij.psi.PsiNamedElement)?.name ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(superPsi),
                kind = LanguageServices.getKind(superPsi),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, superPsi),
                column = getColumnNumber(project, superPsi),
            ))
            // Recurse to walk transitive chain (analogous to Java's findSuperMethods recursion).
            // Disabled for class anchors — direct supertypes only (one level up).
            if (recurse) out.addAll(buildHierarchy(project, superPsi, visited))
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
