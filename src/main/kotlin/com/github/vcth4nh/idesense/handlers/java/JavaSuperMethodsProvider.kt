package com.github.vcth4nh.idesense.handlers.java

import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.handlers.MethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodsData
import com.github.vcth4nh.idesense.handlers.SuperMethodsProvider
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.LambdaUtil
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFunctionalExpression
import com.intellij.psi.PsiMethod
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.impl.FindSuperElementsHelper
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

    private fun buildHierarchy(
        project: Project,
        method: PsiMethod,
        visited: MutableSet<String> = mutableSetOf(),
    ): List<SuperMethodData> {
        val out = mutableListOf<SuperMethodData>()
        for (superMethod in method.findSuperMethods()) {
            val key = QualifiedNameUtil.getQualifiedName(superMethod)
                ?: "${superMethod.containingClass?.qualifiedName}.${superMethod.name}"
            if (!visited.add(key)) continue
            val file = superMethod.containingFile?.virtualFile
            out.add(SuperMethodData(
                name = superMethod.name,
                qualifiedName = QualifiedNameUtil.getQualifiedName(superMethod),
                kind = LanguageServices.getKind(superMethod),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, superMethod),
                column = getColumnNumber(project, superMethod),
            ))
            out.addAll(buildHierarchy(project, superMethod, visited))
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
