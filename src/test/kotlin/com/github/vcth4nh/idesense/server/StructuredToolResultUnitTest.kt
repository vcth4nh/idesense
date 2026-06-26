package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.settings.McpSettings
import junit.framework.TestCase
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

class StructuredToolResultUnitTest : TestCase() {

    fun testObjectPayloadSetsStructuredContentAndTextMirror() {
        val body = buildJsonObject { put("error", "tool_error"); put("message", "boom") }
        val result = StructuredToolResult.fromElement(body, isError = true, format = McpSettings.ResponseFormat.JSON)

        assertTrue(result.isError)
        assertNotNull(result.structuredContent)
        assertEquals("tool_error", result.structuredContent!!["error"]!!.jsonPrimitive.content)
        val text = (result.content.first() as ContentBlock.Text).text
        assertTrue("text mirror is the serialized JSON", text.contains("\"error\":\"tool_error\""))
    }

    fun testNonObjectPayloadOmitsStructuredContentButKeepsText() {
        val arr = JsonArray(listOf(JsonPrimitive(1), JsonPrimitive(2)))
        val result = StructuredToolResult.fromElement(arr, isError = false, format = McpSettings.ResponseFormat.JSON)

        assertNull("array payload cannot be structuredContent (object-typed field)", result.structuredContent)
        val text = (result.content.first() as ContentBlock.Text).text
        assertEquals("[1,2]", text)
    }
}
