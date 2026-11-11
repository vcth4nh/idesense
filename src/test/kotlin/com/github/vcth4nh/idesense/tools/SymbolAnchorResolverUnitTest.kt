package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.handlers.PopupSearchCandidate
import com.github.vcth4nh.idesense.handlers.PopupSearchResult
import com.github.vcth4nh.idesense.tools.models.SymbolMatch
import com.intellij.navigation.NavigationItem
import io.mockk.mockk
import junit.framework.TestCase

class SymbolAnchorResolverUnitTest : TestCase() {

    private fun candidates(count: Int): List<SymbolMatch> = (1..count).map { index ->
        SymbolMatch(name = "Provision", qualifiedName = "pkg$index.Provision", kind = "METHOD", file = "f$index.go", line = index, column = 1)
    }

    fun testASmallCandidateListReportsItsSize() {
        val ambiguous = SymbolResolution.Ambiguous(candidates(2), totalMatches = 2)

        assertEquals("2 matches", ambiguous.matchCount)
    }

    // The count is the number of the matches, not the length of the cut list (#131).
    fun testACutCandidateListReportsTheNumberOfAllMatches() {
        val ambiguous = SymbolResolution.Ambiguous(candidates(10), totalMatches = 107)

        assertEquals("107 matches, the first 10 are listed", ambiguous.matchCount)
    }

    fun testASearchThatStoppedAtItsLimitReportsAMinimum() {
        val ambiguous = SymbolResolution.Ambiguous(candidates(10), totalMatches = 200, searchWasCut = true)

        assertEquals("200 or more matches, the first 10 are listed", ambiguous.matchCount)
    }

    private fun popupResult(vararg names: String) = PopupSearchResult(
        candidates = names.map { name -> PopupSearchCandidate(item = mockk<NavigationItem>(), fullName = name) },
        isQualifiedQuery = false,
    )

    // The field `handler` is not the type `Handler` (#131).
    fun testAnItemWithTheCaseOfTheNameWins() {
        val searches = mutableListOf<Boolean>()

        val result = SymbolAnchorResolver.exactCaseFirst { ignoreCase ->
            searches.add(ignoreCase)
            if (ignoreCase) popupResult("Handler", "handler") else popupResult("Handler")
        }

        assertEquals(listOf("Handler"), result.candidates.map { it.fullName })
        assertEquals("The search without case does not run", listOf(false), searches)
    }

    // A PHP class name has no case: `shape` is the class `Shape`.
    fun testWithNoItemOfThatCaseTheSearchIgnoresTheCase() {
        val result = SymbolAnchorResolver.exactCaseFirst { ignoreCase ->
            if (ignoreCase) popupResult("Shape") else popupResult()
        }

        assertEquals(listOf("Shape"), result.candidates.map { it.fullName })
    }
}
