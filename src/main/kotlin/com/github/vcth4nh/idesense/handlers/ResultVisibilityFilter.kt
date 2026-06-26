package com.github.vcth4nh.idesense.handlers

import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement
import com.intellij.psi.search.GlobalSearchScope

internal fun shouldIncludeNavigationElement(
    searchScope: GlobalSearchScope,
    element: PsiElement,
): Boolean {
    val file = element.containingFile?.virtualFile ?: return true
    return shouldIncludeNavigationFile(searchScope, file)
}

internal fun shouldIncludeNavigationFile(
    searchScope: GlobalSearchScope,
    file: VirtualFile,
): Boolean = searchScope.contains(file)
