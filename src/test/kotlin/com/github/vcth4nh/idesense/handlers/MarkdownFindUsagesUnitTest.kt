package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.handlers.markdown.MarkdownFindUsages
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiReference
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import junit.framework.TestCase

class MarkdownFindUsagesUnitTest : TestCase() {

    // The Markdown classes are not on the unit-test classpath. The live row of ripgrep pins the true case.
    fun testAReferenceOutsideACodeSpanIsNotDynamic() {
        val element = mockk<PsiElement>(relaxed = true)
        val reference = mockk<PsiReference> { every { this@mockk.element } returns element }

        assertFalse(MarkdownFindUsages.isDynamicUsage(reference))
        verify(exactly = 0) { element.references }
    }
}
