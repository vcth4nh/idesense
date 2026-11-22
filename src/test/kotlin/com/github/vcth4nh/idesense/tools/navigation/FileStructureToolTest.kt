package com.github.vcth4nh.idesense.tools.navigation

import com.intellij.psi.PsiElement
import com.intellij.psi.PsiMethod
import com.intellij.psi.impl.FakePsiElement
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * The line of a node in the outline of ide_file_structure is the line of its navigation element:
 * the Structure window goes there (#197). An example is the node `default` of a JavaScript
 * `export default { ... }` object: its element is not physical, its text offset is 0, and its
 * navigation element is the first member of the object. [NavigatesTo] has the same form.
 */
class FileStructureToolTest : BasePlatformTestCase() {

    fun testLineIsTheLineOfTheNavigationElement() {
        val file = myFixture.configureByText("A.java", "class A {\n\n    void m() {}\n}\n")
        val m = PsiTreeUtil.findChildOfType(file, PsiMethod::class.java)!!

        assertEquals(3, FileStructureTool.lineOf(project, NavigatesTo(target = m, parent = m), file))
    }

    // For example a compiled class and its source: the line stays a line of the file of the outline.
    fun testLineStaysTheLineOfTheElementWhenTheNavigationElementIsInAnotherFile() {
        val other = myFixture.addFileToProject("B.java", "class B {\n\n\n\n    void n() {}\n}\n")
        val n = PsiTreeUtil.findChildOfType(other, PsiMethod::class.java)!!
        val file = myFixture.configureByText("A.java", "class A {\n    void m() {}\n}\n")
        val m = PsiTreeUtil.findChildOfType(file, PsiMethod::class.java)!!

        assertEquals(2, FileStructureTool.lineOf(project, NavigatesTo(target = n, parent = m, offset = m.textOffset), file))
    }

    private class NavigatesTo(
        private val target: PsiElement,
        private val parent: PsiElement,
        private val offset: Int = 0,
    ) : FakePsiElement() {
        override fun getParent(): PsiElement = parent
        override fun getNavigationElement(): PsiElement = target
        override fun getTextOffset(): Int = offset
    }
}
