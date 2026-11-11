package com.github.vcth4nh.idesense.util

import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.search.GlobalSearchScope
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import junit.framework.TestCase

class PsiUtilsPositionUnitTest : TestCase() {

    private val scope = mockk<GlobalSearchScope>()

    private fun file(inScope: Boolean): PsiFile {
        val virtualFile = mockk<VirtualFile>()
        every { scope.contains(virtualFile) } returns inScope
        val file = mockk<PsiFile>()
        every { file.virtualFile } returns virtualFile
        return file
    }

    private fun element(textOffset: Int, file: PsiFile?, navigation: PsiElement? = null): PsiElement {
        val element = mockk<PsiElement>()
        every { element.textOffset } returns textOffset
        every { element.containingFile } returns file
        every { element.navigationElement } returns (navigation ?: element)
        return element
    }

    fun testAnElementWithAPositionInTheScopeIsItsOwnPositionElement() {
        val declaration = element(textOffset = 120, file = file(inScope = true), navigation = element(7, file(inScope = true)))

        assertSame(declaration, PsiUtils.positionElement(declaration, scope))
    }

    // GoLand gives a method that a struct gets through an embedded pointer as a
    // GoLightMethodDeclaration: a LightElement with text offset -1 whose navigation element is
    // the real method declaration (#129).
    fun testALightElementTakesThePositionOfItsNavigationElement() {
        val sourceFile = file(inScope = true)
        val realDeclaration = element(textOffset = 42, file = sourceFile)
        val lightElement = element(textOffset = -1, file = sourceFile, navigation = realDeclaration)

        assertSame(realDeclaration, PsiUtils.positionElement(lightElement, scope))
    }

    fun testALightElementWithoutAFileTakesThePositionOfItsNavigationElement() {
        val realDeclaration = element(textOffset = 42, file = file(inScope = true))
        val lightElement = element(textOffset = -1, file = null, navigation = realDeclaration)

        assertSame(realDeclaration, PsiUtils.positionElement(lightElement, scope))
    }

    // RustRover keeps the expansion of a macro call in a file of its own, which no scope holds.
    // The navigation element of an implementation in it is the macro call.
    fun testAnElementInAFileOutsideTheScopeTakesThePositionOfItsNavigationElement() {
        val macroCall = element(textOffset = 300, file = file(inScope = true))
        val expandedImpl = element(textOffset = 0, file = file(inScope = false), navigation = macroCall)

        assertSame(macroCall, PsiUtils.positionElement(expandedImpl, scope))
    }

    fun testAnElementWhoseNavigationElementIsOutsideTheScopeHasNoPosition() {
        val librarySource = element(textOffset = 10, file = file(inScope = false))
        val libraryClass = element(textOffset = 5, file = file(inScope = false), navigation = librarySource)

        assertNull(PsiUtils.positionElement(libraryClass, scope))
    }

    fun testALightElementThatNavigatesToItselfHasNoPosition() {
        val lightElement = element(textOffset = -1, file = file(inScope = true))

        assertNull(PsiUtils.positionElement(lightElement, scope))
    }

    // The Go search returns each library implementation under the project scope (#134). The file
    // of a hit comes from its stub, and the text offset can need the syntax tree of the file.
    fun testAHitOutsideTheScopeIsDroppedBeforeItsTextOffsetIsRead() {
        val libraryMethod = element(textOffset = 77, file = file(inScope = false))

        assertNull(PsiUtils.positionElement(libraryMethod, scope))
        verify(exactly = 0) { libraryMethod.textOffset }
    }
}
