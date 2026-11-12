package com.github.vcth4nh.idesense.models

import com.github.vcth4nh.idesense.tools.models.FindUsagesResult
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
}
