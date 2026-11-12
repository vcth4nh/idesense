package com.github.vcth4nh.idesense.tools.intelligence

import com.github.vcth4nh.idesense.tools.models.UsageLocation
import junit.framework.TestCase

// #132: topUsages of ide_explain_symbol prefers code usages; a comment usage fills only a free slot.
class ExplainSymbolTopUsagesUnitTest : TestCase() {

    private fun usage(line: Int, usageType: String) =
        UsageLocation("a.go", line, 1, "preview", usageType, emptyList())

    private fun select(vararg usages: UsageLocation) =
        ExplainSymbolTool.preferCodeUsages(usages.toList(), 5).map { "${it.line}:${it.usageType}" }

    fun testCommentsFillTheSlotsThatFewCodeUsagesLeaveFree() {
        val selected = select(
            usage(1, "COMMENT"), usage(2, "COMMENT"), usage(3, "METHOD_CALL"),
            usage(4, "COMMENT"), usage(5, "REFERENCE"), usage(6, "COMMENT"),
        )

        assertEquals(listOf("3:METHOD_CALL", "5:REFERENCE", "1:COMMENT", "2:COMMENT", "4:COMMENT"), selected)
    }

    fun testFiveCodeUsagesLeaveNoSlotForAComment() {
        val selected = select(
            usage(1, "COMMENT"), usage(2, "METHOD_CALL"), usage(3, "REFERENCE"), usage(4, "METHOD_CALL"),
            usage(5, "COMMENT"), usage(6, "IMPORT"), usage(7, "METHOD_CALL"), usage(8, "REFERENCE"),
        )

        assertEquals(listOf("2:METHOD_CALL", "3:REFERENCE", "4:METHOD_CALL", "6:IMPORT", "7:METHOD_CALL"), selected)
    }

    fun testCommentsOnlyKeepTheirArrivalOrder() {
        val selected = select(
            usage(1, "COMMENT"), usage(2, "COMMENT"), usage(3, "COMMENT"),
            usage(4, "COMMENT"), usage(5, "COMMENT"), usage(6, "COMMENT"),
        )

        assertEquals(listOf("1:COMMENT", "2:COMMENT", "3:COMMENT", "4:COMMENT", "5:COMMENT"), selected)
    }
}
