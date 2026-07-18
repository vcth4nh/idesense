package com.github.vcth4nh.idesense.tools.intelligence

import junit.framework.TestCase
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Unit tests for [ExplainAnchor.parse] — the symbol-XOR-position input contract of
 * ide_explain_symbol (#41).
 */
class ExplainAnchorUnitTest : TestCase() {

    private fun args(vararg pairs: Pair<String, Any>): JsonObject = JsonObject(
        pairs.associate { (k, v) ->
            k to when (v) {
                is Int -> JsonPrimitive(v)
                else -> JsonPrimitive(v.toString())
            }
        }
    )

    fun testSymbolOnlyParsesBySymbol() {
        val anchor = ExplainAnchor.parse(args("symbol" to "demo.Circle"))
        assertEquals(ExplainAnchor.BySymbol("demo.Circle"), anchor)
    }

    fun testPositionOnlyParsesByPosition() {
        val anchor = ExplainAnchor.parse(args("file" to "src/A.java", "line" to 3, "column" to 14))
        assertEquals(ExplainAnchor.ByPosition("src/A.java", 3, 14), anchor)
    }

    fun testProjectPathAloneDoesNotCountAsPosition() {
        val anchor = ExplainAnchor.parse(args("symbol" to "Circle", "project_path" to "/p"))
        assertEquals(ExplainAnchor.BySymbol("Circle"), anchor)
    }

    fun testBothSymbolAndPositionInvalid() {
        val anchor = ExplainAnchor.parse(args("symbol" to "Circle", "file" to "src/A.java", "line" to 1, "column" to 1))
        assertTrue(anchor is ExplainAnchor.Invalid)
        val message = (anchor as ExplainAnchor.Invalid).message
        assertTrue("message should name both anchor forms: $message",
            message.contains("symbol") && message.contains("file"))
    }

    fun testNeitherAnchorInvalid() {
        val anchor = ExplainAnchor.parse(args())
        assertTrue(anchor is ExplainAnchor.Invalid)
        val message = (anchor as ExplainAnchor.Invalid).message
        assertTrue("message should name both anchor forms: $message",
            message.contains("symbol") && message.contains("file"))
    }

    fun testPartialPositionInvalid() {
        val anchor = ExplainAnchor.parse(args("file" to "src/A.java", "line" to 3))
        assertTrue(anchor is ExplainAnchor.Invalid)
        val message = (anchor as ExplainAnchor.Invalid).message
        assertTrue("message should name the missing param: $message", message.contains("column"))
    }

    fun testBlankSymbolInvalid() {
        val anchor = ExplainAnchor.parse(args("symbol" to "  "))
        assertTrue(anchor is ExplainAnchor.Invalid)
        assertTrue((anchor as ExplainAnchor.Invalid).message.contains("symbol"))
    }
}
