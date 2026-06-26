package com.github.vcth4nh.idesense.util

import com.intellij.psi.PsiDirectory
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiPolyVariantReference

/**
 * Python-specific fallback for qualified member/callee resolution.
 *
 * The generic IntelliJ PSI resolution path can resolve dotted Python expressions such as
 * `json.dumps(...)` to a module/package directory when invoked on the member token. This helper
 * refines those cases by reusing PyCharm's own qualified-reference and call-resolution APIs via
 * reflection, while preserving normal qualifier navigation semantics.
 */
internal object PythonDefinitionResolver {

    private val pyCallExpressionClass by lazy { loadClass("com.jetbrains.python.psi.PyCallExpression") }
    private val pyReferenceExpressionClass by lazy { loadClass("com.jetbrains.python.psi.PyReferenceExpression") }
    private val pyResolveContextClass by lazy { loadClass("com.jetbrains.python.psi.resolve.PyResolveContext") }
    private val psiPackageClass by lazy { loadClass("com.intellij.psi.PsiPackage") }

    fun refineResolvedTarget(element: PsiElement, resolvedTarget: PsiElement?): PsiElement? {
        if (!shouldAttemptFallback(element, resolvedTarget)) return resolvedTarget

        return resolveQualifiedCallee(element)
            ?: resolveQualifiedReference(element)
            ?: resolvedTarget
    }

    private fun shouldAttemptFallback(element: PsiElement, resolvedTarget: PsiElement?): Boolean {
        val referenceClass = pyReferenceExpressionClass ?: return false
        if (findNearestInstance(element, referenceClass) == null) return false
        return resolvedTarget == null || resolvedTarget is PsiDirectory || isPsiPackage(resolvedTarget)
    }

    private fun resolveQualifiedCallee(element: PsiElement): PsiElement? {
        val callClass = pyCallExpressionClass ?: return null
        val resolveContextClass = pyResolveContextClass ?: return null
        val referenceElement = findNearestReferenceExpression(element) ?: return null
        val callExpression = findNearestInstance(element, callClass) ?: return null
        val callee = invokeNoArg(callExpression, "getCallee") as? PsiElement ?: return null

        if (callee !== referenceElement) return null

        val resolveContext = runCatching {
            resolveContextClass.getMethod("defaultContext").invoke(null)
        }.getOrNull() ?: return null

        val resolved = runCatching {
            callExpression.javaClass
                .getMethod("multiResolveCalleeFunction", resolveContextClass)
                .invoke(callExpression, resolveContext) as? Collection<*>
        }.getOrNull().orEmpty()

        return resolved
            .filterIsInstance<PsiElement>()
            .firstOrNull { !isDirectoryLike(it) }
    }

    private fun resolveQualifiedReference(element: PsiElement): PsiElement? {
        val referenceElement = findNearestReferenceExpression(element) ?: return null
        val qualifier = invokeNoArg(referenceElement, "getQualifier") as? PsiElement ?: return null
        val reference = invokeNoArg(referenceElement, "getReference") as? PsiPolyVariantReference ?: return null

        val directResolved = reference.resolve()
        if (directResolved != null && !isDirectoryLike(directResolved)) {
            return directResolved
        }

        return reference.multiResolve(false)
            .asSequence()
            .mapNotNull { it.element }
            .firstOrNull { !isDirectoryLike(it) && it != qualifier }
    }

    private fun findNearestReferenceExpression(element: PsiElement): PsiElement? {
        val referenceClass = pyReferenceExpressionClass ?: return null
        return findNearestInstance(element, referenceClass)
    }

    private fun findNearestInstance(element: PsiElement, targetClass: Class<*>): PsiElement? {
        var current: PsiElement? = element
        while (current != null) {
            if (targetClass.isInstance(current)) return current
            current = current.parent
        }
        return null
    }

    private fun invokeNoArg(target: Any, methodName: String): Any? {
        return runCatching {
            target.javaClass.getMethod(methodName).invoke(target)
        }.getOrNull()
    }

    private fun isDirectoryLike(target: PsiElement?): Boolean {
        return target is PsiDirectory || isPsiPackage(target)
    }

    private fun isPsiPackage(target: PsiElement?): Boolean {
        val packageClass = psiPackageClass ?: return false
        return target != null && packageClass.isInstance(target)
    }

    private fun loadClass(className: String): Class<*>? {
        return try {
            Class.forName(className)
        } catch (_: ClassNotFoundException) {
            null
        } catch (_: LinkageError) {
            null
        }
    }
}
