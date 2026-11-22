package com.github.vcth4nh.idesense.tools.navigation

import junit.framework.TestCase

// #199: the name of a node in the outline of ide_file_structure is one line. A name that had a
// line break (source text of several lines) is cut at 80 characters.
class FileStructureToolUnitTest : TestCase() {

    private fun name(text: String?) = FileStructureTool.nodeName(text, element = null)

    fun testEachRunOfWhiteSpaceBecomesOneSpace() = assertEquals(
        "...(cond ? [ { name: a, value: b, }, ] : [])",
        name("...(cond\n        ? [\n              {\n\t\t  name: a,\n  value: b,\n  },\n   ]\n    : [])"),
    )

    // A function signature in the name of a JavaScript, TypeScript, Go or PHP node stays whole.
    fun testLongNameWithNoLineBreakStaysComplete() {
        val text = "send(notification: BeanModel, msg: string, monitorJSON: Object|null, heartbeatJSON: Object|null): Promise<string>"
        assertEquals(text, name(text))
    }

    fun testLongNameWithNoLineBreakGetsTheWhiteSpaceRuleOnly() =
        assertEquals("a".repeat(60) + " " + "b".repeat(60), name("a".repeat(60) + " \t  " + "b".repeat(60)))

    fun testNameWithALineBreakLongerThan80IsCutTo80CharactersThatEndWithAnEllipsis() {
        val result = name("a".repeat(50) + "\n    " + "b".repeat(50))
        assertEquals("a".repeat(50) + " " + "b".repeat(28) + "…", result)
        assertEquals(80, result!!.length)
    }

    fun testNameWithACarriageReturnLongerThan80IsCut() =
        assertEquals("a".repeat(50) + " " + "b".repeat(28) + "…", name("a".repeat(50) + "\r\n" + "b".repeat(50)))

    fun testNameWithALineBreakOf80CharactersAfterTheWhiteSpaceRuleIsNotCut() {
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
