package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.constants.ErrorMessages
import com.github.vcth4nh.idesense.exceptions.McpException
import com.github.vcth4nh.idesense.tools.schema.Violation
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray

/**
 * Builds canonical MCP error bodies as [JsonObject]s. Pure — callers render them to a
 * [ToolCallResult] via [StructuredToolResult.fromElement]. Canonical shape:
 * `{ "error": "<snake_case_code>", "message": "<human-readable>", ...context }`.
 */
object McpErrors {

    /** Flat `{error, message}` body — the base shape for non-validation errors. */
    fun generic(code: String, message: String): JsonObject = buildJsonObject {
        put("error", code)
        put("message", message)
    }

    /** Maps a thrown [McpException] to its stable snake_case code + message. */
    fun fromException(e: McpException): JsonObject =
        generic(e.errorType, e.message ?: ErrorMessages.UNKNOWN_ERROR)

    /**
     * Structured body for an unsupported `scope` (or other enum-like) argument. A first-class
     * McpErrors code so the five search + two hierarchy tools stop hand-building their own shape.
     */
    fun invalidScope(parameter: String, provided: String, supportedValues: List<String>): JsonObject = buildJsonObject {
        put("error", "invalid_scope")
        put("message", "Unsupported $parameter '$provided'. Supported values: ${supportedValues.joinToString(", ")}.")
        put("parameter", parameter)
        put("provided", provided)
        putJsonArray("supportedValues") { supportedValues.forEach { add(it) } }
    }

    /** Aggregate body for argument-validation failures; the agent fixes everything in one retry. */
    fun invalidArguments(toolName: String, violations: List<Violation>): JsonObject = buildJsonObject {
        put("error", "invalid_arguments")
        put("message", "Invalid arguments for $toolName.")
        putJsonArray("violations") { violations.forEach { add(renderViolation(it)) } }
    }

    private fun renderViolation(v: Violation): JsonObject = buildJsonObject {
        put("parameter", v.parameter)
        when (v) {
            is Violation.MissingRequired -> put("problem", "missing_required")
            is Violation.UnknownParameter -> {
                put("problem", "unknown_parameter")
                putJsonArray("allowedParameters") { v.allowedParameters.forEach { add(it) } }
            }
            is Violation.InvalidType -> {
                put("problem", "invalid_type")
                put("expected", v.expected)
                put("provided", v.provided)
            }
            is Violation.InvalidEnum -> {
                put("problem", "invalid_enum")
                put("provided", v.provided)
                putJsonArray("supportedValues") { v.supportedValues.forEach { add(it) } }
            }
        }
    }
}
