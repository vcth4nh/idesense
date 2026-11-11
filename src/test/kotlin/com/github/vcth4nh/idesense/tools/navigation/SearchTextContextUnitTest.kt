package com.github.vcth4nh.idesense.tools.navigation

import junit.framework.TestCase

class SearchTextContextUnitTest : TestCase() {

    fun testEachContextValueKeepsTheMatchesOfOneLabel() {
        assertEquals("CODE", SearchTextTool.requestedContextType("code"))
        assertEquals("COMMENT", SearchTextTool.requestedContextType("comments"))
        assertEquals("STRING_LITERAL", SearchTextTool.requestedContextType("strings"))
    }

    fun testAllKeepsTheMatchesOfEachLabel() {
        assertNull(SearchTextTool.requestedContextType("all"))
        assertNull(SearchTextTool.requestedContextType("something else"))
    }

    fun testTheContextValueIsReadWithoutCase() {
        assertEquals("COMMENT", SearchTextTool.requestedContextType("Comments"))
    }
}
