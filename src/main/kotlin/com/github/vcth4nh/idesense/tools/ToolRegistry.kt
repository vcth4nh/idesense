package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.server.McpServerService
import com.github.vcth4nh.idesense.server.models.ToolDefinition
import com.github.vcth4nh.idesense.settings.McpSettings
import com.github.vcth4nh.idesense.tools.intelligence.GetDiagnosticsTool
import com.github.vcth4nh.idesense.tools.navigation.FileStructureTool
import com.github.vcth4nh.idesense.tools.navigation.FindClassTool
import com.github.vcth4nh.idesense.tools.navigation.FindDefinitionTool
import com.github.vcth4nh.idesense.tools.navigation.FindFileTool
import com.github.vcth4nh.idesense.tools.navigation.FindImplementationsTool
import com.github.vcth4nh.idesense.tools.navigation.FindSymbolTool
import com.github.vcth4nh.idesense.tools.navigation.FindUsagesTool
import com.github.vcth4nh.idesense.tools.navigation.ReadFileTool
import com.github.vcth4nh.idesense.tools.navigation.SearchTextTool
import com.github.vcth4nh.idesense.tools.project.GetIndexStatusTool
import com.github.vcth4nh.idesense.tools.project.InstallPluginTool
import com.github.vcth4nh.idesense.tools.project.RestartIdeTool
import com.github.vcth4nh.idesense.tools.project.SyncFilesTool
import com.github.vcth4nh.idesense.tools.refactoring.MoveFileTool
import com.github.vcth4nh.idesense.tools.refactoring.RenameSymbolTool
import com.intellij.openapi.diagnostic.logger
import java.util.concurrent.ConcurrentHashMap

/**
 * Registry for MCP tools available to AI assistants.
 *
 * The registry manages the lifecycle of tools and provides thread-safe access
 * for tool lookup and definition generation.
 *
 * ## Built-in Tools
 *
 * The registry automatically registers built-in tools based on IDE capabilities.
 *
 * ### Universal Tools (All JetBrains IDEs)
 *
 * These tools work in all JetBrains IDEs (IntelliJ, PyCharm, WebStorm, GoLand, etc.):
 *
 * - `ide_find_usages` - Find all usages of a symbol
 * - `ide_find_definition` - Find symbol definition location
 * - `ide_find_class` - Class search using CLASS_EP_NAME index
 * - `ide_find_file` - File search using FILE_EP_NAME index
 * - `ide_find_symbol` - Search for symbols by name (universal, popup-backed)
 * - `ide_search_text` - Text search using word index
 * - `ide_diagnostics` - Analyze code for problems and available intentions
 * - `ide_install_plugin` - Install a locally built plugin .zip into this IDE (disabled by default)
 * - `ide_restart` - Restart this IDE to load a freshly installed plugin (disabled by default)
 * - `ide_index_status` - Check indexing status
 *
 * ### Language-Specific Navigation Tools
 *
 * These tools support multiple languages (Java, Kotlin, Python, JavaScript/TypeScript, PHP, Rust)
 * and are registered when at least one language handler is available:
 *
 * - `ide_type_hierarchy` - Get class inheritance hierarchy
 * - `ide_call_hierarchy` - Analyze method call relationships
 * - `ide_find_implementations` - Find interface/method implementations
 * - `ide_find_super_methods` - Find methods that a method overrides
 *
 * ### Universal Refactoring Tools
 *
 * - `ide_refactor_rename` - Rename symbol (works across ALL languages via RenameProcessor)
 * - `ide_move_file` - Move file to a new directory using the IDE move backend appropriate for that file type
 *
 * ## Custom Tool Registration
 *
 * Custom tools can be registered programmatically using [register].
 *
 * @see McpTool
 * @see McpServerService
 */
class ToolRegistry {

    companion object {
        private val LOG = logger<ToolRegistry>()
    }

    private val tools = ConcurrentHashMap<String, McpTool>()

    /**
     * Registers a tool with the registry.
     *
     * If a tool with the same name already exists, it will be replaced.
     *
     * @param tool The tool to register
     */
    fun register(tool: McpTool) {
        tools[tool.name] = tool
        LOG.info("Registered MCP tool: ${tool.name}")
    }

    /**
     * Removes a tool from the registry.
     *
     * @param toolName The name of the tool to remove
     */
    fun unregister(toolName: String) {
        tools.remove(toolName)
        LOG.info("Unregistered MCP tool: $toolName")
    }

    /**
     * Gets a tool by name.
     *
     * @param name The tool name (e.g., `ide_find_usages`)
     * @return The tool, or null if not found
     */
    fun getTool(name: String): McpTool? {
        return tools[name]
    }

    /**
     * Returns all registered tools.
     *
     * @return List of all tools
     */
    fun getAllTools(): List<McpTool> {
        return tools.values.toList()
    }

    /**
     * Gets tool definitions for the MCP `tools/list` response.
     * Respects user settings for disabled tools.
     *
     * @return List of enabled tool definitions with name, description, and schema
     */
    fun getToolDefinitions(): List<ToolDefinition> {
        val settings = McpSettings.getInstance()
        return tools.values
            .filter { settings.isToolEnabled(it.name) }
            .map { tool ->
                ToolDefinition(
                    name = tool.name,
                    description = tool.description,
                    inputSchema = tool.inputSchema
                )
            }
    }

    /**
     * Gets ALL tool definitions regardless of enabled/disabled state.
     * Used by settings UI to display all available tools.
     *
     * @return List of all tool definitions
     */
    fun getAllToolDefinitions(): List<ToolDefinition> {
        return tools.values.map { tool ->
            ToolDefinition(
                name = tool.name,
                description = tool.description,
                inputSchema = tool.inputSchema
            )
        }
    }

    /**
     * Registers all built-in tools.
     *
     * This is called automatically during [McpServerService] initialization.
     * Tools are registered conditionally based on IDE capabilities:
     * - Universal tools are always registered
     * - Language-specific navigation tools are registered when any language handler is available
     */
    fun registerBuiltInTools() {
        // Universal tools - work in all JetBrains IDEs
        registerUniversalTools()

        // Language-specific navigation tools - registered when handlers are available
        registerLanguageNavigationTools()

        LOG.info("Registered ${tools.size} built-in MCP tools")
        logAvailableLanguages()
    }

    private fun logAvailableLanguages() {
        LOG.info("Language services initialized")
    }

    /**
     * Registers universal tools that work in all JetBrains IDEs.
     *
     * These tools use only platform APIs (com.intellij.modules.platform)
     * and do not depend on Java-specific PSI classes.
     */
    private fun registerUniversalTools() {
        // Navigation tools (universal)
        register(FindUsagesTool())
        register(FindDefinitionTool())
        register(FileStructureTool())

        // Intelligence tools
        register(GetDiagnosticsTool())

        // Project tools
        register(GetIndexStatusTool())
        register(SyncFilesTool())
        register(InstallPluginTool())
        register(RestartIdeTool())

        // Refactoring tools (universal - uses platform APIs)
        register(RenameSymbolTool())
        register(MoveFileTool())

        // Fast search tools (universal)
        register(FindClassTool())
        register(FindFileTool())
        register(FindSymbolTool())
        register(SearchTextTool())
        register(ReadFileTool())

        // Navigation tools (EP-delegated, universal)
        register(FindImplementationsTool())

        LOG.info("Registered universal tools (available in all JetBrains IDEs)")
    }

    private data class ConditionalTool(
        val className: String,
        val isAvailable: () -> Boolean
    )

    private val languageNavigationTools = listOf(
        ConditionalTool("com.github.vcth4nh.idesense.tools.navigation.TypeHierarchyTool") { true },
        ConditionalTool("com.github.vcth4nh.idesense.tools.navigation.CallHierarchyTool") { true },
        ConditionalTool("com.github.vcth4nh.idesense.tools.navigation.FindSuperMethodsTool") { LanguageServices.hasAnySuperMethodsProvider() },
    )

    /**
     * Registers language-specific navigation tools.
     *
     * These tools delegate to language handlers and support multiple languages
     * (Java, Kotlin, Python, JavaScript/TypeScript, PHP, Rust).
     *
     * Tools are registered when at least one language handler is available
     * for the tool's functionality.
     */
    private fun registerLanguageNavigationTools() {
        for (tool in languageNavigationTools) {
            try {
                if (tool.isAvailable()) {
                    val toolClass = Class.forName(tool.className)
                    register(toolClass.getDeclaredConstructor().newInstance() as McpTool)
                }
            } catch (e: Exception) {
                LOG.warn("Failed to register language navigation tool ${tool.className}: ${e.message}")
            }
        }
    }
}
