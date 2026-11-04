package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.exceptions.IndexNotReadyException
import com.github.vcth4nh.idesense.tools.schema.Violation
import junit.framework.TestCase
import kotlinx.serialization.json.*

class McpErrorsUnitTest : TestCase() {

    fun testGenericShape() {
        val body = McpErrors.generic("tool_error", "boom")
        assertEquals("tool_error", body["error"]?.jsonPrimitive?.content)
        assertEquals("boom", body["message"]?.jsonPrimitive?.content)
    }

    fun testFromExceptionUsesErrorType() {
        val body = McpErrors.fromException(IndexNotReadyException("IDE is in dumb mode"))
        assertEquals("index_not_ready", body["error"]?.jsonPrimitive?.content)
        assertEquals("IDE is in dumb mode", body["message"]?.jsonPrimitive?.content)
    }

    fun testScopeMatchesNoFilesShape() {
        val body = McpErrors.scopeMatchesNoFiles("project_production_files", "the project has no production source roots")
        assertEquals("scope_matches_no_files", body["error"]?.jsonPrimitive?.content)
        assertEquals("project_production_files", body["provided"]?.jsonPrimitive?.content)
        val message = body["message"]!!.jsonPrimitive.content
        assertTrue(message.contains("project_production_files"))
        assertTrue(message.contains("no production source roots"))
    }

    fun testIndexMismatchDetectedDirectlyAndAsCause() {
        val platform = RuntimeException("PSI and index do not match.\nPlease report the problem to JetBrains with the files attached\n")
        assertTrue(McpErrors.isIndexMismatch(platform))
        assertTrue(McpErrors.isIndexMismatch(IllegalStateException("wrapper", platform)))
        // A wrapper that copies cause.toString() into its own message and drops the cause.
        assertTrue(McpErrors.isIndexMismatch(RuntimeException("com.intellij.openapi.diagnostic.RuntimeExceptionWithAttachments: PSI and index do not match.")))
        assertFalse(McpErrors.isIndexMismatch(RuntimeException("something else")))
        assertFalse(McpErrors.isIndexMismatch(RuntimeException()))
        assertEquals("index_out_of_sync", McpErrors.indexOutOfSync()["error"]?.jsonPrimitive?.content)
    }

    fun testInvalidScopeShape() {
        val body = McpErrors.invalidScope(
            "scope",
            "totally_invalid",
            listOf("project_files", "project_and_libraries", "project_production_files", "project_test_files")
        )
        assertEquals("invalid_scope", body["error"]?.jsonPrimitive?.content)
        assertEquals("scope", body["parameter"]?.jsonPrimitive?.content)
        assertEquals("totally_invalid", body["provided"]?.jsonPrimitive?.content)
        assertEquals(
            listOf("project_files", "project_and_libraries", "project_production_files", "project_test_files"),
            body["supportedValues"]!!.jsonArray.map { it.jsonPrimitive.content }
        )
        // Consistent with the McpErrors vocabulary: every body carries a human-readable message.
        assertNotNull("invalid_scope must carry a message", body["message"])
        assertTrue(
            "message should name the bad value",
            body["message"]!!.jsonPrimitive.content.contains("totally_invalid")
        )
    }

    fun testInvalidArgumentsAggregatesAllViolationKinds() {
        val body = McpErrors.invalidArguments("ide_find_class", listOf(
            Violation.MissingRequired("query"),
            Violation.UnknownParameter("maxResult", listOf("query", "scope")),
            Violation.InvalidType("line", "integer", "string"),
            Violation.InvalidEnum("scope", "foo", listOf("project_files"))
        ))
        assertEquals("invalid_arguments", body["error"]?.jsonPrimitive?.content)
        assertEquals("Invalid arguments for ide_find_class.", body["message"]?.jsonPrimitive?.content)

        val violations = body["violations"]!!.jsonArray
        assertEquals(4, violations.size)

        val missing = violations[0].jsonObject
        assertEquals("query", missing["parameter"]?.jsonPrimitive?.content)
        assertEquals("missing_required", missing["problem"]?.jsonPrimitive?.content)

        val unknown = violations[1].jsonObject
        assertEquals("unknown_parameter", unknown["problem"]?.jsonPrimitive?.content)
        assertEquals(listOf("query", "scope"),
            unknown["allowedParameters"]!!.jsonArray.map { it.jsonPrimitive.content })

        val type = violations[2].jsonObject
        assertEquals("invalid_type", type["problem"]?.jsonPrimitive?.content)
        assertEquals("integer", type["expected"]?.jsonPrimitive?.content)
        assertEquals("string", type["provided"]?.jsonPrimitive?.content)

        val enum = violations[3].jsonObject
        assertEquals("invalid_enum", enum["problem"]?.jsonPrimitive?.content)
        assertEquals("foo", enum["provided"]?.jsonPrimitive?.content)
        assertEquals(listOf("project_files"),
            enum["supportedValues"]!!.jsonArray.map { it.jsonPrimitive.content })
    }
}
