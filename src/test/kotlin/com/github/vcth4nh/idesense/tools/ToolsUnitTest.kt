package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.SchemaConstants
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.handlers.BuiltInSearchScope
import com.github.vcth4nh.idesense.tools.intelligence.GetDiagnosticsTool
import com.github.vcth4nh.idesense.tools.navigation.CallHierarchyTool
import com.github.vcth4nh.idesense.tools.navigation.FileStructureTool
import com.github.vcth4nh.idesense.tools.navigation.FindClassTool
import com.github.vcth4nh.idesense.tools.navigation.FindDefinitionTool
import com.github.vcth4nh.idesense.tools.navigation.FindFileTool
import com.github.vcth4nh.idesense.tools.navigation.FindImplementationsTool
import com.github.vcth4nh.idesense.tools.navigation.FindSuperMethodsTool
import com.github.vcth4nh.idesense.tools.navigation.FindSymbolTool
import com.github.vcth4nh.idesense.tools.navigation.FindUsagesTool
import com.github.vcth4nh.idesense.tools.navigation.SearchTextTool
import com.github.vcth4nh.idesense.tools.navigation.TypeHierarchyTool
import com.github.vcth4nh.idesense.tools.project.GetIndexStatusTool
import com.github.vcth4nh.idesense.tools.project.BuildProjectTool
import com.github.vcth4nh.idesense.tools.project.InstallPluginTool
import com.github.vcth4nh.idesense.tools.project.RestartIdeTool
import com.github.vcth4nh.idesense.tools.project.SyncFilesTool
import com.github.vcth4nh.idesense.tools.refactoring.MoveFileTool
import com.github.vcth4nh.idesense.tools.refactoring.RenameSymbolTool
import com.github.vcth4nh.idesense.handlers.isExcludedPath
import junit.framework.TestCase
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class ToolsUnitTest : TestCase() {
    private fun assertHasScopeAndNoLegacyFilters(properties: kotlinx.serialization.json.JsonObject?) {
        val scopeProperty = properties?.get(ParamNames.SCOPE)?.jsonObject
        assertNotNull("Should have scope property", scopeProperty)
        assertEquals(
            BuiltInSearchScope.supportedWireValues(),
            scopeProperty?.get("enum")?.jsonArray?.map { it.jsonPrimitive.content }
        )
        assertNull("Should not have includeLibraries property", properties?.get("includeLibraries"))
        assertNull("Should not have includeTests property", properties?.get("includeTests"))
    }

    private fun assertHasHierarchyScope(
        properties: kotlinx.serialization.json.JsonObject?,
        expectedValues: List<String>,
    ) {
        val scopeProperty = properties?.get(ParamNames.SCOPE)?.jsonObject
        assertNotNull("Should have scope property", scopeProperty)
        assertEquals(
            expectedValues,
            scopeProperty?.get("enum")?.jsonArray?.map { it.jsonPrimitive.content }
        )
        assertNull("Should not have includeLibraries property", properties?.get("includeLibraries"))
        assertNull("Should not have includeTests property", properties?.get("includeTests"))
    }

    fun testGetIndexStatusToolSchema() {
        val tool = GetIndexStatusTool()

        assertEquals(ToolNames.INDEX_STATUS, tool.name)
        assertNotNull(tool.description)
        assertNotNull(tool.inputSchema)
    }

    fun testSyncFilesToolSchema() {
        val tool = SyncFilesTool()

        assertEquals(ToolNames.SYNC_FILES, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have paths property", properties?.get("paths"))

        assertNull("Should not have required array (no required fields)", schema[SchemaConstants.REQUIRED])
    }

    fun testSyncFilesToolIsRegistered() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val tool = registry.getTool(ToolNames.SYNC_FILES)
        assertNotNull("ide_sync_files should be registered", tool)
        assertEquals(ToolNames.SYNC_FILES, tool?.name)
    }

    fun testBuildProjectToolSchema() {
        val tool = BuildProjectTool()

        assertEquals(ToolNames.BUILD_PROJECT, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have rebuild property", properties?.get(ParamNames.REBUILD))
        assertNotNull("Should have includeRawOutput property", properties?.get(ParamNames.INCLUDE_RAW_OUTPUT))
        assertNotNull("Should have timeoutSeconds property", properties?.get(ParamNames.TIMEOUT_SECONDS))

        assertNull("Should not have required array", schema[SchemaConstants.REQUIRED])
    }

    fun testBuildProjectToolIsRegistered() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val tool = registry.getTool(ToolNames.BUILD_PROJECT)
        assertNotNull("ide_build_project should be registered", tool)
        assertEquals(ToolNames.BUILD_PROJECT, tool?.name)
    }

    fun testInstallPluginToolSchema() {
        val tool = InstallPluginTool()

        assertEquals(ToolNames.INSTALL_PLUGIN, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have path property", properties?.get(ParamNames.PATH))

        assertNull("Should not have required array (all params optional)", schema[SchemaConstants.REQUIRED])
    }

    fun testInstallPluginToolIsRegistered() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val tool = registry.getTool(ToolNames.INSTALL_PLUGIN)
        assertNotNull("ide_install_plugin should be registered", tool)
        assertEquals(ToolNames.INSTALL_PLUGIN, tool?.name)
    }

    fun testRestartIdeToolSchema() {
        val tool = RestartIdeTool()

        assertEquals(ToolNames.RESTART_IDE, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have delaySeconds property", properties?.get(ParamNames.DELAY_SECONDS))

        assertNull("Should not have required array (all params optional)", schema[SchemaConstants.REQUIRED])
    }

    fun testRestartIdeToolIsRegistered() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val tool = registry.getTool(ToolNames.RESTART_IDE)
        assertNotNull("ide_restart should be registered", tool)
        assertEquals(ToolNames.RESTART_IDE, tool?.name)
    }

    fun testFindUsagesToolSchema() {
        val tool = FindUsagesTool()

        assertEquals(ToolNames.FIND_USAGES, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have file property", properties?.get(ParamNames.FILE))
        assertNotNull("Should have line property", properties?.get(ParamNames.LINE))
        assertNotNull("Should have column property", properties?.get(ParamNames.COLUMN))
        assertHasScopeAndNoLegacyFilters(properties)
        assertNotNull("Should have cursor property", properties?.get("cursor"))
        assertNotNull("Should have pageSize property", properties?.get("pageSize"))

        assertNull("Should not have anyOf (incompatible with Anthropic API)", schema["anyOf"])
        assertNull("Should not have required array (all params optional for pagination)", schema[SchemaConstants.REQUIRED])
    }

    fun testFindDefinitionToolSchema() {
        val tool = FindDefinitionTool()

        assertEquals(ToolNames.FIND_DEFINITION, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have file property", properties?.get(ParamNames.FILE))
        assertNotNull("Should have line property", properties?.get(ParamNames.LINE))
        assertNotNull("Should have column property", properties?.get(ParamNames.COLUMN))
    }

    fun testTypeHierarchyToolSchema() {
        val tool = TypeHierarchyTool()

        assertEquals(ToolNames.TYPE_HIERARCHY, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have file property", properties?.get(ParamNames.FILE))
        assertNotNull("Should have line property", properties?.get(ParamNames.LINE))
        assertNotNull("Should have column property", properties?.get(ParamNames.COLUMN))
        assertNotNull("Should have className property", properties?.get(ParamNames.CLASS_NAME))
        assertHasHierarchyScope(properties, listOf("all", "production", "test"))

        // direction (supertypes|subtypes|both) + maxDepth — parity with call hierarchy
        val directionProp = properties?.get(ParamNames.DIRECTION)?.jsonObject
        assertNotNull("Should have direction property", directionProp)
        assertEquals(
            listOf("supertypes", "subtypes", "both"),
            directionProp?.get("enum")?.jsonArray?.map { it.jsonPrimitive.content }
        )
        assertNotNull("Should have maxDepth property", properties?.get("maxDepth"))
    }

    fun testCallHierarchyToolSchema() {
        val tool = CallHierarchyTool()

        assertEquals(ToolNames.CALL_HIERARCHY, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have direction property", properties?.get(ParamNames.DIRECTION))
        assertHasHierarchyScope(
            properties,
            listOf("all", "production", "test", "this_class", "this_module")
        )
    }

    fun testFindImplementationsToolSchema() {
        val tool = FindImplementationsTool()

        assertEquals(ToolNames.FIND_IMPLEMENTATIONS, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have file property", properties?.get(ParamNames.FILE))
        assertNotNull("Should have line property", properties?.get(ParamNames.LINE))
        assertNotNull("Should have column property", properties?.get(ParamNames.COLUMN))
        assertHasScopeAndNoLegacyFilters(properties)
        assertNotNull("Should have cursor property", properties?.get("cursor"))
        assertNotNull("Should have pageSize property", properties?.get("pageSize"))

        assertNull("Should not have anyOf (incompatible with Anthropic API)", schema["anyOf"])
        assertNull("Should not have required array (all params optional for pagination)", schema[SchemaConstants.REQUIRED])
    }

    fun testFindClassToolSchemaUsesScope() {
        val tool = FindClassTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject

        assertNotNull("Should have query property", properties?.get(ParamNames.QUERY))
        assertHasScopeAndNoLegacyFilters(properties)
    }

    fun testFindFileToolSchemaUsesScope() {
        val tool = FindFileTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject

        assertNotNull("Should have query property", properties?.get(ParamNames.QUERY))
        assertHasScopeAndNoLegacyFilters(properties)
    }

    fun testFindSymbolToolSchemaUsesScope() {
        val tool = FindSymbolTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject

        assertNotNull("Should have query property", properties?.get(ParamNames.QUERY))
        assertHasScopeAndNoLegacyFilters(properties)
    }

    fun testGetDiagnosticsToolSchema() {
        val tool = GetDiagnosticsTool()

        assertEquals(ToolNames.DIAGNOSTICS, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        // Existing params
        assertNotNull("Should have project_path", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have file", properties?.get(ParamNames.FILE))
        assertNotNull("Should have line", properties?.get("line"))
        assertNotNull("Should have column", properties?.get("column"))
        assertNotNull("Should have startLine", properties?.get("startLine"))
        assertNotNull("Should have endLine", properties?.get("endLine"))

        // New params
        assertNotNull("Should have includeBuildErrors", properties?.get(ParamNames.INCLUDE_BUILD_ERRORS))
        assertNotNull("Should have includeTestResults", properties?.get(ParamNames.INCLUDE_TEST_RESULTS))
        assertNotNull("Should have severity", properties?.get(ParamNames.SEVERITY))
        assertNotNull("Should have testResultFilter", properties?.get(ParamNames.TEST_RESULT_FILTER))
        assertNotNull("Should have maxBuildErrors", properties?.get(ParamNames.MAX_BUILD_ERRORS))
        assertNotNull("Should have maxTestResults", properties?.get(ParamNames.MAX_TEST_RESULTS))

        // file should NOT be required anymore
        val required = schema[SchemaConstants.REQUIRED]?.jsonArray?.map { it.jsonPrimitive.content }
        assertTrue("file should not be required", required == null || !required.contains(ParamNames.FILE))
    }

    fun testGetDiagnosticsToolSeverityEnum() {
        val tool = GetDiagnosticsTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject
        val severityProp = properties?.get(ParamNames.SEVERITY)?.jsonObject

        val enumValues = severityProp?.get("enum")?.jsonArray?.map { it.jsonPrimitive.content }
        assertNotNull("severity should have enum values", enumValues)
        assertEquals(listOf("all", "errors", "warnings"), enumValues)
    }

    fun testGetDiagnosticsToolTestResultFilterEnum() {
        val tool = GetDiagnosticsTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject
        val filterProp = properties?.get(ParamNames.TEST_RESULT_FILTER)?.jsonObject

        val enumValues = filterProp?.get("enum")?.jsonArray?.map { it.jsonPrimitive.content }
        assertNotNull("testResultFilter should have enum values", enumValues)
        assertEquals(listOf("failed", "all"), enumValues)
    }

    /**
     * Tests that the tool registry registers built-in tools correctly.
     *
     * Note: The number of tools registered depends on available language plugins:
     * - Universal tools: Always registered in all IDEs
     * - Navigation tools: Registered when language handlers are available (Java, Python, JS/TS)
     *
     * In a unit test environment without the full IntelliJ Platform, only universal tools
     * may be registered since plugin detection may fail.
     */
    fun testToolRegistryRegistersUniversalTools() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        // Universal tools - always available in all IDEs
        val universalTools = listOf(
            ToolNames.FIND_USAGES,
            ToolNames.FIND_DEFINITION,
            ToolNames.FIND_SYMBOL,
            ToolNames.DIAGNOSTICS,
            ToolNames.INDEX_STATUS,
            ToolNames.SYNC_FILES,
            ToolNames.BUILD_PROJECT
        )

        // Universal tools should always be registered
        for (toolName in universalTools) {
            val tool = registry.getTool(toolName)
            assertNotNull("Universal tool $toolName should be registered", tool)
        }

        assertTrue("Should have at least 9 universal tools", registry.getAllTools().size >= 9)
    }

    /**
     * Tests tool registration for language-specific navigation tools.
     *
     * Note: This test may register fewer tools in unit test mode since handler detection
     * depends on the IntelliJ Platform being fully initialized.
     */
    fun testToolRegistryRegistersLanguageToolsWhenAvailable() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        // Language-specific navigation tools (registered when handlers available)
        val navigationTools = listOf(
            ToolNames.TYPE_HIERARCHY,
            ToolNames.CALL_HIERARCHY,
            ToolNames.FIND_IMPLEMENTATIONS,
            ToolNames.FIND_SUPER_METHODS,
            ToolNames.FILE_STRUCTURE
        )

        val registeredNavTools = navigationTools.count { registry.getTool(it) != null }

        // In unit tests, individual handler availability drives registration: the bundled Markdown
        // plugin registers a structure handler, so FILE_STRUCTURE is expected whenever any handler loads.
        if (registeredNavTools > 0) {
            assertTrue("FILE_STRUCTURE should be registered when the Markdown structure handler is available",
                registry.getTool(ToolNames.FILE_STRUCTURE) != null)
        }

        // RenameSymbolTool is universal and should always be registered
        assertTrue("RenameSymbolTool should always be registered (universal tool)",
            registry.getTool(ToolNames.REFACTOR_RENAME) != null)

        val totalTools = registry.getAllTools().size
        println("Tool registry test: $totalTools tools registered ($registeredNavTools navigation)")
    }

    /**
     * `ide_find_symbol` delegates to the platform's Go to Symbol popup stack (via
     * [com.github.vcth4nh.idesense.handlers.PopupFaithfulSymbolSearch]),
     * which works in any JetBrains IDE regardless of whether the plugin registers a
     * language-specific handler. The tool should therefore always be registered.
     */
    fun testFindSymbolToolIsRegisteredAsUniversal() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val tool = registry.getTool(ToolNames.FIND_SYMBOL)
        assertNotNull("ide_find_symbol should be registered as a universal tool", tool)
        assertEquals(ToolNames.FIND_SYMBOL, tool?.name)
    }

    // Phase 3: Refactoring Tools Schema Tests

    fun testRenameSymbolToolSchema() {
        val tool = RenameSymbolTool()

        assertEquals(ToolNames.REFACTOR_RENAME, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have file property", properties?.get(ParamNames.FILE))
        assertNotNull("Should have line property", properties?.get(ParamNames.LINE))
        assertNotNull("Should have column property", properties?.get(ParamNames.COLUMN))
        assertNotNull("Should have newName property", properties?.get(ParamNames.NEW_NAME))
        assertNotNull("Should have relatedRenamingStrategy property", properties?.get("relatedRenamingStrategy"))

        // line and column should be optional (not in required) to support file rename mode
        val required = schema[SchemaConstants.REQUIRED]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList()
        assertTrue("file should be required", required.contains(ParamNames.FILE))
        assertTrue("newName should be required", required.contains(ParamNames.NEW_NAME))
        assertFalse("line should NOT be required (optional for file rename)", required.contains(ParamNames.LINE))
        assertFalse("column should NOT be required (optional for file rename)", required.contains(ParamNames.COLUMN))

        // Verify relatedRenamingStrategy has enum values
        val relatedStrategyProp = properties?.get("relatedRenamingStrategy")?.jsonObject
        assertNotNull("relatedRenamingStrategy should have enum", relatedStrategyProp?.get("enum"))
        val enumValues = relatedStrategyProp?.get("enum")?.jsonArray?.map { it.jsonPrimitive.content }
        assertEquals(listOf("all", "none", "accessors_and_tests", "ask"), enumValues)
    }

    // New navigation tools

    fun testFindSymbolToolSchema() {
        val tool = FindSymbolTool()

        assertEquals(ToolNames.FIND_SYMBOL, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have query property", properties?.get(ParamNames.QUERY))
        assertHasScopeAndNoLegacyFilters(properties)
        assertNotNull("Should have limit property", properties?.get(ParamNames.LIMIT))
        assertNotNull("Should have cursor property", properties?.get("cursor"))
        assertNotNull("Should have pageSize property", properties?.get("pageSize"))

        assertNull("Should not have anyOf (incompatible with Anthropic API)", schema["anyOf"])
        assertNull("Should not have required array (all params optional for pagination)", schema[SchemaConstants.REQUIRED])
    }

    fun testFindSuperMethodsToolSchema() {
        val tool = FindSuperMethodsTool()

        assertEquals(ToolNames.FIND_SUPER_METHODS, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have file property", properties?.get(ParamNames.FILE))
        assertNotNull("Should have line property", properties?.get(ParamNames.LINE))
        assertNotNull("Should have column property", properties?.get(ParamNames.COLUMN))
    }

    fun testAllRegisteredToolNamesAreInToolNamesAll() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        for (tool in registry.getAllTools()) {
            assertTrue(
                "Registered tool '${tool.name}' should be listed in ToolNames.ALL",
                ToolNames.ALL.contains(tool.name)
            )
        }
    }

    fun testAllToolsHaveProjectPathInSchema() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val tools = registry.getAllTools()

        for (tool in tools) {
            val schema = tool.inputSchema
            val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject

            assertNotNull("${tool.name} schema should have properties", properties)

            val projectPathProp = properties?.get(ParamNames.PROJECT_PATH)?.jsonObject
            assertNotNull("${tool.name} schema should include project_path property", projectPathProp)
        }
    }

    fun testFileStructureToolSchema() {
        val tool = FileStructureTool()

        assertEquals(ToolNames.FILE_STRUCTURE, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have file property", properties?.get(ParamNames.FILE))

        val required = schema[SchemaConstants.REQUIRED]
        assertNotNull("Should have required array", required)
    }

    fun testFindClassToolSchema() {
        val tool = FindClassTool()

        assertEquals(ToolNames.FIND_CLASS, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have query property", properties?.get(ParamNames.QUERY))
        assertHasScopeAndNoLegacyFilters(properties)
        assertNotNull("Should have limit property", properties?.get(ParamNames.LIMIT))
        assertNotNull("Should have cursor property", properties?.get("cursor"))
        assertNotNull("Should have pageSize property", properties?.get("pageSize"))

        assertNull("Should not have anyOf (incompatible with Anthropic API)", schema["anyOf"])
        assertNull("Should not have required array (all params optional for pagination)", schema[SchemaConstants.REQUIRED])
    }

    fun testFindFileToolSchema() {
        val tool = FindFileTool()

        assertEquals(ToolNames.FIND_FILE, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have query property", properties?.get(ParamNames.QUERY))
        assertHasScopeAndNoLegacyFilters(properties)
        assertNotNull("Should have limit property", properties?.get(ParamNames.LIMIT))
        assertNotNull("Should have cursor property", properties?.get("cursor"))
        assertNotNull("Should have pageSize property", properties?.get("pageSize"))

        assertNull("Should not have anyOf (incompatible with Anthropic API)", schema["anyOf"])
        assertNull("Should not have required array (all params optional for pagination)", schema[SchemaConstants.REQUIRED])
    }

    fun testSearchTextToolSchema() {
        val tool = SearchTextTool()

        assertEquals(ToolNames.SEARCH_TEXT, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have query property", properties?.get(ParamNames.QUERY))
        assertNotNull("Should have context property", properties?.get(ParamNames.CONTEXT))
        assertNotNull("Should have caseSensitive property", properties?.get(ParamNames.CASE_SENSITIVE))
        assertNotNull("Should have limit property", properties?.get(ParamNames.LIMIT))
        assertNotNull("Should have cursor property", properties?.get("cursor"))
        assertNotNull("Should have pageSize property", properties?.get("pageSize"))

        assertNull("Should not have anyOf (incompatible with Anthropic API)", schema["anyOf"])
        assertNull("Should not have required array (all params optional for pagination)", schema[SchemaConstants.REQUIRED])
    }

    fun testNewSearchToolsAreRegistered() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        // Verify new fast search tools are registered
        val findClassTool = registry.getTool(ToolNames.FIND_CLASS)
        assertNotNull("ide_find_class should be registered", findClassTool)
        assertEquals(ToolNames.FIND_CLASS, findClassTool?.name)

        val findFileTool = registry.getTool(ToolNames.FIND_FILE)
        assertNotNull("ide_find_file should be registered", findFileTool)
        assertEquals(ToolNames.FIND_FILE, findFileTool?.name)

        val searchTextTool = registry.getTool(ToolNames.SEARCH_TEXT)
        assertNotNull("ide_search_text should be registered", searchTextTool)
        assertEquals(ToolNames.SEARCH_TEXT, searchTextTool?.name)
    }


    // ── MoveFileTool tests ──────────────────────────────────────────────────────

    fun testMoveFileToolSchema() {
        val tool = MoveFileTool()

        assertEquals(ToolNames.REFACTOR_MOVE, tool.name)
        assertNotNull(tool.description)

        val schema = tool.inputSchema
        assertEquals(SchemaConstants.TYPE_OBJECT, schema[SchemaConstants.TYPE]?.jsonPrimitive?.content)

        val properties = schema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull(properties)

        assertNotNull("Should have project_path property", properties?.get(ParamNames.PROJECT_PATH))
        assertNotNull("Should have file property", properties?.get(ParamNames.FILE))
        assertNotNull("Should have destination property", properties?.get(ParamNames.DESTINATION))
        assertNull("Should not expose update_references anymore", properties?.get("update_references"))

        val required = schema[SchemaConstants.REQUIRED]
        assertNotNull("Should have required array", required)
        assertTrue("Required should include 'file'", required.toString().contains("file"))
        assertTrue("Required should include 'destination'", required.toString().contains("destination"))
    }

    fun testMoveFileToolIsRegistered() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val tool = registry.getTool(ToolNames.REFACTOR_MOVE)
        assertNotNull("ide_move_file should be registered", tool)
        assertEquals(ToolNames.REFACTOR_MOVE, tool?.name)
    }

    fun testMoveFileToolDescriptionIncludesExamples() {
        val tool = MoveFileTool()
        val description = tool.description

        assertTrue("Description should mention file parameter", description.contains("file"))
        assertTrue("Description should mention destination parameter", description.contains("destination"))
        assertTrue("Description should mention references", description.contains("references"))
    }

    fun testFindClassToolSchemaHasFuzzySearchBoolean() {
        val tool = FindClassTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull("Should have properties", properties)

        assertNull("ide_find_class should no longer expose matchMode", properties?.get("matchMode"))

        val fuzzyProp = properties?.get(ParamNames.FUZZY_SEARCH)?.jsonObject
        assertNotNull("Should have fuzzySearch property", fuzzyProp)
        assertEquals(
            "fuzzySearch should be a boolean",
            SchemaConstants.TYPE_BOOLEAN,
            fuzzyProp?.get(SchemaConstants.TYPE)?.jsonPrimitive?.content
        )
    }

    fun testFindSymbolToolSchemaHasFuzzySearchBoolean() {
        val tool = FindSymbolTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull("Should have properties", properties)

        val fuzzyProp = properties?.get(ParamNames.FUZZY_SEARCH)?.jsonObject
        assertNotNull("Should have fuzzySearch property", fuzzyProp)
        assertEquals(
            "fuzzySearch should be a boolean",
            SchemaConstants.TYPE_BOOLEAN,
            fuzzyProp?.get(SchemaConstants.TYPE)?.jsonPrimitive?.content
        )
    }

    // ── language filter schema tests ───────────────────────────────────────────

    fun testFindSymbolToolSchemaHasLanguageFilter() {
        val tool = FindSymbolTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull("Should have properties", properties)
        assertNotNull("Should have language property", properties?.get(ParamNames.LANGUAGE))
    }

    fun testFindClassToolSchemaHasLanguageFilter() {
        val tool = FindClassTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull("Should have properties", properties)
        assertNotNull("Should have language property", properties?.get(ParamNames.LANGUAGE))
    }

    // ── maxPreviewLines schema test ────────────────────────────────────────────

    // ── FindUsagesTool totalCount/truncated via maxResults schema ──────────────

    fun testFindUsagesToolSchemaHasMaxResults() {
        val tool = FindUsagesTool()
        val properties = tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject
        assertNotNull("Should have properties", properties)
        assertNotNull("Should have maxResults property", properties?.get("maxResults"))
    }

    // ── isExcludedPath pure logic tests ─────────────────────────────────────

    fun testIsExcludedPathDetectsBuildDirs() {
        assertTrue("bin/ should be excluded",     isExcludedPath("bin/Main.class"))
        assertTrue("build/ should be excluded",   isExcludedPath("build/libs/app.jar"))
        assertTrue("out/ should be excluded",     isExcludedPath("out/production/Main.class"))
        assertTrue(".gradle/ should be excluded", isExcludedPath(".gradle/cache/file.jar"))
    }

    fun testIsExcludedPathDetectsVenvDirs() {
        // Root-level venv dirs
        assertTrue(".venv/ should be excluded",   isExcludedPath(".venv/lib/python3.11/site-packages/flask/__init__.py"))
        assertTrue("venv/ should be excluded",    isExcludedPath("venv/lib/python3.11/site-packages/flask/__init__.py"))
        assertTrue(".env/ should be excluded",    isExcludedPath(".env/lib/python3.11/site-packages/flask/__init__.py"))
        assertTrue("env/ should be excluded",     isExcludedPath("env/lib/python3.11/site-packages/flask/__init__.py"))
        // Nested venv dirs (e.g. multi-module projects like python-services/.venv/)
        assertTrue("nested .venv/ should be excluded", isExcludedPath("python-services/.venv/lib/python3.13/site-packages/h11/_writers.py"))
        assertTrue("nested venv/ should be excluded",  isExcludedPath("backend/venv/lib/python3.11/flask/__init__.py"))
    }

    fun testIsExcludedPathDetectsNodeModules() {
        assertTrue("node_modules/ should be excluded",        isExcludedPath("node_modules/@types/react/index.d.ts"))
        assertTrue("nested node_modules/ should be excluded", isExcludedPath("packages/ui/node_modules/react/index.js"))
    }

    fun testIsExcludedPathDetectsWorktrees() {
        assertTrue(".worktrees/ should be excluded",        isExcludedPath(".worktrees/feature-branch/src/Main.kt"))
        assertTrue(".claude/worktrees/ should be excluded", isExcludedPath(".claude/worktrees/fix-123/src/Main.kt"))
    }

    fun testIsExcludedPathAllowsSourcePaths() {
        assertFalse("src/ should not be excluded",        isExcludedPath("src/main/kotlin/Foo.kt"))
        assertFalse("nested bin path should not match",   isExcludedPath("src/bin/config.txt"))
        assertFalse("nested build path should not match", isExcludedPath("src/build/notes.md"))
        assertFalse("root file should not be excluded",   isExcludedPath("README.md"))
    }

}
