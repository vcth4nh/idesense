package com.github.vcth4nh.idesense.handlers.php

import com.github.vcth4nh.idesense.handlers.LanguageKindResolver
import com.intellij.psi.PsiElement

class PhpKindResolver : LanguageKindResolver {

    private val phpClassClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.lang.psi.elements.PhpClass") } catch (_: ClassNotFoundException) { null }
    }

    override fun resolveKind(element: PsiElement): String? {
        val phpClass = phpClassClass ?: return null
        if (!phpClass.isInstance(element)) return null
        return try {
            val isInterface = invokeBoolean(element, "isInterface")
            val isTrait = invokeBoolean(element, "isTrait")
            val isEnum = invokeBoolean(element, "isEnum")
            val isAbstract = invokeBoolean(element, "isAbstract")
            when {
                isInterface -> "INTERFACE"
                isTrait -> "TRAIT"
                isEnum -> "ENUM"
                isAbstract -> "ABSTRACT_CLASS"
                else -> "CLASS"
            }
        } catch (_: Exception) { null }
    }

    private fun invokeBoolean(target: Any, method: String): Boolean = runCatching {
        target.javaClass.getMethod(method).invoke(target) as? Boolean ?: false
    }.getOrDefault(false)
}
