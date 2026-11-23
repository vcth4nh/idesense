package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.util.ProjectUtils
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.impl.FakePsiElement
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * A class with no position stays in the result of ide_find_class, with no line and no column
 * (#316). A compiled class has the text offset -1 when the IDE cannot match it to the decompiled
 * text of its class file (`ClsElementImpl.getTextOffset`). The test platform has no such class, so
 * [NoPosition] has this text offset in a source file.
 */
class FindClassToolTest : BasePlatformTestCase() {

    fun testClassWithNoPositionHasNoLineAndNoColumn() {
        val file = myFixture.configureByText("A.java", "class A {}\n")

        val match = FindClassTool().convertToSymbolMatch(NoPosition(file), project, GlobalSearchScope.allScope(project))

        assertNotNull(match)
        assertEquals("Broken", match!!.name)
        assertEquals(ProjectUtils.getToolFilePath(project, file.virtualFile), match.file)
        assertNull(match.line)
        assertNull(match.column)
    }

    fun testClassWithAPositionKeepsItsLineAndColumn() {
        val file = myFixture.configureByText("A.java", "\nclass A {}\n")
        val a = PsiTreeUtil.findChildOfType(file, PsiClass::class.java)!!

        val match = FindClassTool().convertToSymbolMatch(a, project, GlobalSearchScope.allScope(project))

        assertNotNull(match)
        assertEquals(2, match!!.line)
        assertEquals(7, match.column)
    }

    private class NoPosition(private val file: PsiFile) : FakePsiElement() {
        override fun getParent(): PsiElement = file
        override fun getContainingFile(): PsiFile = file
        override fun getName(): String = "Broken"
        override fun getTextOffset(): Int = -1
    }
}
