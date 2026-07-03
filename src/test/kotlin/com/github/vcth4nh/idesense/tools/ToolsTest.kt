package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.tools.intelligence.GetDiagnosticsTool
import com.github.vcth4nh.idesense.tools.navigation.CallHierarchyTool
import com.github.vcth4nh.idesense.tools.navigation.FileStructureTool
import com.github.vcth4nh.idesense.tools.navigation.FindClassTool
import com.github.vcth4nh.idesense.tools.navigation.FindImplementationsTool
import com.github.vcth4nh.idesense.tools.navigation.FindSuperMethodsTool
import com.github.vcth4nh.idesense.tools.navigation.FindUsagesTool
import com.github.vcth4nh.idesense.tools.navigation.FindDefinitionTool
import com.github.vcth4nh.idesense.tools.navigation.TypeHierarchyTool
import com.github.vcth4nh.idesense.tools.project.GetIndexStatusTool
import com.github.vcth4nh.idesense.tools.refactoring.RenameSymbolTool
import com.github.vcth4nh.idesense.constants.SchemaConstants
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScope
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScopeResolver
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Platform-dependent tests that require IntelliJ Platform indexing.
 * For schema and registration tests that don't need the platform, see ToolsUnitTest.
 */
class ToolsTest : BasePlatformTestCase() {

    private fun errorText(result: com.github.vcth4nh.idesense.server.models.ToolCallResult): String =
        (result.content.first() as ContentBlock.Text).text

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    fun testGetIndexStatusTool() = runBlocking {
        val tool = GetIndexStatusTool()

        val result = tool.execute(project, buildJsonObject { })

        assertFalse("get_index_status should succeed", result.isError)
        assertTrue("Should have content", result.content.isNotEmpty())

        val content = result.content.first()
        assertTrue("Content should be text", content is ContentBlock.Text)

        val textContent = (content as ContentBlock.Text).text
        val resultJson = json.parseToJsonElement(textContent).jsonObject

        assertNotNull("Result should have isDumbMode", resultJson["isDumbMode"])
        assertNotNull("Result should have isIndexing", resultJson["isIndexing"])
    }

    fun testFindUsagesToolMissingParams() = runBlocking {
        val tool = FindUsagesTool()

        val result = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing params", result.isError)
    }

    fun testFindUsagesToolInvalidFile() = runBlocking {
        val tool = FindUsagesTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "nonexistent/file.kt")
            put("line", 1)
            put("column", 1)
        })

        assertTrue("Should error with invalid file", result.isError)
    }

    fun testFindUsagesToolPartialPosition() = runBlocking {
        val tool = FindUsagesTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "test.kt")
            put("line", 1)
        })

        assertTrue("Should error with partial position params", result.isError)
        assertTrue("Should mention missing column", errorText(result).contains("column"))
    }

    fun testFindDefinitionToolMissingParams() = runBlocking {
        val tool = FindDefinitionTool()

        val result = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing params", result.isError)
    }

    fun testFindDefinitionToolPartialPosition() = runBlocking {
        val tool = FindDefinitionTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "test.kt")
        })

        assertTrue("Should error with partial position params", result.isError)
        assertTrue("Should mention missing line", errorText(result).contains("line"))
    }

    // Navigation Tools Tests

    fun testTypeHierarchyToolMissingParams() = runBlocking {
        val tool = TypeHierarchyTool()

        val result = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing className", result.isError)
    }

    fun testTypeHierarchyToolInvalidClass() = runBlocking {
        val tool = TypeHierarchyTool()

        val result = tool.execute(project, buildJsonObject {
            put("className", "com.nonexistent.Class")
        })

        assertTrue("Should error with invalid class", result.isError)
    }

    fun testCallHierarchyToolMissingParams() = runBlocking {
        val tool = CallHierarchyTool()

        val result = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing params", result.isError)
    }

    fun testCallHierarchyToolInvalidFile() = runBlocking {
        val tool = CallHierarchyTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "nonexistent/file.kt")
            put("line", 1)
            put("column", 1)
        })

        assertTrue("Should error with invalid file", result.isError)
    }

    fun testFindImplementationsToolMissingParams() = runBlocking {
        val tool = FindImplementationsTool()

        val result = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing params", result.isError)
    }

    fun testFindImplementationsToolInvalidFile() = runBlocking {
        val tool = FindImplementationsTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "nonexistent/file.kt")
            put("line", 1)
            put("column", 1)
        })

        assertTrue("Should error with invalid file", result.isError)
    }

    fun testFindClassToolInvalidScopeReturnsStructuredError() = runBlocking {
        val tool = FindClassTool()

        val result = tool.execute(project, buildJsonObject {
            put("query", "UserService")
            put("scope", "totally_invalid")
        })

        assertTrue("Should error with invalid scope", result.isError)

        val errorJson = json.parseToJsonElement(errorText(result)).jsonObject
        assertEquals("invalid_scope", errorJson["error"]?.jsonPrimitive?.content)
        assertEquals("scope", errorJson["parameter"]?.jsonPrimitive?.content)
        assertEquals("totally_invalid", errorJson["provided"]?.jsonPrimitive?.content)
        assertEquals(
            listOf("project_files", "project_and_libraries", "project_production_files", "project_test_files"),
            errorJson["supportedValues"]?.jsonArray?.map { it.jsonPrimitive.content }
        )
    }

    fun testFindClassToolMalformedScopeTypeReturnsStructuredError() = runBlocking {
        val tool = FindClassTool()

        val result = tool.execute(project, buildJsonObject {
            put("query", "UserService")
            put("scope", buildJsonArray {
                add(JsonPrimitive("project_files"))
            })
        })

        assertTrue("Should error with malformed scope type", result.isError)

        val errorJson = json.parseToJsonElement(errorText(result)).jsonObject
        assertEquals("invalid_scope", errorJson["error"]?.jsonPrimitive?.content)
        assertEquals("scope", errorJson["parameter"]?.jsonPrimitive?.content)
        assertEquals("[\"project_files\"]", errorJson["provided"]?.jsonPrimitive?.content)
        assertEquals(
            listOf("project_files", "project_and_libraries", "project_production_files", "project_test_files"),
            errorJson["supportedValues"]?.jsonArray?.map { it.jsonPrimitive.content }
        )
    }

    // Intelligence Tools Tests

    fun testGetDiagnosticsToolMissingParams() = runBlocking {
        val tool = GetDiagnosticsTool()

        val result = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing file", result.isError)
    }

    fun testGetDiagnosticsToolInvalidFile() = runBlocking {
        val tool = GetDiagnosticsTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "nonexistent/file.kt")
        })

        assertTrue("Should error with invalid file", result.isError)
    }

    // Refactoring Tools Tests

    fun testRenameSymbolToolMissingParams() = runBlocking {
        val tool = RenameSymbolTool()

        val result = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing params", result.isError)
    }

    fun testRenameSymbolToolInvalidFile() = runBlocking {
        val tool = RenameSymbolTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "nonexistent/file.kt")
            put("line", 1)
            put("column", 1)
            put("newName", "newSymbol")
        })

        assertTrue("Should error with invalid file", result.isError)
    }

    fun testRenameSymbolToolBlankName() = runBlocking {
        val tool = RenameSymbolTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "test.kt")
            put("line", 1)
            put("column", 1)
            put("newName", "   ")
        })

        assertTrue("Should error with blank name", result.isError)
    }

    // File Structure Tool Tests

    fun testFileStructureToolMissingParams() = runBlocking {
        val tool = FileStructureTool()

        val result = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing params", result.isError)
    }

    fun testFileStructureToolInvalidFile() = runBlocking {
        val tool = FileStructureTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "nonexistent/file.java")
        })

        assertTrue("Should error with invalid file", result.isError)
    }

    // FindSuperMethods Tool Tests

    fun testFindSuperMethodsToolMissingParams() = runBlocking {
        val tool = FindSuperMethodsTool()

        val result = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing params", result.isError)
    }

    fun testFindSuperMethodsToolInvalidFile() = runBlocking {
        val tool = FindSuperMethodsTool()

        val result = tool.execute(project, buildJsonObject {
            put("file", "nonexistent/file.kt")
            put("line", 1)
            put("column", 1)
        })

        assertTrue("Should error with invalid file", result.isError)
    }

    fun testFindSuperMethodsToolPartialPosition() = runBlocking {
        val tool = FindSuperMethodsTool()

        val result = tool.execute(project, buildJsonObject {
            put("line", 1)
            put("column", 1)
        })

        assertTrue("Should error with partial position params", result.isError)
        assertTrue("Should mention missing file", errorText(result).contains("file"))
    }

    // Registry tests that require platform services (McpSettings)

    fun testToolDefinitionsHaveRequiredFields() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val definitions = registry.getToolDefinitions()

        for (definition in definitions) {
            assertNotNull("Definition should have name", definition.name)
            assertTrue("Name should not be empty", definition.name.isNotEmpty())

            assertNotNull("Definition should have description", definition.description)
            assertTrue("Description should not be empty", definition.description.isNotEmpty())

            assertNotNull("Definition should have inputSchema", definition.inputSchema)
            assertEquals(SchemaConstants.TYPE_OBJECT, definition.inputSchema[SchemaConstants.TYPE]?.jsonPrimitive?.content)
        }
    }

}
