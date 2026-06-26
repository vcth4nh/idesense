package com.github.vcth4nh.idesense.tools.schema

import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.SchemaConstants
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScope
import junit.framework.TestCase
import kotlinx.serialization.json.*

class SchemaBuilderUnitTest : TestCase() {

    fun testBasicSchema() {
        val schema = SchemaBuilder.tool()
            .projectPath()
            .build()

        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)
        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)
        assertNotNull("Should have project_path", properties?.get(ParamNames.PROJECT_PATH))
    }

    fun testFileLineColumnSchema() {
        val schema = SchemaBuilder.tool()
            .projectPath()
            .file()
            .lineAndColumn()
            .build()

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject!!
        assertNotNull(properties[ParamNames.FILE])
        assertNotNull(properties[ParamNames.LINE])
        assertNotNull(properties[ParamNames.COLUMN])

        val required = schema[SchemaConstants.REQUIRED]?.jsonArray?.map { it.jsonPrimitive.content }!!
        assertTrue("file should be required", required.contains(ParamNames.FILE))
        assertTrue("line should be required", required.contains(ParamNames.LINE))
        assertTrue("column should be required", required.contains(ParamNames.COLUMN))
    }

    fun testCustomProperty() {
        val schema = SchemaBuilder.tool()
            .projectPath()
            .stringProperty("query", "Search query", required = true)
            .intProperty("limit", "Max results")
            .build()

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject!!
        assertNotNull(properties["query"])
        assertNotNull(properties["limit"])

        val required = schema[SchemaConstants.REQUIRED]?.jsonArray?.map { it.jsonPrimitive.content }!!
        assertTrue("query should be required", required.contains("query"))
        assertFalse("limit should not be required", required.contains("limit"))
    }

    fun testEnumProperty() {
        val schema = SchemaBuilder.tool()
            .projectPath()
            .enumProperty("mode", "Match mode", listOf("exact", "prefix", "substring"))
            .build()

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject!!
        val modeProp = properties["mode"]?.jsonObject!!
        val enumValues = modeProp["enum"]?.jsonArray?.map { it.jsonPrimitive.content }!!
        assertEquals(3, enumValues.size)
        assertTrue(enumValues.contains("exact"))
    }

    fun testScopeProperty() {
        val schema = SchemaBuilder.tool()
            .projectPath()
            .scopeProperty("Search scope. Default: project_files.")
            .build()

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject!!
        val scopeProp = properties[ParamNames.SCOPE]?.jsonObject!!
        assertEquals(SchemaConstants.TYPE_STRING, scopeProp[SchemaConstants.TYPE]?.jsonPrimitive?.content)
        assertEquals(
            BuiltInSearchScope.supportedWireValues(),
            scopeProp["enum"]?.jsonArray?.map { it.jsonPrimitive.content }
        )
        assertEquals(
            "Search scope. Default: project_files.",
            scopeProp[SchemaConstants.DESCRIPTION]?.jsonPrimitive?.content
        )
    }

    fun testBooleanProperty() {
        val schema = SchemaBuilder.tool()
            .projectPath()
            .booleanProperty("caseSensitive", "Case-sensitive search")
            .build()

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject!!
        val prop = properties["caseSensitive"]?.jsonObject!!
        assertEquals(SchemaConstants.TYPE_BOOLEAN, prop[SchemaConstants.TYPE]?.jsonPrimitive?.content)
    }

    fun testProjectPathNotRequired() {
        val schema = SchemaBuilder.tool()
            .projectPath()
            .file()
            .build()

        val required = schema[SchemaConstants.REQUIRED]?.jsonArray?.map { it.jsonPrimitive.content }!!
        assertFalse("project_path should NOT be required", required.contains(ParamNames.PROJECT_PATH))
    }

    fun testNoRequiredFieldsOmitsRequiredKey() {
        val schema = SchemaBuilder.tool()
            .projectPath()
            .intProperty("limit", "Max results")
            .build()

        assertNull("Schema with no required fields should not have 'required' key", schema[SchemaConstants.REQUIRED])
    }

    fun testRawProperty() {
        val customSchema = buildJsonObject {
            put(SchemaConstants.TYPE, SchemaConstants.TYPE_STRING)
            put(SchemaConstants.DESCRIPTION, "Custom property")
            put("default", "symbol")
        }
        val schema = SchemaBuilder.tool()
            .projectPath()
            .property("custom", customSchema, required = true)
            .build()

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject!!
        val prop = properties["custom"]?.jsonObject!!
        assertEquals("symbol", prop["default"]?.jsonPrimitive?.content)

        val required = schema[SchemaConstants.REQUIRED]?.jsonArray?.map { it.jsonPrimitive.content }!!
        assertTrue("custom should be required", required.contains("custom"))
    }

}
