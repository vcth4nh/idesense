package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.tools.models.ImplementationLocation
import com.intellij.openapi.progress.ProcessCanceledException
import junit.framework.TestCase

class ImplementationLocationsUnitTest : TestCase() {

    private fun location(name: String, line: Int, file: String = "demo.go") = ImplementationLocation(
        name = name,
        file = file,
        line = line,
        column = 10,
        kind = "METHOD",
        qualifiedName = "demo.B.$name",
    )

    // The platform takes an IndexOutOfBoundsException that leaves a search callback for index
    // damage and rebuilds the stub index (#129), so a failed conversion must stay in the callback.
    fun testAConversionFailureStopsTheSearchAndDoesNotLeaveTheCallback() {
        val collector = ImplementationLocations.Collector(limit = 10)

        val continueSearch = collector.addInCallback {
            throw IndexOutOfBoundsException("Wrong offset: -1. Should be in range: [0, 397046]")
        }

        assertFalse(continueSearch)
    }

    // A skipped hit would make a partial result look complete, so the failure is not lost.
    fun testTheConversionFailureIsThrownAfterTheSearch() {
        val collector = ImplementationLocations.Collector(limit = 10)
        val failure = IndexOutOfBoundsException("Wrong offset: -1")
        collector.addInCallback { throw failure }

        try {
            collector.throwFailure()
            fail("The failure of the conversion must reach the caller")
        } catch (e: IndexOutOfBoundsException) {
            assertSame(failure, e)
        }
    }

    fun testASearchWithNoFailureThrowsNothing() {
        val collector = ImplementationLocations.Collector(limit = 10)
        collector.addInCallback { location("M", line = 6) }

        collector.throwFailure()

        assertEquals(listOf(6), collector.results.map { it.line })
    }

    fun testACancellationLeavesTheCallback() {
        val collector = ImplementationLocations.Collector(limit = 10)

        try {
            collector.addInCallback { throw ProcessCanceledException() }
            fail("The cancellation must reach the search")
        } catch (_: ProcessCanceledException) {
        }
    }

    // GoLand reports a promoted method as a second hit at the position of the declared method.
    fun testAHitAtThePositionOfAnEarlierHitIsNotCollectedAgain() {
        val collector = ImplementationLocations.Collector(limit = 10)

        collector.add(location("M", line = 6))
        collector.add(location("M", line = 6))
        collector.add(location("M", line = 20))

        assertEquals(listOf(6, 20), collector.results.map { it.line })
    }

    fun testTheCollectorStopsTheSearchAtItsLimit() {
        val collector = ImplementationLocations.Collector(limit = 2)

        assertTrue("One hit of two: the search continues", collector.add(location("M", line = 1)))
        assertFalse("Two hits of two: the search stops", collector.add(location("M", line = 2)))
    }

    fun testASkippedHitDoesNotStopTheSearch() {
        val collector = ImplementationLocations.Collector(limit = 1)

        assertTrue(collector.add(null))
        assertEquals(emptyList<ImplementationLocation>(), collector.results)
    }

    // The next-page search runs the search again and must return only hits that no page has.
    fun testAHitThatAnEarlierPageHasIsNotCollected() {
        val earlier = location("M", line = 6)
        val collector = ImplementationLocations.Collector(limit = 10, skipKeys = setOf(ImplementationLocations.key(earlier)))

        collector.add(earlier)
        collector.add(location("M", line = 20))

        assertEquals(listOf(20), collector.results.map { it.line })
    }

    fun testTheKeyIsThePaginationKeyOfTheTool() {
        assertEquals("demo.go:6:10:M", ImplementationLocations.key(location("M", line = 6)))
    }
}
