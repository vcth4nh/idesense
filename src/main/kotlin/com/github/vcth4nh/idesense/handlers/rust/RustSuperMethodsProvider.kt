package com.github.vcth4nh.idesense.handlers.rust

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
import com.intellij.psi.util.PsiTreeUtil

/**
 * Rust super-methods provider. Delegates to
 * `org.rust.ide.navigation.goto.RsGotoSuperHandlerKt.gotoSuperTargets` —
 * the pure data function `RsGotoSuperHandler` uses internally and the same
 * resolver path the `I↑` gutter line marker (`RsTraitItemImplLineMarkerProvider`)
 * uses (both routes lead to `RsAbstractableKt.getSuperItem`).
 *
 * Covers: trait fn / const / type alias inside `impl Trait for Struct` blocks.
 * Multi-trait satisfaction is by Rust semantics impossible (an impl block
 * binds to exactly one trait) — single super is correct for that case.
 */
class RustSuperMethodsProvider : SuperMethodsProvider {

    companion object {
        private val LOG = logger<RustSuperMethodsProvider>()
    }

    private val rsAbstractableClass: Class<*>? by lazy {
        try { Class.forName("org.rust.lang.core.psi.ext.RsAbstractable") } catch (_: ClassNotFoundException) { null }
    }

    private val gotoSuperHandlerKtClass: Class<*>? by lazy {
        try { Class.forName("org.rust.ide.navigation.goto.RsGotoSuperHandlerKt") } catch (_: ClassNotFoundException) { null }
    }

    private val gotoSuperTargetsMethod: java.lang.reflect.Method? by lazy {
        try {
            gotoSuperHandlerKtClass?.getMethod("gotoSuperTargets", PsiElement::class.java)
        } catch (_: Throwable) { null }
    }

    override fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData? {
        val abstractable = resolveRsAbstractable(element) ?: return null

        val file = abstractable.containingFile?.virtualFile
        val methodData = MethodData(
            name = getName(abstractable) ?: "unknown",
            qualifiedName = QualifiedNameUtil.getQualifiedName(abstractable),
            kind = LanguageServices.getKind(abstractable),
            file = file?.let { getRelativePath(project, it) } ?: "unknown",
            line = getLineNumber(project, abstractable) ?: 0,
            column = getColumnNumber(project, abstractable) ?: 0,
        )

        return SuperMethodsData(method = methodData, hierarchy = buildHierarchy(project, abstractable))
    }

    private fun resolveRsAbstractable(element: PsiElement): PsiElement? {
        val cls = rsAbstractableClass ?: return null
        if (cls.isInstance(element)) return element
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, cls as Class<out PsiElement>)
    }

    private fun buildHierarchy(project: Project, abstractable: PsiElement): List<SuperMethodData> {
        val invoker = gotoSuperTargetsMethod ?: return emptyList()
        val abstractableClass = rsAbstractableClass ?: return emptyList()

        @Suppress("UNCHECKED_CAST")
        val rawTargets = try {
            invoker.invoke(null, abstractable) as? List<PsiElement> ?: return emptyList()
        } catch (t: Throwable) {
            LOG.debug("RsGotoSuperHandlerKt.gotoSuperTargets invocation failed", t)
            return emptyList()
        }

        val visited = mutableSetOf<String>()
        val out = mutableListOf<SuperMethodData>()
        for (target in rawTargets) {
            // Filter to RsAbstractable (drops module-super results which gotoSuperTargets also returns for mod files)
            if (!abstractableClass.isInstance(target)) continue
            val key = QualifiedNameUtil.getQualifiedName(target)
                ?: "${target.javaClass.simpleName}@${System.identityHashCode(target)}"
            if (!visited.add(key)) continue
            val file = target.containingFile?.virtualFile
            out.add(SuperMethodData(
                name = getName(target) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(target),
                kind = LanguageServices.getKind(target),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, target),
                column = getColumnNumber(project, target),
            ))
        }
        return out
    }

    private fun getName(element: PsiElement): String? = runCatching {
        element.javaClass.getMethod("getName").invoke(element) as? String
    }.getOrNull()

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
