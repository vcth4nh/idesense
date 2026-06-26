package com.github.vcth4nh.idesense.handlers.python

import com.github.vcth4nh.idesense.handlers.LanguageKindResolver
import com.intellij.psi.PsiElement

class PythonKindResolver : LanguageKindResolver {

    private val pyTargetExpressionClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.python.psi.PyTargetExpression") } catch (_: ClassNotFoundException) { null }
    }

    override fun resolveKind(element: PsiElement): String? {
        val pyClass = pyTargetExpressionClass ?: return null
        if (!pyClass.isInstance(element)) return null
        return try {
            val containingClass = element.javaClass.getMethod("getContainingClass").invoke(element)
            if (containingClass != null) "FIELD" else "VARIABLE"
        } catch (_: Exception) { "FIELD" }
    }
}
