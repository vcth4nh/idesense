package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.settings.McpSettings
import com.github.vcth4nh.idesense.util.ResponseFormatter
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/**
 * Builds a [ToolCallResult] from a structured [JsonElement]: the element is rendered into the
 * text content block (via [ResponseFormatter], honoring the user's response-format setting) and,
 * when it is a JSON object, also attached as native [ToolCallResult.structuredContent]
 * (MCP 2025-11-25). The serialized-JSON text mirror is always present per the spec's
 * backwards-compatibility rule. Pure logic — [format] is passed in so this is unit-testable.
 *
 * Callers own formatting-failure fallback: this builder does not catch exceptions. The
 * AbstractMcpTool producers that wrap it fall back to a plain-text error on failure.
 */
object StructuredToolResult {
    private val json = Json { encodeDefaults = true; prettyPrint = false }

    fun fromElement(
        element: JsonElement,
        isError: Boolean,
        format: McpSettings.ResponseFormat,
    ): ToolCallResult {
        val serialized = json.encodeToString(JsonElement.serializer(), element)
        val text = ResponseFormatter.formatStructuredPayload(serialized, format)
        return ToolCallResult(
            content = listOf(ContentBlock.Text(text = text)),
            structuredContent = element as? JsonObject,
            isError = isError,
        )
    }
}
