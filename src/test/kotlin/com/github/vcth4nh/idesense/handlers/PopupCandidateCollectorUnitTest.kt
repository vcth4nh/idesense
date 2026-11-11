package com.github.vcth4nh.idesense.handlers

import com.intellij.navigation.NavigationItem
import io.mockk.every
import io.mockk.mockk
import junit.framework.TestCase

class PopupCandidateCollectorUnitTest : TestCase() {

    private fun item(name: String): NavigationItem {
        val item = mockk<NavigationItem>()
        every { item.name } returns name
        return item
    }

    private fun exactName(name: String): (NavigationItem) -> Boolean = { it.name == name }

    // GoLand gives each symbol of the package `caddypki` for the text `PKI`, in the order of the
    // names, and the type `PKI` comes after more than 40 of them (#131).
    fun testAnAcceptedItemAfterManyOtherItemsIsCollected() {
        val collector = PopupCandidateCollector(limit = 40, accept = exactName("PKI"))
        val others = (1..100).map { item("caddypki.symbol$it") }
        val wanted = item("PKI")

        val continueAfterOthers = others.map { collector.offer(it) }
        collector.offer(wanted)

        assertTrue("An item that is not accepted does not stop the search", continueAfterOthers.all { it })
        assertEquals(listOf(wanted), collector.items)
    }

    fun testOnlyAnAcceptedItemCountsForTheLimit() {
        val collector = PopupCandidateCollector(limit = 2, accept = exactName("Handler"))

        assertTrue(collector.offer(item("handler")))
        assertTrue(collector.offer(item("Handler")))
        assertTrue(collector.offer(item("HandlerFunc")))
        assertFalse("The second accepted item fills the limit", collector.offer(item("Handler")))
        assertEquals(2, collector.items.size)
    }

    // The field `handler` is not the type `Handler` (#131).
    fun testTheExactNameFilterComparesWithCase() {
        val accept = PopupFaithfulSymbolSearch.exactNameFilter("Handler", ignoreCase = false) { it.name }

        assertTrue(accept(item("Handler")))
        assertFalse(accept(item("handler")))
        assertFalse(accept(item("HandlerFunc")))
    }

    // ide_find_symbol matches the exact name without case.
    fun testTheExactNameFilterCanIgnoreCase() {
        val accept = PopupFaithfulSymbolSearch.exactNameFilter("Handler", ignoreCase = true) { it.name }

        assertTrue(accept(item("Handler")))
        assertTrue(accept(item("handler")))
        assertFalse(accept(item("HandlerFunc")))
    }

    // GoLand gives a symbol two times. The limit and the match count are for different symbols.
    fun testTheExactNameFilterAcceptsAnItemOneTime() {
        val accept = PopupFaithfulSymbolSearch.exactNameFilter("Provision", ignoreCase = false) { it.name }
        val symbol = item("Provision")

        assertTrue(accept(symbol))
        assertFalse(accept(symbol))
        assertTrue(accept(item("Provision")))
    }

    // The search reads the items of an index name only when the name can hold the exact name.
    // GoLand has the index name `caddypki.CA` for the type `CA`, and the text `CA` also matches
    // `caddy.Config` and each other symbol of a package that starts with these letters.
    fun testAnIndexNameCanHoldTheExactNameWhenItEndsWithIt() {
        assertTrue(PopupFaithfulSymbolSearch.canHoldExactName("CA", "CA"))
        assertTrue(PopupFaithfulSymbolSearch.canHoldExactName("caddypki.CA", "CA"))
        assertFalse(PopupFaithfulSymbolSearch.canHoldExactName("caddy.Config", "CA"))
        assertFalse(PopupFaithfulSymbolSearch.canHoldExactName("caddypki.CAPool", "CA"))
    }

    // An index name can differ from the name of its element in a prefix and in case:
    // `$count` for a PHP field, `getFoo` for a property.
    fun testAnIndexNameWithAPrefixOrAnotherCaseCanHoldTheExactName() {
        assertTrue(PopupFaithfulSymbolSearch.canHoldExactName("\$count", "count"))
        assertTrue(PopupFaithfulSymbolSearch.canHoldExactName("getFoo", "foo"))
    }

    // The platform records for each contributor the names for which the processor answers true
    // (ContributorsBasedGotoByModel.processContributorNames). It continues with the next name
    // after each answer.
    fun testAnIndexNameThatCannotHoldTheExactNameIsNotGivenToTheSearch() {
        val given = mutableListOf<String>()
        val processor = PopupFaithfulSymbolSearch.exactNameProcessor("CA") { name -> given.add(name) }

        assertFalse(processor.process("caddy.Config"))
        assertTrue(processor.process("caddypki.CA"))
        assertEquals(listOf("caddypki.CA"), given)
    }

    fun testTheAnswerOfTheSearchForAnIndexNameIsKept() {
        val processor = PopupFaithfulSymbolSearch.exactNameProcessor("CA") { false }

        assertFalse(processor.process("caddypki.CA"))
    }

    fun testWithNoFilterEachItemCountsForTheLimit() {
        val collector = PopupCandidateCollector(limit = 2, accept = null)

        assertTrue(collector.offer(item("first")))
        assertFalse(collector.offer(item("second")))
        assertEquals(2, collector.items.size)
    }
}
