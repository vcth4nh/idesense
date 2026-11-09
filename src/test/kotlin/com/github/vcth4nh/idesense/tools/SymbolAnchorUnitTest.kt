package com.github.vcth4nh.idesense.tools

import junit.framework.TestCase
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Unit tests for [SymbolAnchor.parse] — the symbol-XOR-position input contract of
 * ide_explain_symbol (#41).
 */
class SymbolAnchorUnitTest : TestCase() {

    private fun args(vararg pairs: Pair<String, Any>): JsonObject = JsonObject(
        pairs.associate { (k, v) ->
            k to when (v) {
                is Int -> JsonPrimitive(v)
                else -> JsonPrimitive(v.toString())
            }
        }
    )

    fun testSymbolOnlyParsesBySymbol() {
        val anchor = SymbolAnchor.parse(args("symbol" to "demo.Circle"))
        assertEquals(SymbolAnchor.BySymbol("demo.Circle"), anchor)
    }

    fun testPositionOnlyParsesByPosition() {
        val anchor = SymbolAnchor.parse(args("file" to "src/A.java", "line" to 3, "column" to 14))
        assertEquals(SymbolAnchor.ByPosition("src/A.java", 3, 14), anchor)
    }

    fun testProjectPathAloneDoesNotCountAsPosition() {
        val anchor = SymbolAnchor.parse(args("symbol" to "Circle", "project_path" to "/p"))
        assertEquals(SymbolAnchor.BySymbol("Circle"), anchor)
    }

    fun testBothSymbolAndPositionInvalid() {
        val anchor = SymbolAnchor.parse(args("symbol" to "Circle", "file" to "src/A.java", "line" to 1, "column" to 1))
        assertTrue(anchor is SymbolAnchor.Invalid)
        val message = (anchor as SymbolAnchor.Invalid).message
        assertTrue("message should name both anchor forms: $message",
            message.contains("symbol") && message.contains("file"))
    }

    fun testNeitherAnchorInvalid() {
        val anchor = SymbolAnchor.parse(args())
        assertTrue(anchor is SymbolAnchor.Invalid)
        val message = (anchor as SymbolAnchor.Invalid).message
        assertTrue("message should name both anchor forms: $message",
            message.contains("symbol") && message.contains("file"))
    }

    fun testPartialPositionInvalid() {
        val anchor = SymbolAnchor.parse(args("file" to "src/A.java", "line" to 3))
        assertTrue(anchor is SymbolAnchor.Invalid)
        val message = (anchor as SymbolAnchor.Invalid).message
        assertTrue("message should name the missing param: $message", message.contains("column"))
    }

    fun testBlankSymbolInvalid() {
        val anchor = SymbolAnchor.parse(args("symbol" to "  "))
        assertTrue(anchor is SymbolAnchor.Invalid)
        assertTrue((anchor as SymbolAnchor.Invalid).message.contains("symbol"))
    }
}
