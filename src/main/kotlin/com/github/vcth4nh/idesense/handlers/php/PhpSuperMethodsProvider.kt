package com.github.vcth4nh.idesense.handlers.php

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
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Proxy

/**
 * PHP super-methods provider. Delegates to
 * `com.jetbrains.php.PhpClassHierarchyUtils.processSuperMembers(PhpClassMember, HierarchyClassMemberProcessor)`
 * — the broader API that internally dispatches to `processSuperMethods` for
 * `Method` and `processSuperFields` for `Field`. In the PHP plugin's PSI,
 * `const X = "y"` inside a class is a `Field` with `isConstant() == true`,
 * so this single call covers methods, fields/properties, AND class constants.
 *
 * Matches the data path `PhpLineMarkerProvider.findParents` uses for the
 * `↑` gutter marker (which also accepts both Method and Field).
 *
 * The `HierarchyClassMemberProcessor` is a `@FunctionalInterface` callback;
 * we implement it via `java.lang.reflect.Proxy.newProxyInstance` to avoid a
 * compile-time PHP-plugin dep.
 *
 * Covers (gain over previous walker): trait sources, `insteadof` conflict
 * resolution, `@mixin`, constant overrides, field overrides, correct
 * private-method handling.
 */
class PhpSuperMethodsProvider : SuperMethodsProvider {

    companion object {
        private val LOG = logger<PhpSuperMethodsProvider>()
    }

    private val phpClassMemberClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.lang.psi.elements.PhpClassMember") } catch (_: ClassNotFoundException) { null }
    }

    private val phpClassClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.lang.psi.elements.PhpClass") } catch (_: ClassNotFoundException) { null }
    }

    private val hierarchyUtilsClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.PhpClassHierarchyUtils") } catch (_: ClassNotFoundException) { null }
    }

    private val hierarchyClassMemberProcessorClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.PhpClassHierarchyUtils\$HierarchyClassMemberProcessor") } catch (_: ClassNotFoundException) { null }
    }

    private val processSuperMembersMethod: java.lang.reflect.Method? by lazy {
        try {
            val util = hierarchyUtilsClass ?: return@lazy null
            val member = phpClassMemberClass ?: return@lazy null
            val processor = hierarchyClassMemberProcessorClass ?: return@lazy null
            util.getMethod("processSuperMembers", member, processor)
        } catch (_: Throwable) { null }
    }

    private val getImmediateParentsMethod: java.lang.reflect.Method? by lazy {
        try {
            val util = hierarchyUtilsClass ?: return@lazy null
            val phpClass = phpClassClass ?: return@lazy null
            util.getMethod("getImmediateParents", phpClass)
        } catch (_: Throwable) { null }
    }

    override fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData? {
        // Member anchor: existing full-chain behavior (unchanged)
        val member = findContainingMember(element)
        if (member != null) {
            val file = member.containingFile?.virtualFile
            val methodData = MethodData(
                name = getName(member) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(member),
                kind = LanguageServices.getKind(member),
                file = file?.let { getRelativePath(project, it) } ?: "unknown",
                line = getLineNumber(project, member) ?: 0,
                column = getColumnNumber(project, member) ?: 0,
            )
            return SuperMethodsData(method = methodData, hierarchy = buildHierarchy(project, member))
        }

        // Class anchor: direct supertypes only (one level up)
        val phpClass = findContainingPhpClass(element) ?: return null
        val file = phpClass.containingFile?.virtualFile
        val classData = MethodData(
            name = getName(phpClass) ?: "unknown",
            qualifiedName = QualifiedNameUtil.getQualifiedName(phpClass),
            kind = LanguageServices.getKind(phpClass),
            file = file?.let { getRelativePath(project, it) } ?: "unknown",
            line = getLineNumber(project, phpClass) ?: 0,
            column = getColumnNumber(project, phpClass) ?: 0,
        )
        return SuperMethodsData(method = classData, hierarchy = buildClassHierarchy(project, phpClass))
    }

    private fun buildHierarchy(project: Project, member: PsiElement): List<SuperMethodData> {
        val invoker = processSuperMembersMethod ?: return emptyList()
        val processorIface = hierarchyClassMemberProcessorClass ?: return emptyList()

        val collected = mutableListOf<PsiElement>()
        val visited = mutableSetOf<String>()

        val handler = InvocationHandler { _, m, args ->
            if (m.name == "process" && args != null && args.isNotEmpty()) {
                val superMember = args[0] as? PsiElement
                if (superMember != null) {
                    val key = QualifiedNameUtil.getQualifiedName(superMember)
                        ?: "${superMember.javaClass.simpleName}@${System.identityHashCode(superMember)}"
                    if (visited.add(key)) collected.add(superMember)
                }
                return@InvocationHandler true  // keep processing
            }
            // Default returns for the Object methods (equals/hashCode/toString) and
            // any unexpected interface method. Defensive — the PHP plugin should
            // only ever call `process(...)` on our processor.
            when {
                m.name == "equals" && args?.size == 1 -> false
                m.name == "hashCode" -> 0
                m.name == "toString" -> "HierarchyClassMemberProcessor\$Proxy"
                m.returnType == java.lang.Boolean.TYPE -> true
                m.returnType == java.lang.Void.TYPE -> null
                else -> null
            }
        }

        val proxy = Proxy.newProxyInstance(
            processorIface.classLoader,
            arrayOf(processorIface),
            handler,
        )

        try {
            invoker.invoke(null, member, proxy)
        } catch (t: Throwable) {
            LOG.debug("PhpClassHierarchyUtils.processSuperMembers invocation failed", t)
            return emptyList()
        }

        return collected.map { superMember ->
            val file = superMember.containingFile?.virtualFile
            SuperMethodData(
                name = getName(superMember) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(superMember),
                kind = LanguageServices.getKind(superMember),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, superMember),
                column = getColumnNumber(project, superMember),
            )
        }
    }

    private fun findContainingMember(element: PsiElement): PsiElement? {
        val cls = phpClassMemberClass ?: return null
        if (cls.isInstance(element)) return element
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, cls as Class<out PsiElement>)
    }

    private fun findContainingPhpClass(element: PsiElement): PsiElement? {
        val cls = phpClassClass ?: return null
        if (cls.isInstance(element)) return element
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, cls as Class<out PsiElement>)
    }

    /**
     * Returns the DIRECT supertypes of [phpClass] — one level only, no transitive walk.
     * Mirrors `PhpGotoSuperMethodHandler`'s class branch, which calls
     * `PhpClassHierarchyUtils.getImmediateParents(PhpClass)` (super class + interfaces + traits).
     */
    private fun buildClassHierarchy(project: Project, phpClass: PsiElement): List<SuperMethodData> {
        val invoker = getImmediateParentsMethod ?: return emptyList()

        @Suppress("UNCHECKED_CAST")
        val parents: List<PsiElement> = try {
            invoker.invoke(null, phpClass) as? List<PsiElement> ?: return emptyList()
        } catch (t: Throwable) {
            LOG.debug("PhpClassHierarchyUtils.getImmediateParents invocation failed", t)
            return emptyList()
        }

        return parents.mapNotNull { parent ->
            val file = parent.containingFile?.virtualFile
            SuperMethodData(
                name = getName(parent) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(parent),
                kind = LanguageServices.getKind(parent),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, parent),
                column = getColumnNumber(project, parent),
            )
        }
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
