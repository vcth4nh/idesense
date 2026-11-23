package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.tools.models.SymbolMatch
import junit.framework.TestCase

/** The key of a match of ide_find_class, for the dedup and for the seen keys of the pagination (#316). */
class FindClassToolUnitTest : TestCase() {

    // Two nested classes with the same name in one class file that the IDE cannot match to its
    // decompiled text: neither class has a position.
    fun testTwoMatchesWithNoPositionAndTheSameNameStayApart() {
        val file = "jar:///lib.jar!/p/Outer.class"
        val first = SymbolMatch("B", "p.Outer.A.B", "CLASS", file, null, null)
        val second = SymbolMatch("B", "p.Outer.C.B", "CLASS", file, null, null)

        assertEquals(listOf(first, second), listOf(first, second).distinctBy { FindClassTool.matchKey(it) })
    }

    fun testAMatchWithAPositionKeepsItsKey() {
        assertEquals("src/A.kt:3:7:A", FindClassTool.matchKey(SymbolMatch("A", "p.A", "CLASS", "src/A.kt", 3, 7)))
        assertEquals("src/B.java:12:14:B", FindClassTool.matchKey(SymbolMatch("B", null, "INTERFACE", "src/B.java", 12, 14)))
    }
}
