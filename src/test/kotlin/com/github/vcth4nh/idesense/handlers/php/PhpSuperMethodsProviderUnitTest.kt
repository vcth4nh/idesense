package com.github.vcth4nh.idesense.handlers.php

import com.github.vcth4nh.idesense.constants.UsageMatch
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiReference
import com.intellij.psi.search.SearchScope
import io.mockk.mockk
import junit.framework.TestCase

class PhpSuperMethodsProviderUnitTest : TestCase() {

    private val anchor = mockk<PsiElement>()
    private val override = mockk<PsiElement>()
    private val base = mockk<PsiElement>()
    private val other = mockk<PsiElement>()

    private fun mark(targets: List<PsiElement>, passMark: String?, hasBase: Boolean = true): String? =
        PhpSuperMethodsProvider.usageMarkOf(targets, anchor, listOf(override), hasBase, passMark) { a, b -> a === b }

    fun testAUsageThatResolvesToTheAnchorHasNoMarkInEachPass() {
        assertNull(mark(listOf(anchor), null))
        assertNull(mark(listOf(anchor), UsageMatch.BASE))
        assertNull(mark(listOf(anchor), UsageMatch.OVERRIDE))
    }

    fun testAUsageThatResolvesToAnOverridingMethodHasOverrideInEachPass() {
        assertEquals(UsageMatch.OVERRIDE, mark(listOf(override), null))
        assertEquals(UsageMatch.OVERRIDE, mark(listOf(override), UsageMatch.BASE))
        assertEquals(UsageMatch.OVERRIDE, mark(listOf(override), UsageMatch.OVERRIDE))
    }

    fun testTheAnchorAmongTheTargetsWinsOverAnOverridingMethod() {
        assertNull(mark(listOf(override, anchor), UsageMatch.OVERRIDE))
        assertNull(mark(listOf(base, anchor), UsageMatch.BASE))
    }

    fun testAnOverridingMethodAmongTheTargetsWinsOverABaseMethod() {
        assertEquals(UsageMatch.OVERRIDE, mark(listOf(base, override), UsageMatch.BASE))
    }

    fun testAUsageWithNoTargetKeepsThePassMark() {
        assertNull(mark(emptyList(), null))
        assertEquals(UsageMatch.BASE, mark(emptyList(), UsageMatch.BASE))
        assertEquals(UsageMatch.OVERRIDE, mark(emptyList(), UsageMatch.OVERRIDE))
    }

    fun testAnotherTargetKeepsThePassMarkOfABaseOrOverridePass() {
        assertEquals(UsageMatch.BASE, mark(listOf(base), UsageMatch.BASE))
        assertEquals(UsageMatch.OVERRIDE, mark(listOf(other), UsageMatch.OVERRIDE))
    }

    // Circle::area of the PHP fixture: the references of the method hold the calls on a value of
    // the type Shape, which resolve to Shape::area.
    fun testAnotherTargetInTheDirectPassIsBaseWhenTheAnchorHasABaseMethod() {
        assertEquals(UsageMatch.BASE, mark(listOf(base), null, hasBase = true))
    }

    fun testAnotherTargetInTheDirectPassIsDynamicWhenTheAnchorHasNoBaseMethod() {
        assertEquals(UsageMatch.DYNAMIC, mark(listOf(other), null, hasBase = false))
    }

    fun testTheRuleUsesTheEquivalenceAndNotTheIdentity() {
        val copy = mockk<PsiElement>()
        val result = PhpSuperMethodsProvider.usageMarkOf(listOf(copy), anchor, emptyList(), false, UsageMatch.BASE) { a, b ->
            (a === copy && b === anchor) || (a === anchor && b === copy)
        }
        assertNull(result)
    }

    // The PHP plugin is not on the unit-test classpath, and the test tree has no stub of a PHP
    // class. The strict mocks fail on each call, thus the tests also prove that the hooks do not
    // read the element or resolve the reference.
    fun testNoBaseDeclarationsWhenThePhpPluginIsAbsent() {
        assertTrue(PhpSuperMethodsProvider().findBaseDeclarations(mockk<PsiElement>()).isEmpty())
    }

    fun testNoOverridingDeclarationsWhenThePhpPluginIsAbsent() {
        assertTrue(PhpSuperMethodsProvider().findOverridingDeclarations(mockk<PsiElement>()).isEmpty())
    }

    fun testNoDirectReferencesWhenThePhpPluginIsAbsent() {
        assertNull(PhpSuperMethodsProvider().findDirectReferences(mockk<PsiElement>(), mockk<SearchScope>()))
    }

    fun testNoDropWhenThePhpPluginIsAbsent() {
        assertNull(PhpSuperMethodsProvider().droppedUsageKind(mockk<PsiElement>(), mockk<PsiElement>()))
    }

    fun testThePassMarkWhenThePhpPluginIsAbsent() {
        val provider = PhpSuperMethodsProvider()
        assertEquals(UsageMatch.BASE, provider.usageMark(mockk<PsiReference>(), mockk<PsiElement>(), UsageMatch.BASE))
        assertNull(provider.usageMark(mockk<PsiReference>(), mockk<PsiElement>(), null))
    }
}
