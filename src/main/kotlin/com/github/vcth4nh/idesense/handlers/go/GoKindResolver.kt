package com.github.vcth4nh.idesense.handlers.go

import com.github.vcth4nh.idesense.handlers.LanguageKindResolver
import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil

class GoKindResolver : LanguageKindResolver {

    private val goTypeSpecClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoTypeSpec") } catch (_: ClassNotFoundException) { null }
    }
    private val goStructTypeClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoStructType") } catch (_: ClassNotFoundException) { null }
    }
    private val goInterfaceTypeClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoInterfaceType") } catch (_: ClassNotFoundException) { null }
    }

    override fun resolveKind(element: PsiElement): String? {
        val typeSpec = goTypeSpecClass ?: return null
        if (!typeSpec.isInstance(element)) return null
        return try {
            @Suppress("UNCHECKED_CAST")
            when {
                goInterfaceTypeClass != null && PsiTreeUtil.findChildOfType(
                    element, goInterfaceTypeClass as Class<out PsiElement>
                ) != null -> "INTERFACE"
                goStructTypeClass != null && PsiTreeUtil.findChildOfType(
                    element, goStructTypeClass as Class<out PsiElement>
                ) != null -> "STRUCT"
                else -> null
            }
        } catch (_: Exception) { null }
    }
}
