package com.github.vcth4nh.idesense.tools.schema

import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.SchemaConstants
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScope
import kotlinx.serialization.json.*

class SchemaBuilder private constructor() {
    private val properties = linkedMapOf<String, JsonObject>()
    private val requiredFields = mutableListOf<String>()

    fun projectPath() = apply {
        properties[ParamNames.PROJECT_PATH] = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING)
            put(SchemaConstants.DESCRIPTION, SchemaConstants.DESC_PROJECT_PATH)
        }
    }

    fun file(required: Boolean = true, description: String = SchemaConstants.DESC_FILE) = apply {
        properties[ParamNames.FILE] = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING)
            put(SchemaConstants.DESCRIPTION, description)
        }
        if (required) requiredFields.add(ParamNames.FILE)
    }

    fun lineAndColumn(required: Boolean = true) = apply {
        properties[ParamNames.LINE] = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_INTEGER)
            put(SchemaConstants.DESCRIPTION, SchemaConstants.DESC_LINE)
        }
        properties[ParamNames.COLUMN] = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_INTEGER)
            put(SchemaConstants.DESCRIPTION, SchemaConstants.DESC_COLUMN)
        }
        if (required) {
            requiredFields.add(ParamNames.LINE)
            requiredFields.add(ParamNames.COLUMN)
        }
    }

    fun stringProperty(name: String, description: String, required: Boolean = false) = apply {
        properties[name] = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING)
            put(SchemaConstants.DESCRIPTION, description)
        }
        if (required) requiredFields.add(name)
    }

    fun intProperty(name: String, description: String, required: Boolean = false) = apply {
        properties[name] = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_INTEGER)
            put(SchemaConstants.DESCRIPTION, description)
        }
        if (required) requiredFields.add(name)
    }

    fun booleanProperty(name: String, description: String, required: Boolean = false) = apply {
        properties[name] = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_BOOLEAN)
            put(SchemaConstants.DESCRIPTION, description)
        }
        if (required) requiredFields.add(name)
    }

    fun enumProperty(name: String, description: String, values: List<String>, required: Boolean = false) = apply {
        properties[name] = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING)
            put(SchemaConstants.DESCRIPTION, description)
            putJsonArray("enum") { values.forEach { add(JsonPrimitive(it)) } }
        }
        if (required) requiredFields.add(name)
    }

    fun scopeProperty(description: String, required: Boolean = false) = apply {
        enumProperty(
            name = ParamNames.SCOPE,
            description = description,
            values = BuiltInSearchScope.supportedWireValues(),
            required = required
        )
    }

    fun hierarchyScopeProperty(description: String, values: List<String>, required: Boolean = false) = apply {
        enumProperty(
            name = ParamNames.SCOPE,
            description = description,
            values = values,
            required = required
        )
    }

    fun property(name: String, schema: JsonObject, required: Boolean = false) = apply {
        properties[name] = schema
        if (required) requiredFields.add(name)
    }

    fun stringArrayProperty(name: String, description: String, required: Boolean = false) = apply {
        properties[name] = buildJsonObject {
            put(SchemaConstants.TYPE, "array")
            putJsonObject("items") { put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING) }
            put(SchemaConstants.DESCRIPTION, description)
        }
        if (required) requiredFields.add(name)
    }

    fun build(): JsonObject = buildJsonObject {
        put(SchemaConstants.TYPE, SchemaConstants.TYPE_OBJECT)
        putJsonObject(SchemaConstants.PROPERTIES) {
            for ((name, schema) in properties) {
                put(name, schema)
            }
        }
        if (requiredFields.isNotEmpty()) {
            putJsonArray(SchemaConstants.REQUIRED) {
                for (field in requiredFields) {
                    add(JsonPrimitive(field))
                }
            }
        }
    }

    companion object {
        fun tool() = SchemaBuilder()
    }
}
