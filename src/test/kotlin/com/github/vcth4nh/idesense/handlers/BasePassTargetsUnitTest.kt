package com.github.vcth4nh.idesense.handlers

import com.intellij.psi.PsiElement
import io.mockk.mockk
import junit.framework.TestCase

// The targets of the base pass of the find usages search: each base declaration, then the other
// overriding declarations of that base declaration.
class BasePassTargetsUnitTest : TestCase() {

    private val anchor = mockk<PsiElement>()
    private val baseA = mockk<PsiElement>()
    private val baseB = mockk<PsiElement>()
    private val anchorOverride = mockk<PsiElement>()
    private val siblingA = mockk<PsiElement>()
    private val siblingB = mockk<PsiElement>()
    private val shared = mockk<PsiElement>()

    private fun targets(
        bases: List<PsiElement>,
        overrides: List<PsiElement>,
        overridesOf: Map<PsiElement, List<PsiElement>>,
    ): List<PsiElement> =
        FindUsagesHandlerSearch.basePassTargets(anchor, bases, overrides) { overridesOf[it].orEmpty() }.toList()

    fun testWithNoOverridingDeclarationOfABaseTheTargetsAreTheBases() {
        assertEquals(listOf(baseA, baseB), targets(listOf(baseA, baseB), emptyList(), emptyMap()))
    }

    fun testTheOtherImplementationsOfABaseFollowThatBase() {
        val result = targets(
            listOf(baseA, baseB), emptyList(),
            mapOf(baseA to listOf(siblingA), baseB to listOf(siblingB)),
        )
        assertEquals(listOf(baseA, siblingA, baseB, siblingB), result)
    }

    // DeferringDispatcher::dispatch: the overriding declarations of Dispatcher::dispatch are the
    // anchor and the two other implementations.
    fun testTheAnchorAndItsOverridingDeclarationsAreNoTargetOfTheBasePass() {
        val result = targets(
            listOf(baseA), listOf(anchorOverride),
            mapOf(baseA to listOf(anchor, siblingA, anchorOverride, siblingB)),
        )
        assertEquals(listOf(baseA, siblingA, siblingB), result)
    }

    fun testATargetIsSearchedOneTime() {
        val result = targets(
            listOf(baseA, baseB), emptyList(),
            // baseB overrides baseA, and both bases have the same other implementation.
            mapOf(baseA to listOf(baseB, shared), baseB to listOf(shared, siblingB)),
        )
        assertEquals(listOf(baseA, shared, baseB, siblingB), result)
    }

    fun testTheOverridingDeclarationsOfABaseComeOnlyAfterTheSearchOfThatBase() {
        val asked = mutableListOf<PsiElement>()
        val sequence = FindUsagesHandlerSearch.basePassTargets(anchor, listOf(baseA, baseB), emptyList()) {
            asked.add(it)
            if (it === baseA) listOf(siblingA) else emptyList()
        }
        val iterator = sequence.iterator()
        assertSame(baseA, iterator.next())
        assertTrue(asked.isEmpty())
        assertSame(siblingA, iterator.next())
        assertEquals(listOf(baseA), asked)
    }
}
