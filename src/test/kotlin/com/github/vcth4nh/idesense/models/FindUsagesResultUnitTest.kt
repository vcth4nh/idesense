package com.github.vcth4nh.idesense.models

import com.github.vcth4nh.idesense.constants.UsageMatch
import com.github.vcth4nh.idesense.tools.models.FindUsagesResult
import com.github.vcth4nh.idesense.tools.models.UsageLocation
import junit.framework.TestCase
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class FindUsagesResultUnitTest : TestCase() {

    private val json = Json {
        encodeDefaults = true
    }

    // notes (#130): omitted from the JSON when null, unlike warnings, which keep "warnings":null.
    fun testNotesAreOmittedWhenNullAndSerializedWhenSet() {
        val plain = json.encodeToString(FindUsagesResult(usages = emptyList()))
        assertFalse(plain.contains("\"notes\""))
        assertTrue(plain.contains("\"warnings\":null"))

        val noted = json.encodeToString(FindUsagesResult(usages = emptyList(), notes = listOf("n")))
        assertTrue(noted.contains("\"notes\":[\"n\"]"))
    }

    // match (#171): a sure usage has no match key; a usage that is not sure has its mark.
    fun testMatchIsOmittedWhenNullAndSerializedWhenSet() {
        val sure = json.encodeToString(UsageLocation("a.go", 1, 1, "preview", "METHOD_CALL", emptyList()))
        assertFalse(sure.contains("\"match\""))

        val marked = json.encodeToString(
            UsageLocation("a.go", 1, 1, "preview", "METHOD_CALL", emptyList(), match = UsageMatch.BASE)
        )
        assertTrue(marked.contains("\"match\":\"BASE\""))
    }
}
