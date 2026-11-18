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
    private val sibling = mockk<PsiElement>()
    private val other = mockk<PsiElement>()

    // [base] is the base declaration of [anchor] unless the test gives [bases].
    private fun mark(targets: List<PsiElement>, passMark: String?, bases: List<PsiElement> = listOf(base)): String? =
        PhpSuperMethodsProvider.usageMarkOf(targets, anchor, bases, listOf(override), passMark) { a, b -> a === b }

    // Circle::area of the PHP fixture: for a call on a value of the abstract type Shape, multiResolve
    // gives Shape::area and each implementation (Circle::area, Rectangle::area).
    fun testACallThroughTheBaseTypeHasBaseAlsoWhenTheTargetsHoldTheAnchor() {
        assertEquals(UsageMatch.BASE, mark(listOf(base, anchor, sibling), null))
        assertEquals(UsageMatch.BASE, mark(listOf(base, anchor, sibling), UsageMatch.BASE))
        assertEquals(UsageMatch.BASE, mark(listOf(base, anchor, override), UsageMatch.OVERRIDE))
    }

    fun testABaseDeclarationAmongTheTargetsWinsOverAnOverridingMethod() {
        assertEquals(UsageMatch.BASE, mark(listOf(base, override), null))
    }

    fun testAUsageThatResolvesToTheAnchorHasNoMarkInEachPass() {
        assertNull(mark(listOf(anchor), null))
        assertNull(mark(listOf(anchor), UsageMatch.BASE))
        assertNull(mark(listOf(anchor), UsageMatch.OVERRIDE))
    }

    // Shape::area of the PHP fixture or Dispatcher::dispatch of phpunit: the anchor is in an abstract
    // class or an interface and has no base, and a call on a value of its type also resolves to the
    // implementations.
    fun testTheAnchorAmongTheTargetsWinsOverAnOverridingMethod() {
        assertNull(mark(listOf(anchor, override), null, bases = emptyList()))
        assertNull(mark(listOf(override, anchor), UsageMatch.OVERRIDE, bases = emptyList()))
    }

    fun testAUsageThatResolvesToAnOverridingMethodHasOverrideInEachPass() {
        assertEquals(UsageMatch.OVERRIDE, mark(listOf(override), null))
        assertEquals(UsageMatch.OVERRIDE, mark(listOf(override), UsageMatch.BASE))
        assertEquals(UsageMatch.OVERRIDE, mark(listOf(override), UsageMatch.OVERRIDE))
    }

    fun testAUsageWithNoTargetKeepsThePassMark() {
        assertNull(mark(emptyList(), null))
        assertEquals(UsageMatch.BASE, mark(emptyList(), UsageMatch.BASE))
        assertEquals(UsageMatch.OVERRIDE, mark(emptyList(), UsageMatch.OVERRIDE))
    }

    fun testATargetThatIsABaseDeclarationHasBaseInTheBasePass() {
        assertEquals(UsageMatch.BASE, mark(listOf(base), UsageMatch.BASE))
    }

    fun testAnotherTargetKeepsThePassMarkOfABaseOrOverridePass() {
        assertEquals(UsageMatch.BASE, mark(listOf(other), UsageMatch.BASE))
        assertEquals(UsageMatch.OVERRIDE, mark(listOf(other), UsageMatch.OVERRIDE))
    }

    // DeferringDispatcher::dispatch: the base pass also searches DirectDispatcher::dispatch, another
    // implementation of Dispatcher::dispatch. A call on a DirectDispatcher value resolves to it.
    fun testAUsageOfAnotherImplementationOfTheBaseHasBase() {
        assertEquals(UsageMatch.BASE, mark(listOf(sibling), UsageMatch.BASE))
    }

    fun testAnotherTargetInTheDirectPassIsBaseWhenTheAnchorHasABaseMethod() {
        assertEquals(UsageMatch.BASE, mark(listOf(other), null))
    }

    fun testAnotherTargetInTheDirectPassIsDynamicWhenTheAnchorHasNoBaseMethod() {
        assertEquals(UsageMatch.DYNAMIC, mark(listOf(other), null, bases = emptyList()))
    }

    fun testTheRuleUsesTheEquivalenceAndNotTheIdentity() {
        val copy = mockk<PsiElement>()
        val same = { a: PsiElement, b: PsiElement -> a === b || (a === copy && b === anchor) || (a === anchor && b === copy) }
        assertNull(PhpSuperMethodsProvider.usageMarkOf(listOf(copy), anchor, emptyList(), emptyList(), UsageMatch.BASE, same))
        val baseCopy = mockk<PsiElement>()
        val sameBase = { a: PsiElement, b: PsiElement -> a === b || (a === baseCopy && b === base) || (a === base && b === baseCopy) }
        assertEquals(UsageMatch.BASE, PhpSuperMethodsProvider.usageMarkOf(listOf(baseCopy, anchor), anchor, listOf(base), emptyList(), null, sameBase))
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
