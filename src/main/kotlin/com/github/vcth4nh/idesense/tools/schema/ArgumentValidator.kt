package com.github.vcth4nh.idesense.tools.schema

import com.github.vcth4nh.idesense.constants.SchemaConstants
import kotlinx.serialization.json.*

/** One argument-validation failure. Sealed so each kind carries exactly its context fields. */
sealed class Violation(val parameter: String) {
    class MissingRequired(parameter: String) : Violation(parameter)
    class UnknownParameter(parameter: String, val allowedParameters: List<String>) : Violation(parameter)
    class InvalidType(parameter: String, val expected: String, val provided: String) : Violation(parameter)
    class InvalidEnum(parameter: String, val provided: String, val supportedValues: List<String>) : Violation(parameter)
}

/**
 * Validates a tool-call `arguments` object against a tool's `inputSchema` (the JSON produced by
 * [SchemaBuilder]). Pure logic — no platform, no settings; the enforcement counterpart to [SchemaBuilder].
 *
 * Strict: unknown keys are rejected (the central fix for #12's silently-ignored typos). Type checking
 * mirrors the runtime accessors (`jsonPrimitive.int`/`.boolean`/`.content`) — it rejects only the kinds
 * those accessors would throw on, staying lenient on numeric-string coercion (`line:"123"` passes,
 * `line:"abc"` does not). Only required + primitive-type + enum + unknown-key are checked (no nested/min/
 * max/pattern). Collects ALL violations so one retry fixes everything.
 */
object ArgumentValidator {

    /** Undocumented pagination aliases accepted by the tools but declared in no schema. */
    private val ALWAYS_ALLOWED = setOf("limit", "maxResults")

    fun validate(arguments: JsonObject, schema: JsonObject): List<Violation> {
        val properties = schema[SchemaConstants.PROPERTIES] as? JsonObject
            ?: return emptyList() // absent/malformed schema → enforce nothing
        val required = (schema[SchemaConstants.REQUIRED] as? JsonArray)
            ?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }?.toSet()
            ?: emptySet()
        val allowed = properties.keys.toList()

        val violations = mutableListOf<Violation>()

        for (name in required) {
            if (name !in arguments) violations.add(Violation.MissingRequired(name))
        }

        for ((key, value) in arguments) {
            if (key in ALWAYS_ALLOWED) continue
            val propSchema = properties[key] as? JsonObject
            if (propSchema == null) {
                violations.add(Violation.UnknownParameter(key, allowed))
                continue
            }
            if (value is JsonNull) continue // nothing to type/enum-check

            val declaredType = (propSchema[SchemaConstants.TYPE] as? JsonPrimitive)?.contentOrNull
            if (declaredType != null && !isCompatible(declaredType, value)) {
                violations.add(Violation.InvalidType(key, declaredType, kindOf(value)))
                continue
            }

            val enumValues = (propSchema[SchemaConstants.ENUM] as? JsonArray)
                ?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
            if (enumValues != null && value is JsonPrimitive && value.content !in enumValues) {
                violations.add(Violation.InvalidEnum(key, value.content, enumValues))
            }
        }
        return violations
    }

    /** Accept exactly what the runtime accessors tolerate; reject only kinds that would throw. */
    private fun isCompatible(expected: String, value: JsonElement): Boolean = when (expected) {
        SchemaConstants.TYPE_STRING  -> value is JsonPrimitive                          // `.content` coerces any primitive
        SchemaConstants.TYPE_INTEGER -> value is JsonPrimitive && value.longOrNull != null // 5, "5" ok; "abc", 1.5, true no
        SchemaConstants.TYPE_BOOLEAN -> value is JsonPrimitive && value.booleanOrNull != null
        SchemaConstants.TYPE_ARRAY   -> value is JsonArray
        SchemaConstants.TYPE_OBJECT  -> value is JsonObject
        else -> true // unknown declared type → don't enforce
    }

    /** Surface JSON kind of the provided value, for the `provided` field of an invalid_type violation. */
    private fun kindOf(value: JsonElement): String = when (value) {
        is JsonArray -> "array"
        is JsonObject -> "object"
        is JsonNull -> "null"
        is JsonPrimitive -> when {
            value.isString -> "string"
            value.booleanOrNull != null -> "boolean" // before integer: a numeric primitive's booleanOrNull is null, so order is safe
            value.longOrNull != null -> "integer"
            value.doubleOrNull != null -> "number"
            else -> "string"
        }
    }
}
