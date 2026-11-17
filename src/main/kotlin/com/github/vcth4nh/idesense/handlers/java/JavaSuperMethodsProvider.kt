package com.github.vcth4nh.idesense.handlers.java

import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.handlers.MethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodsData
import com.github.vcth4nh.idesense.handlers.SuperMethodsProvider
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.lang.java.JavaLanguage
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.LambdaUtil
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFunctionalExpression
import com.intellij.psi.PsiMethod
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.PsiReference
import com.intellij.psi.impl.FindSuperElementsHelper
import com.intellij.psi.search.SearchScope
import com.intellij.psi.search.searches.MethodReferencesSearch
import com.intellij.psi.util.PsiTreeUtil

/**
 * Java super-methods provider. Delegates to the platform-public
 * [PsiMethod.findSuperMethods] (same API the IDE's `JavaGotoSuperHandler`
 * uses via `FindSuperElementsHelper.findSuperElements`). Recursion walks
 * the transitive chain because `findSuperMethods` returns only direct
 * overrides.
 */
class JavaSuperMethodsProvider : SuperMethodsProvider {

    override fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData? {
        // Lambda / method-reference: resolve the SAM it implements (mirrors JavaGotoSuperHandler).
        val functionalExpr = element as? PsiFunctionalExpression
            ?: PsiTreeUtil.getParentOfType(element, PsiFunctionalExpression::class.java, false, PsiMethod::class.java)
        if (functionalExpr != null) {
            val sam = LambdaUtil.getFunctionalInterfaceMethod(functionalExpr)
            if (sam != null) {
                return SuperMethodsData(method = toMethodData(project, sam), hierarchy = buildHierarchy(project, sam))
            }
        }

        // Nearest method or class, mirroring FindSuperElementsHelper's two branches.
        val member = PsiTreeUtil.getNonStrictParentOfType(element, PsiMethod::class.java, PsiClass::class.java)
            ?: return null
        return when (member) {
            is PsiMethod -> {
                member.containingClass ?: return null
                SuperMethodsData(method = toMethodData(project, member), hierarchy = buildHierarchy(project, member))
            }
            is PsiClass -> {
                // Direct supertypes only (FindSuperElementsHelper returns getSupers() minus Object).
                val supers = FindSuperElementsHelper.findSuperElements(member)
                    .filterIsInstance<PsiClass>()
                SuperMethodsData(
                    method = toMethodData(project, member),
                    hierarchy = supers.map { superClass ->
                        SuperMethodData(
                            name = superClass.name ?: "unknown",
                            qualifiedName = QualifiedNameUtil.getQualifiedName(superClass),
                            kind = LanguageServices.getKind(superClass),
                            file = superClass.containingFile?.virtualFile?.let { getRelativePath(project, it) },
                            line = getLineNumber(project, superClass),
                            column = getColumnNumber(project, superClass),
                        )
                    },
                )
            }
            else -> null
        }
    }

    private fun toMethodData(project: Project, element: PsiElement): MethodData {
        val named = element as? PsiNamedElement
        val file = element.containingFile?.virtualFile
        return MethodData(
            name = named?.name ?: "unknown",
            qualifiedName = QualifiedNameUtil.getQualifiedName(element),
            kind = LanguageServices.getKind(element),
            file = file?.let { getRelativePath(project, it) } ?: "unknown",
            line = getLineNumber(project, element) ?: 0,
            column = getColumnNumber(project, element) ?: 0,
        )
    }

    /**
     * The methods that [element] overrides or implements, when [element] itself is a [PsiMethod]:
     * the methods of [walkSuperMethods], in the same order as the hierarchy of [findSuperMethods].
     * A method of `java.lang.Object` stays in the list, because IntelliJ IDEA searches it too.
     * Empty for any other element, also for an element inside a method (#175).
     *
     * A super method of another language gives its real declaration ([baseDeclarationOf]), so the
     * search of that declaration takes the provider and the handler of its own language. The Java
     * handler of a light method reads `primaryElements`, which throws off the EDT (#175).
     */
    override fun findBaseDeclarations(element: PsiElement): List<PsiElement> {
        if (element !is PsiMethod) return emptyList()
        return walkSuperMethods(element).map(::baseDeclarationOf)
    }

    /**
     * The declaration that the base pass searches for [superMethod]: [superMethod] itself when its
     * language is the Java language (also a method of a compiled class), else its navigation
     * element. For a Kotlin light method, the navigation element is the Kotlin declaration.
     */
    internal fun baseDeclarationOf(superMethod: PsiMethod): PsiElement =
        if (superMethod.language is JavaLanguage) superMethod else superMethod.navigationElement

    /**
     * The references to [element] itself, when [element] is a [PsiMethod] (a method or a
     * constructor, with or without a super method): `MethodReferencesSearch.search(element, scope,
     * true)`, the search that `JavaFindUsagesHandler.findReferencesToHighlight` runs for one target.
     * The result also holds a reference that resolves to an override of [element] in a subclass,
     * but not a reference that resolves to a super method. Null for any other element: the search
     * then takes the find-usages handler.
     *
     * The search does not take `JavaFindUsagesHandler` for a method (#175). Its `getPrimaryElements`
     * calls `SuperMethodWarningUtil.getTargetMethodCandidates`, which asserts the EDT, so it throws
     * off the EDT for each method and constructor. Its `findReferencesToHighlight` searches the
     * deepest super methods of a method, not the method itself.
     */
    override fun findDirectReferences(element: PsiElement, scope: SearchScope): Collection<PsiReference>? {
        if (element !is PsiMethod) return null
        return MethodReferencesSearch.search(element, scope, true).findAll()
    }

    private fun buildHierarchy(project: Project, method: PsiMethod): List<SuperMethodData> =
        walkSuperMethods(method).map { superMethod ->
            val file = superMethod.containingFile?.virtualFile
            SuperMethodData(
                name = superMethod.name,
                qualifiedName = QualifiedNameUtil.getQualifiedName(superMethod),
                kind = LanguageServices.getKind(superMethod),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, superMethod),
                column = getColumnNumber(project, superMethod),
            )
        }

    /**
     * The walk of [buildHierarchy] and [findBaseDeclarations]: the super methods of [method], all
     * levels, depth first (a super method, then its super methods). A super method with the key of
     * an earlier method (its qualified name, else its class and its name) is skipped, together with
     * its super methods.
     */
    private fun walkSuperMethods(method: PsiMethod, visited: MutableSet<String> = mutableSetOf()): List<PsiMethod> {
        val out = mutableListOf<PsiMethod>()
        for (superMethod in method.findSuperMethods()) {
            val key = QualifiedNameUtil.getQualifiedName(superMethod)
                ?: "${superMethod.containingClass?.qualifiedName}.${superMethod.name}"
            if (!visited.add(key)) continue
            out.add(superMethod)
            out.addAll(walkSuperMethods(superMethod, visited))
        }
        return out
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
