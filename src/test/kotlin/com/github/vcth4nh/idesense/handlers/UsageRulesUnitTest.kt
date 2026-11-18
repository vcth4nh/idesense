package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.constants.UsageMatch
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiReference
import io.mockk.every
import io.mockk.mockk
import junit.framework.TestCase

// The drop rule and the mark rule of the find usages search for each usage.
class UsageRulesUnitTest : TestCase() {

    private val anchor = mockk<PsiElement>()

    private fun usageIn(file: VirtualFile): PsiElement {
        val psiFile = mockk<PsiFile>()
        every { psiFile.virtualFile } returns file
        val element = mockk<PsiElement>()
        every { element.containingFile } returns psiFile
        return element
    }

    private fun dropping(kind: String?): SuperMethodsProvider {
        val provider = mockk<SuperMethodsProvider>()
        every { provider.droppedUsageKind(any(), any()) } returns kind
        return provider
    }

    fun testADroppedPositionCountsOneTime() {
        val dropped = LinkedHashMap<String, Int>()
        val rules = UsageRules(dropping("KIND"), anchor, dropped)
        val file = mockk<VirtualFile>()

        assertTrue(rules.drops(usageIn(file), 10))
        // A second pass finds the same position again.
        assertTrue(rules.drops(usageIn(file), 10))
        assertTrue(rules.drops(usageIn(file), 20))
        assertTrue(rules.drops(usageIn(mockk()), 10))

        assertEquals(mapOf("KIND" to 3), dropped)
    }

    fun testTheKindsKeepTheOrderOfTheirFirstDrop() {
        val dropped = LinkedHashMap<String, Int>()
        val provider = mockk<SuperMethodsProvider>()
        val first = usageIn(mockk())
        val second = usageIn(mockk())
        every { provider.droppedUsageKind(first, anchor) } returns "B"
        every { provider.droppedUsageKind(second, anchor) } returns "A"
        val rules = UsageRules(provider, anchor, dropped)

        rules.drops(first, 1)
        rules.drops(second, 1)

        assertEquals(listOf("B", "A"), dropped.keys.toList())
    }

    fun testTheDropDoesNotNeedACounter() {
        assertTrue(UsageRules(dropping("KIND"), anchor, null).drops(usageIn(mockk()), 1))
    }

    fun testAUsageWithNoKindStays() {
        val dropped = LinkedHashMap<String, Int>()

        assertFalse(UsageRules(dropping(null), anchor, dropped).drops(usageIn(mockk()), 1))
        assertFalse(UsageRules(null, anchor, dropped).drops(usageIn(mockk()), 1))
        assertTrue(dropped.isEmpty())
    }

    fun testAThrowingDropRuleKeepsTheUsage() {
        val provider = mockk<SuperMethodsProvider>()
        every { provider.droppedUsageKind(any(), any()) } throws IllegalStateException("broken")
        val dropped = LinkedHashMap<String, Int>()

        assertFalse(UsageRules(provider, anchor, dropped).drops(usageIn(mockk()), 1))
        assertTrue(dropped.isEmpty())
    }

    fun testACancellationLeavesTheDropRule() {
        val provider = mockk<SuperMethodsProvider>()
        every { provider.droppedUsageKind(any(), any()) } throws ProcessCanceledException()

        try {
            UsageRules(provider, anchor, null).drops(usageIn(mockk()), 1)
            fail("ProcessCanceledException expected")
        } catch (_: ProcessCanceledException) {
        }
    }

    fun testTheMarkOfTheProviderWins() {
        val provider = mockk<SuperMethodsProvider>()
        val reference = mockk<PsiReference>()
        every { provider.usageMark(reference, anchor, null) } returns UsageMatch.OVERRIDE

        assertEquals(UsageMatch.OVERRIDE, UsageRules(provider, anchor, null).mark(reference, null))
    }

    fun testAThrowingMarkRuleGivesThePassMark() {
        val provider = mockk<SuperMethodsProvider>()
        every { provider.usageMark(any(), any(), any()) } throws IllegalStateException("broken")

        assertEquals(UsageMatch.BASE, UsageRules(provider, anchor, null).mark(mockk(), UsageMatch.BASE))
        assertEquals(UsageMatch.BASE, UsageRules(null, anchor, null).mark(mockk(), UsageMatch.BASE))
    }
}
