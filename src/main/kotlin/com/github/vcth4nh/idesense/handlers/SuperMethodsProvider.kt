package com.github.vcth4nh.idesense.handlers

import com.intellij.lang.LanguageExtension
import com.intellij.openapi.extensions.ExtensionPointName
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiReference
import com.intellij.psi.search.SearchScope
import com.intellij.util.KeyedLazyInstance

interface SuperMethodsProvider {
    fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData?

    /**
     * The declarations that [element] overrides or implements: all levels, the nearest first.
     * Empty when [element] itself is not a member with a base declaration. Never walks up from
     * [element] to an enclosing member.
     */
    fun findBaseDeclarations(element: PsiElement): List<PsiElement> = emptyList()

    /**
     * The references to [element] itself in [scope], for a language whose find-usages handler sends
     * the search of a member to its base declarations, or whose handler factory asks a question for
     * a member (PHP, #182). Null (the default): the search takes the find-usages handler for [element].
     */
    fun findDirectReferences(element: PsiElement, scope: SearchScope): Collection<PsiReference>? = null

    /**
     * The declarations that override or implement [element]: all levels. The find usages search
     * also searches each one, with the mark [com.github.vcth4nh.idesense.constants.UsageMatch.OVERRIDE].
     * Empty (the default): the search has no override pass.
     */
    fun findOverridingDeclarations(element: PsiElement): List<PsiElement> = emptyList()

    /**
     * The base declarations of [element] that [findBaseDeclarations] leaves out on purpose. The
     * find usages search does not search them, and the tools name them in a note. Empty (the default).
     */
    fun skippedBaseDeclarations(element: PsiElement): List<PsiElement> = emptyList()

    /**
     * The mark of the usage of [reference], a usage that is no dynamic usage. [anchor] is the symbol
     * of the query, not the target of the pass. [passMark] is the mark of the pass (null for the
     * direct pass). The default gives [passMark].
     */
    fun usageMark(reference: PsiReference, anchor: PsiElement, passMark: String?): String? = passMark

    /**
     * A [com.github.vcth4nh.idesense.constants.UsageDrop] value when the find usages search leaves
     * out the usage at [usageElement] for the query [anchor], else null (the default). The tools
     * give the count of each kind in a note.
     */
    fun droppedUsageKind(usageElement: PsiElement, anchor: PsiElement): String? = null

    companion object {
        const val EP_NAME_STRING = "com.github.vcth4nh.idesense.superMethodsProvider"
        val EP_NAME = ExtensionPointName.create<KeyedLazyInstance<SuperMethodsProvider>>(EP_NAME_STRING)
        val EP = LanguageExtension<SuperMethodsProvider>(EP_NAME_STRING)
    }
}
