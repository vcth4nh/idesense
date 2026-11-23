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
 * [AtOffset] has this text offset in a source file.
 */
class FindClassToolTest : BasePlatformTestCase() {

    // The fake element stands for the offset -1 of a compiled element with no mirror. It does not
    // cover the navigationElement path of a real ClsClassImpl.
    fun testClassWithNoPositionHasNoLineAndNoColumn() {
        val file = myFixture.configureByText("A.java", "class A {}\n")

        val match = FindClassTool().convertToSymbolMatch(AtOffset(file, -1), project, GlobalSearchScope.allScope(project))

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

    fun testOffsetEqualToTheTextLengthIsAPosition() {
        val file = myFixture.configureByText("A.java", "class A {}\n")

        val match = FindClassTool().convertToSymbolMatch(AtOffset(file, file.textLength), project, GlobalSearchScope.allScope(project))

        assertNotNull(match)
        assertEquals(2, match!!.line)
        assertEquals(1, match.column)
    }

    fun testOffsetZeroInAnEmptyDocumentIsAPosition() {
        val file = myFixture.configureByText("A.java", "")

        val match = FindClassTool().convertToSymbolMatch(AtOffset(file, 0), project, GlobalSearchScope.allScope(project))

        assertNotNull(match)
        assertEquals(1, match!!.line)
        assertEquals(1, match.column)
    }

    private class AtOffset(private val file: PsiFile, private val offset: Int) : FakePsiElement() {
        override fun getParent(): PsiElement = file
        override fun getContainingFile(): PsiFile = file
        override fun getName(): String = "Broken"
        override fun getTextOffset(): Int = offset
    }
}
