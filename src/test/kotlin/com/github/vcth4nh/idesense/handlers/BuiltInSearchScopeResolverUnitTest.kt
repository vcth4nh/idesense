package com.github.vcth4nh.idesense.handlers

import junit.framework.TestCase
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class BuiltInSearchScopeResolverUnitTest : TestCase() {

    fun testWireValuesAreStable() {
        assertEquals(
            listOf(
                "project_files",
                "project_and_libraries",
                "project_production_files",
                "project_test_files"
            ),
            BuiltInSearchScope.values().map { it.wireValue }
        )
    }

    fun testParseUsesDefaultWhenScopeIsMissing() {
        val arguments = buildJsonObject { }

        val resolved = BuiltInSearchScopeResolver.parse(arguments, BuiltInSearchScope.PROJECT_AND_LIBRARIES)

        assertEquals(BuiltInSearchScope.PROJECT_AND_LIBRARIES, resolved)
    }

    fun testParseRejectsInvalidScopeWithSupportedValues() {
        val arguments = buildJsonObject {
            put("scope", "totally_invalid")
        }

        val error = try {
            BuiltInSearchScopeResolver.parse(arguments, BuiltInSearchScope.PROJECT_FILES)
            null
        } catch (e: IllegalArgumentException) {
            e
        }

        assertNotNull("Expected invalid scope to be rejected", error)
        val message = error!!.message ?: ""
        assertTrue(message.contains("totally_invalid"))
        assertTrue(message.contains("project_files"))
        assertTrue(message.contains("project_and_libraries"))
        assertTrue(message.contains("project_production_files"))
        assertTrue(message.contains("project_test_files"))
    }
}
