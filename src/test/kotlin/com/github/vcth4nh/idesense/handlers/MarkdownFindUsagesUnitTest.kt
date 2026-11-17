package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.handlers.markdown.MarkdownFindUsages
import com.intellij.psi.PsiElement
import io.mockk.mockk
import io.mockk.verify
import junit.framework.TestCase

class MarkdownFindUsagesUnitTest : TestCase() {

    // The Markdown classes are not on the unit-test classpath. The live row of ripgrep pins the true case.
    fun testAnElementOutsideACodeSpanIsNotDynamic() {
        val element = mockk<PsiElement>(relaxed = true)

        assertFalse(MarkdownFindUsages.isDynamicUsage(element))
        verify(exactly = 0) { element.references }
    }
}
