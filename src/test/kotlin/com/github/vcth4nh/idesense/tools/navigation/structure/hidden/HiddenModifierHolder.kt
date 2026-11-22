package com.github.vcth4nh.idesense.tools.navigation.structure.hidden

import com.intellij.psi.PsiElement
import java.lang.reflect.Proxy

/**
 * A stand-in for a PSI element whose class is not public and is in another package than
 * `UniversalModifiers`. The interface is package-private, so the proxy class of it is too, and a
 * reflective call of its public getter from another package throws `IllegalAccessException`.
 */
private interface HiddenModifierHolder : PsiElement {
    fun getModifierList(): Any?
}

fun hiddenModifierHolder(modifierList: Any?): PsiElement =
    Proxy.newProxyInstance(
        HiddenModifierHolder::class.java.classLoader,
        arrayOf(HiddenModifierHolder::class.java),
    ) { _, method, _ -> if (method.name == "getModifierList") modifierList else null } as PsiElement
