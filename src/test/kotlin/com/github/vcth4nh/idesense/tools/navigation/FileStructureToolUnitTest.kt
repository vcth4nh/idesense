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

    // Character 79 is the first half of a surrogate pair: the cut keeps no half of the pair.
    fun testCutKeepsNoHalfOfASurrogatePair() =
        assertEquals("a".repeat(78) + "…", name("a".repeat(78) + "😀\n" + "b".repeat(10)))

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

    // #335: the signature of a node (the location text of the IDE) is one line. A signature that had
    // a line break is cut at 80 characters, as a name.
    private fun signature(text: String?) = FileStructureTool.nodeSignature(text)

    fun testSignatureWithLineBreaksIsOneLine() =
        assertEquals("first line second line", signature("first line\nsecond line"))

    fun testSignatureWithCarriageReturnAndLineFeedIsOneLine() =
        assertEquals("first line second line", signature("first line\r\nsecond line"))

    fun testSignatureWithIndentedLinesAndAnEmptyLineIsOneLine() =
        assertEquals("para one continues para two", signature("para one\n    continues\n\n  para two"))

    fun testSignatureLosesTheWhiteSpaceAtTheTwoEnds() =
        assertEquals("text", signature("  \n\ttext \r\n "))

    fun testBlankSignatureIsAbsent() {
        assertNull(signature(null))
        assertNull(signature(""))
        assertNull(signature(" \n\t "))
    }

    fun testSignatureOfOneLineStaysAsItIs() =
        assertEquals("(a: Int, b: Int): Unit", signature("(a: Int, b: Int): Unit"))

    fun testLongSignatureOfSeveralLinesIsCutTo80CharactersThatEndWithAnEllipsis() {
        val result = signature("a".repeat(60) + "\n   " + "b".repeat(60) + "\n\n" + "c".repeat(60))
        assertEquals("a".repeat(60) + " " + "b".repeat(18) + "…", result)
        assertEquals(80, result!!.length)
    }

    fun testSignatureWithACarriageReturnLongerThan80IsCut() =
        assertEquals("a".repeat(50) + " " + "b".repeat(28) + "…", signature("a".repeat(50) + "\r\n" + "b".repeat(50)))

    fun testSignatureWithALineBreakOf80CharactersAfterTheWhiteSpaceRuleIsNotCut() =
        assertEquals("a".repeat(40) + " " + "b".repeat(39), signature("a".repeat(40) + "\n" + " ".repeat(40) + "b".repeat(39)))

    fun testSignatureWithALineBreakOf81CharactersIsCut() =
        assertEquals("a".repeat(40) + " " + "b".repeat(38) + "…", signature("a".repeat(40) + "\n" + "b".repeat(40)))

    // Character 79 is the first half of a surrogate pair: the cut keeps no half of the pair.
    fun testSignatureCutKeepsNoHalfOfASurrogatePair() =
        assertEquals("a".repeat(78) + "…", signature("a".repeat(78) + "😀\n" + "b".repeat(10)))

    fun testLongSignatureWithNoLineBreakStaysWhole() =
        assertEquals("a".repeat(60) + " " + "b".repeat(60), signature("a".repeat(60) + " \t  " + "b".repeat(60)))

    // The white space at the two ends goes away first: the text left has no line break.
    fun testLongSignatureWithLineBreaksOnlyAtTheTwoEndsStaysWhole() =
        assertEquals("a".repeat(100), signature("\n  " + "a".repeat(100) + "\r\n"))
}
