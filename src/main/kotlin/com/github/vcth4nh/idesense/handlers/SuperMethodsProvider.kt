package com.github.vcth4nh.idesense.handlers

import com.intellij.lang.LanguageExtension
import com.intellij.openapi.extensions.ExtensionPointName
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.util.KeyedLazyInstance

interface SuperMethodsProvider {
    fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData?

    /**
     * The declarations that [element] overrides or implements: all levels, the nearest first.
     * Empty when [element] itself is not a member with a base declaration. Never walks up from
     * [element] to an enclosing member.
     */
    fun findBaseDeclarations(element: PsiElement): List<PsiElement> = emptyList()

    companion object {
        const val EP_NAME_STRING = "com.github.vcth4nh.idesense.superMethodsProvider"
        val EP_NAME = ExtensionPointName.create<KeyedLazyInstance<SuperMethodsProvider>>(EP_NAME_STRING)
        val EP = LanguageExtension<SuperMethodsProvider>(EP_NAME_STRING)
    }
}
