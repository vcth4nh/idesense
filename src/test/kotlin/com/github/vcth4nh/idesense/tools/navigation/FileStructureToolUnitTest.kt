package com.github.vcth4nh.idesense.tools.navigation

import junit.framework.TestCase

// #199: the name of a node in the outline of ide_file_structure is one line of at most 80 characters.
class FileStructureToolUnitTest : TestCase() {

    private fun name(text: String?) = FileStructureTool.nodeName(text, element = null)

    fun testEachRunOfWhiteSpaceBecomesOneSpace() = assertEquals(
        "...(cond ? [ { name: a, value: b, }, ] : [])",
        name("...(cond\n        ? [\n              {\n\t\t  name: a,\n  value: b,\n  },\n   ]\n    : [])"),
    )

    fun testNameOf80CharactersStays() {
        val text = "a".repeat(80)
        assertEquals(text, name(text))
    }

    fun testLongNameIsCutTo80CharactersThatEndWithAnEllipsis() {
        val result = name("a".repeat(79) + "bc")
        assertEquals("a".repeat(79) + "…", result)
        assertEquals(80, result!!.length)
    }

    fun testCutComesAfterTheWhiteSpaceRule() {
        val text = "a".repeat(40) + "\n" + " ".repeat(40) + "b".repeat(39)
        assertEquals("a".repeat(40) + " " + "b".repeat(39), name(text))
    }

    // A node with no text stays out of the outline, except an object literal of JavaScript or
    // TypeScript (#198). The test platform has no JavaScript PSI.
    fun testNodeWithNoTextHasNoName() {
        assertNull(name(null))
        assertNull(name(" \n "))
    }
}
