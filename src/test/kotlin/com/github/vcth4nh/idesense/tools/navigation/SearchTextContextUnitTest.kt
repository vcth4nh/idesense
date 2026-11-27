package com.github.vcth4nh.idesense.tools.navigation

import junit.framework.TestCase

/**
 * The `context` filter keeps the set of a filter of Find in Files, and the label is one of three,
 * COMMENT first (#144). The four cases of the two memberships: in no set, in the comments set, in
 * the strings set, in both sets. A match in both sets is, for example, a Python docstring: its
 * token is in the string literal set of the parser definition and has the highlighting of a doc
 * comment. No file type of the test platform has such a token, so only this test has the case.
 *
 * A membership is a pass of the matcher over the file, so the filter and the label read a set only
 * when the result needs it.
 */
class SearchTextContextUnitTest : TestCase() {

    private val cases = listOf(false to false, true to false, false to true, true to true)

    private val notRead: () -> Boolean = { fail("The set must not be read"); false }

    private fun kept(context: String) =
        cases.filter { (inComments, inStrings) -> SearchTextTool.keepsMatch(context, { inComments }, { inStrings }) }

    fun testEachContextValueKeepsTheSetOfItsFilter() {
        assertEquals(listOf(true to false, true to true), kept("comments"))
        assertEquals(listOf(false to true, true to true), kept("strings"))
        assertEquals(listOf(false to false), kept("code"))
    }

    fun testAllKeepsEachMatch() {
        assertEquals(cases, kept("all"))
        assertEquals(cases, kept("something else"))
    }

    fun testTheContextValueIsReadWithoutCase() {
        assertEquals(kept("comments"), kept("Comments"))
    }

    fun testTheLabelIsCommentFirstThenStringLiteralElseCode() {
        assertEquals(
            listOf("CODE", "COMMENT", "STRING_LITERAL", "COMMENT"),
            cases.map { (inComments, inStrings) -> SearchTextTool.contextLabel({ inComments }, { inStrings }) }
        )
    }

    fun testEachFilterReadsOnlyTheSetsThatItNeeds() {
        assertFalse(SearchTextTool.keepsMatch("comments", { false }, notRead))
        assertTrue(SearchTextTool.keepsMatch("comments", { true }, notRead))
        assertTrue(SearchTextTool.keepsMatch("strings", notRead, { true }))
        assertFalse(SearchTextTool.keepsMatch("code", { true }, notRead))
        assertTrue(SearchTextTool.keepsMatch("all", notRead, notRead))
    }

    fun testTheLabelReadsTheStringsSetOnlyForAMatchOutsideTheCommentsSet() {
        assertEquals("COMMENT", SearchTextTool.contextLabel({ true }, notRead))
    }
}
