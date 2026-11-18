package com.github.vcth4nh.idesense.tools.intelligence

import com.github.vcth4nh.idesense.constants.UsageMatch
import com.github.vcth4nh.idesense.tools.models.UsageLocation
import junit.framework.TestCase

// #132, #171: topUsages of ide_explain_symbol prefers sure code usages, then code usages with the
// match BASE, then code usages with the match OVERRIDE, then code usages with another match
// (DYNAMIC), then comment usages.
class ExplainSymbolTopUsagesUnitTest : TestCase() {

    private fun usage(line: Int, usageType: String, match: String? = null) =
        UsageLocation("a.go", line, 1, "preview", usageType, emptyList(), match)

    private fun select(vararg usages: UsageLocation, limit: Int = 5) =
        ExplainSymbolTool.preferSureUsages(usages.toList(), limit).map { "${it.line}:${it.usageType}" }

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

    fun testSureUsagesComeBeforeTheUsagesWithAMatch() {
        val selected = select(
            usage(1, "COMMENT"),
            usage(2, "METHOD_CALL", UsageMatch.DYNAMIC),
            usage(3, "METHOD_CALL", UsageMatch.BASE),
            usage(4, "METHOD_CALL"),
            usage(5, "REFERENCE"),
            limit = 3,
        )

        assertEquals(listOf("4:METHOD_CALL", "5:REFERENCE", "3:METHOD_CALL"), selected)
    }

    fun testBaseUsagesComeBeforeDynamicUsages() {
        val selected = select(
            usage(1, "METHOD_CALL", UsageMatch.DYNAMIC),
            usage(2, "METHOD_CALL", UsageMatch.DYNAMIC),
            usage(3, "METHOD_CALL", UsageMatch.BASE),
            usage(4, "METHOD_CALL"),
            usage(5, "COMMENT"),
        )

        assertEquals(listOf("4:METHOD_CALL", "3:METHOD_CALL", "1:METHOD_CALL", "2:METHOD_CALL", "5:COMMENT"), selected)
    }

    fun testOverrideUsagesComeAfterBaseUsagesAndBeforeDynamicUsages() {
        val selected = select(
            usage(1, "METHOD_CALL", UsageMatch.DYNAMIC),
            usage(2, "METHOD_CALL", UsageMatch.OVERRIDE),
            usage(3, "METHOD_CALL", UsageMatch.BASE),
            usage(4, "COMMENT"),
            usage(5, "METHOD_CALL"),
        )

        assertEquals(listOf("5:METHOD_CALL", "3:METHOD_CALL", "2:METHOD_CALL", "1:METHOD_CALL", "4:COMMENT"), selected)
    }

    fun testBaseUsagesKeepTheirSlotsWhenDynamicUsagesArriveFirst() {
        val selected = select(
            usage(1, "METHOD_CALL", UsageMatch.DYNAMIC),
            usage(2, "METHOD_CALL", UsageMatch.DYNAMIC),
            usage(3, "METHOD_CALL", UsageMatch.DYNAMIC),
            usage(4, "METHOD_CALL", UsageMatch.DYNAMIC),
            usage(5, "METHOD_CALL", UsageMatch.DYNAMIC),
            usage(6, "METHOD_CALL", UsageMatch.BASE),
            usage(7, "METHOD_CALL", UsageMatch.BASE),
            usage(8, "METHOD_CALL"),
        )

        assertEquals(listOf("8:METHOD_CALL", "6:METHOD_CALL", "7:METHOD_CALL", "1:METHOD_CALL", "2:METHOD_CALL"), selected)
    }
}
