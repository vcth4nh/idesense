package com.github.vcth4nh.idesense.util

import junit.framework.TestCase

class LinePreviewUnitTest : TestCase() {

    fun testShortLineIsTrimmedOnly() {
        assertEquals("val x = foo()", LinePreview.around("    val x = foo()  ", matchStart = 12, matchLength = 3))
    }

    fun testLineAtTheLimitIsNotCut() {
        val line = "a".repeat(LinePreview.MAX_CHARS)
        assertEquals(line, LinePreview.around(line, matchStart = 0))
    }

    fun testLongLineWindowHoldsAMatchInTheMiddle() {
        val line = "x".repeat(5000) + "pickle" + "y".repeat(5000)
        val preview = LinePreview.around(line, matchStart = 5000, matchLength = 6)
        assertTrue(preview.startsWith("…"))
        assertTrue(preview.endsWith("…"))
        assertTrue(preview.contains("pickle"))
        assertEquals(LinePreview.MAX_CHARS + 2, preview.length)
    }

    fun testLongLineWindowAtTheStartHasNoLeadingMarker() {
        val line = "  pickle" + "y".repeat(5000)
        val preview = LinePreview.around(line, matchStart = 2, matchLength = 6)
        assertTrue(preview.startsWith("pickle"))
        assertTrue(preview.endsWith("…"))
        assertEquals(LinePreview.MAX_CHARS + 1, preview.length)
    }

    fun testLongLineWindowAtTheEndHasNoTrailingMarker() {
        val line = "x".repeat(5000) + "pickle"
        val preview = LinePreview.around(line, matchStart = 5000, matchLength = 6)
        assertTrue(preview.startsWith("…"))
        assertTrue(preview.endsWith("pickle"))
        assertEquals(LinePreview.MAX_CHARS + 1, preview.length)
    }

    fun testMatchLongerThanTheWindowShowsTheMatchStart() {
        val line = "x".repeat(1000) + "M".repeat(500) + "y".repeat(1000)
        val preview = LinePreview.around(line, matchStart = 1000, matchLength = 500)
        assertEquals("…" + "M".repeat(LinePreview.MAX_CHARS) + "…", preview)
    }

    fun testOutOfRangeMatchStartDoesNotThrow() {
        val line = "z".repeat(1000)
        assertTrue(LinePreview.around(line, matchStart = 99_999).endsWith("z"))
        assertTrue(LinePreview.around(line, matchStart = -5).startsWith("z"))
    }

    fun testCutDoesNotSplitASurrogatePair() {
        val emoji = "😀" // one code point, two chars
        val line = emoji.repeat(3000)
        val preview = LinePreview.around(line, matchStart = 3001)
        val body = preview.removePrefix("…").removeSuffix("…")
        assertFalse(body.first().isLowSurrogate())
        assertFalse(body.last().isHighSurrogate())
    }
}
