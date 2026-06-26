package com.github.vcth4nh.idesense.tools.schema

import com.github.vcth4nh.idesense.constants.SchemaConstants
import junit.framework.TestCase
import kotlinx.serialization.json.*

class ArgumentValidatorUnitTest : TestCase() {

    // Representative schema: required `query` (string); `scope` enum; `line`/`pageSize` integer; `project_path` string.
    private val schema = buildJsonObject {
        put(SchemaConstants.TYPE, SchemaConstants.TYPE_OBJECT)
        putJsonObject(SchemaConstants.PROPERTIES) {
            putJsonObject("query") { put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING) }
            putJsonObject("scope") {
                put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING)
                putJsonArray(SchemaConstants.ENUM) { add("project_files"); add("project_test_files") }
            }
            putJsonObject("line") { put(SchemaConstants.TYPE, SchemaConstants.TYPE_INTEGER) }
            putJsonObject("pageSize") { put(SchemaConstants.TYPE, SchemaConstants.TYPE_INTEGER) }
            putJsonObject("project_path") { put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING) }
            putJsonObject("verbose") { put(SchemaConstants.TYPE, SchemaConstants.TYPE_BOOLEAN) }
        }
        putJsonArray(SchemaConstants.REQUIRED) { add("query") }
    }

    private fun args(vararg pairs: Pair<String, JsonElement>) = JsonObject(mapOf(*pairs))

    fun testValidArgumentsProduceNoViolations() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "scope" to JsonPrimitive("project_files")), schema)
        assertTrue(v.isEmpty())
    }

    fun testMissingRequired() {
        val v = ArgumentValidator.validate(args("scope" to JsonPrimitive("project_files")), schema)
        val mr = v.single() as Violation.MissingRequired
        assertEquals("query", mr.parameter)
    }

    fun testUnknownParameterCarriesAllowedList() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "maxResult" to JsonPrimitive(5)), schema)
        val up = v.single() as Violation.UnknownParameter
        assertEquals("maxResult", up.parameter)
        assertTrue(up.allowedParameters.contains("query"))
        assertTrue(up.allowedParameters.contains("scope"))
    }

    fun testInvalidTypeRejectsNonNumericStringForInteger() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "line" to JsonPrimitive("abc")), schema)
        val it0 = v.single() as Violation.InvalidType
        assertEquals("line", it0.parameter)
        assertEquals("integer", it0.expected)
        assertEquals("string", it0.provided)
    }

    fun testNumericStringAcceptedForInteger() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "line" to JsonPrimitive("123")), schema)
        assertTrue(v.isEmpty())
    }

    fun testInvalidTypeRejectsArrayForInteger() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "line" to JsonArray(listOf(JsonPrimitive(1)))), schema)
        assertEquals("array", (v.single() as Violation.InvalidType).provided)
    }

    fun testInvalidEnum() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "scope" to JsonPrimitive("bogus")), schema)
        val ie = v.single() as Violation.InvalidEnum
        assertEquals("scope", ie.parameter)
        assertEquals("bogus", ie.provided)
        assertTrue(ie.supportedValues.contains("project_files"))
    }

    fun testMultipleViolationsAggregated() {
        // missing query + unknown maxResult + invalid line type + invalid scope enum = 4
        val v = ArgumentValidator.validate(
            args("maxResult" to JsonPrimitive(5), "line" to JsonPrimitive("abc"), "scope" to JsonPrimitive("bogus")),
            schema)
        assertEquals(4, v.size)
    }

    fun testPaginationAliasesAccepted() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "limit" to JsonPrimitive(10), "maxResults" to JsonPrimitive(20)),
            schema)
        assertTrue(v.isEmpty())
    }

    fun testProjectPathAcceptedWhenInSchema() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "project_path" to JsonPrimitive("/repo")), schema)
        assertTrue(v.isEmpty())
    }

    fun testBooleanTypeAcceptsBooleanAndBooleanString() {
        // `verbose` is declared boolean; `true` and the string "true" both satisfy the runtime accessor.
        assertTrue(ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "verbose" to JsonPrimitive(true)), schema).isEmpty())
        assertTrue(ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "verbose" to JsonPrimitive("true")), schema).isEmpty())
    }

    fun testBooleanTypeRejectsNonBoolean() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "verbose" to JsonPrimitive("yes")), schema)
        val it0 = v.single() as Violation.InvalidType
        assertEquals("verbose", it0.parameter)
        assertEquals("boolean", it0.expected)
        assertEquals("string", it0.provided)
    }

    fun testFloatJsonNumberRejectedForInteger() {
        // 1.5 is a JSON number but not an integer; longOrNull is null, so it must reject as invalid_type.
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "line" to JsonPrimitive(1.5)), schema)
        val it0 = v.single() as Violation.InvalidType
        assertEquals("line", it0.parameter)
        assertEquals("integer", it0.expected)
        assertEquals("number", it0.provided)
    }

    fun testFloatStringRejectedForInteger() {
        val v = ArgumentValidator.validate(
            args("query" to JsonPrimitive("Foo"), "line" to JsonPrimitive("1.5")), schema)
        val it0 = v.single() as Violation.InvalidType
        assertEquals("string", it0.provided)
    }

    fun testCursorOnlyCallPassesWhenNoRequiredArray() {
        val paginated = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_OBJECT)
            putJsonObject(SchemaConstants.PROPERTIES) {
                putJsonObject("cursor") { put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING) }
                putJsonObject("query") { put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING) }
            }
        }
        val v = ArgumentValidator.validate(args("cursor" to JsonPrimitive("abc")), paginated)
        assertTrue(v.isEmpty())
    }
}
