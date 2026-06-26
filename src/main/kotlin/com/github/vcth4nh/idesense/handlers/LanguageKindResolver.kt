package com.github.vcth4nh.idesense.handlers

import com.intellij.lang.LanguageExtension
import com.intellij.psi.PsiElement

interface LanguageKindResolver {
    fun resolveKind(element: PsiElement): String?

    companion object {
        const val EP_NAME_STRING = "com.github.vcth4nh.idesense.languageKindResolver"
        val EP = LanguageExtension<LanguageKindResolver>(EP_NAME_STRING)
    }
}
