package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.McpConstants
import com.github.vcth4nh.idesense.constants.ErrorMessages
import com.github.vcth4nh.idesense.constants.JsonRpcMethods
import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.exceptions.McpException
import com.github.vcth4nh.idesense.history.CommandEntry
import com.github.vcth4nh.idesense.history.CommandHistoryService
import com.github.vcth4nh.idesense.history.CommandStatus
import com.github.vcth4nh.idesense.server.models.*
import com.github.vcth4nh.idesense.settings.McpSettings
import com.github.vcth4nh.idesense.tools.ToolRegistry
import com.github.vcth4nh.idesense.tools.schema.ArgumentValidator
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.*

class JsonRpcHandler @JvmOverloads constructor(
    private val toolRegistry: ToolRegistry,
    private val recordHistory: (Project, CommandEntry) -> Unit = { project, entry ->
        CommandHistoryService.getInstance(project).recordCommand(entry)
    },
    private val updateHistory: (Project, String, CommandStatus, String?, Long?) -> Unit = { project, id, status, result, duration ->
        CommandHistoryService.getInstance(project).updateCommandStatus(id, status, result, duration)
    },
    private val isToolEnabled: (String) -> Boolean = { McpSettings.getInstance().isToolEnabled(it) }
) {
    private val projectResolver = ProjectResolver
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
        prettyPrint = false
    }

    companion object {
        private val LOG = logger<JsonRpcHandler>()
    }

    suspend fun handleRequest(jsonString: String): String? =
        handleRequest(jsonString, McpConstants.MCP_PROTOCOL_VERSION)

    suspend fun handleRequest(
        jsonString: String,
        protocolVersion: String
    ): String? {
        val request = try {
            json.decodeFromString<JsonRpcRequest>(jsonString)
        } catch (e: Exception) {
            LOG.warn("Failed to parse JSON-RPC request", e)
            return json.encodeToString(createErrorResponse(code = JsonRpcErrorCodes.PARSE_ERROR, message = ErrorMessages.PARSE_ERROR))
        }

        if (request.jsonrpc != "2.0") {
            return json.encodeToString(createErrorResponse(
                id = request.id,
                code = JsonRpcErrorCodes.INVALID_REQUEST,
                message = "Invalid JSON-RPC version: ${request.jsonrpc}. Expected \"2.0\"."
            ))
        }

        val response = try {
            routeRequest(request, protocolVersion)
        } catch (e: Exception) {
            LOG.error("Error processing request: ${request.method}", e)
            createErrorResponse(request.id, JsonRpcErrorCodes.INTERNAL_ERROR, e.message ?: "Unknown error")
        }

        return response?.let { json.encodeToString(response) }
    }

    private suspend fun routeRequest(request: JsonRpcRequest, protocolVersion: String): JsonRpcResponse? {
        return when (request.method) {
            JsonRpcMethods.INITIALIZE -> processInitialize(request, protocolVersion)
            JsonRpcMethods.NOTIFICATIONS_INITIALIZED -> null
            JsonRpcMethods.TOOLS_LIST -> processToolsList(request)
            JsonRpcMethods.TOOLS_CALL -> processToolCall(request)
            JsonRpcMethods.PING -> processPing(request)
            else -> createErrorResponse(request.id, JsonRpcErrorCodes.METHOD_NOT_FOUND, ErrorMessages.methodNotFound(request.method))
        }
    }

    private fun processInitialize(request: JsonRpcRequest, protocolVersion: String): JsonRpcResponse {
        val requested = (request.params?.get("protocolVersion") as? JsonPrimitive)?.contentOrNull
        val negotiated = if (requested != null && requested in McpConstants.SUPPORTED_PROTOCOL_VERSIONS) {
            requested
        } else {
            protocolVersion
        }

        val result = InitializeResult(
            protocolVersion = negotiated,
            serverInfo = ServerInfo(
                name = McpConstants.SERVER_NAME,
                version = McpConstants.SERVER_VERSION,
                description = McpConstants.SERVER_DESCRIPTION
            ),
            capabilities = ServerCapabilities(
                tools = ToolCapability(listChanged = false)
            )
        )

        return JsonRpcResponse(
            id = request.id,
            result = json.encodeToJsonElement(result)
        )
    }

    private fun processToolsList(request: JsonRpcRequest): JsonRpcResponse {
        val tools = toolRegistry.getToolDefinitions()
        val result = ToolsListResult(tools = tools)

        return JsonRpcResponse(
            id = request.id,
            result = json.encodeToJsonElement(result)
        )
    }

    private suspend fun processToolCall(request: JsonRpcRequest): JsonRpcResponse {
        val params = request.params
            ?: return createErrorResponse(request.id, JsonRpcErrorCodes.INVALID_PARAMS, ErrorMessages.MISSING_PARAMS)

        val toolName = params[ParamNames.NAME]?.jsonPrimitive?.contentOrNull
            ?: return createErrorResponse(request.id, JsonRpcErrorCodes.INVALID_PARAMS, ErrorMessages.MISSING_TOOL_NAME)

        val arguments = params[ParamNames.ARGUMENTS]?.jsonObject ?: JsonObject(emptyMap())

        val tool = toolRegistry.getTool(toolName)
            ?: return createErrorResponse(request.id, JsonRpcErrorCodes.METHOD_NOT_FOUND, ErrorMessages.toolNotFound(toolName))

        // Disabled tools are hidden from tools/list; enforce the same state here so a client
        // that already knows the name cannot invoke them.
        if (!isToolEnabled(toolName)) {
            return createErrorResponse(request.id, JsonRpcErrorCodes.METHOD_NOT_FOUND, ErrorMessages.toolDisabled(toolName))
        }

        // Extract optional project_path from arguments
        val projectPath = arguments[ParamNames.PROJECT_PATH]?.jsonPrimitive?.contentOrNull

        val projectResult = projectResolver.resolve(projectPath)
        if (projectResult.isError) {
            return JsonRpcResponse(
                id = request.id,
                result = json.encodeToJsonElement(projectResult.errorResult!!)
            )
        }

        val project = projectResult.project!!

        // Strict argument validation against the tool's input schema (Layer B).
        // Returns BEFORE recording history — mirrors the project-resolution early-return above.
        val violations = ArgumentValidator.validate(arguments, tool.inputSchema)
        if (violations.isNotEmpty()) {
            return structuredToolError(request.id, McpErrors.invalidArguments(toolName, violations))
        }

        // Record command in history
        val commandEntry = CommandEntry(
            toolName = toolName,
            parameters = arguments
        )

        recordHistorySafely(project, commandEntry)

        val startTime = System.currentTimeMillis()

        return try {
            val result = tool.execute(project, arguments)
            val duration = System.currentTimeMillis() - startTime

            // Update history
            updateHistorySafely(
                project = project,
                commandEntry = commandEntry,
                status = if (result.isError) CommandStatus.ERROR else CommandStatus.SUCCESS,
                result = result.content.firstOrNull()?.let {
                    when (it) {
                        is ContentBlock.Text -> it.text
                        is ContentBlock.Image -> "[Image]"
                    }
                },
                duration = duration
            )

            JsonRpcResponse(
                id = request.id,
                result = json.encodeToJsonElement(result)
            )
        } catch (e: McpException) {
            val duration = System.currentTimeMillis() - startTime
            // Client-caused (dumb mode, not-found, conflict, …) — do NOT log at ERROR.
            LOG.info("Tool '$toolName' returned ${e.errorType}: ${e.message}")

            updateHistorySafely(
                project = project,
                commandEntry = commandEntry,
                status = CommandStatus.ERROR,
                result = e.message,
                duration = duration
            )

            structuredToolError(request.id, McpErrors.fromException(e))
        } catch (e: Exception) {
            val duration = System.currentTimeMillis() - startTime
            LOG.error("Tool execution failed: $toolName", e)

            updateHistorySafely(
                project = project,
                commandEntry = commandEntry,
                status = CommandStatus.ERROR,
                result = e.message,
                duration = duration
            )

            structuredToolError(
                request.id,
                McpErrors.generic("internal_error", e.message ?: ErrorMessages.UNKNOWN_ERROR)
            )
        }
    }

    private fun recordHistorySafely(project: Project, commandEntry: CommandEntry) {
        try {
            recordHistory(project, commandEntry)
        } catch (e: Exception) {
            LOG.warn("Failed to record command history for ${commandEntry.toolName}", e)
        }
    }

    private fun updateHistorySafely(
        project: Project,
        commandEntry: CommandEntry,
        status: CommandStatus,
        result: String?,
        duration: Long
    ) {
        try {
            updateHistory(project, commandEntry.id, status, result, duration)
        } catch (e: Exception) {
            LOG.warn("Failed to update command history for ${commandEntry.toolName}", e)
        }
    }

    private fun processPing(request: JsonRpcRequest): JsonRpcResponse {
        return JsonRpcResponse(
            id = request.id,
            result = JsonObject(emptyMap())
        )
    }

    /**
     * Renders a canonical error body ([McpErrors]) into a tool-result `JsonRpcResponse`
     * (`isError:true` + text mirror + `structuredContent`). The bodies are trivial objects, so
     * `fromElement` cannot realistically throw; if it ever did, the outer [handleRequest] try/catch
     * is the backstop, returning a JSON-RPC INTERNAL_ERROR.
     */
    private fun structuredToolError(id: JsonElement?, body: JsonObject): JsonRpcResponse {
        val result = StructuredToolResult.fromElement(
            element = body,
            isError = true,
            format = McpSettings.getInstance().responseFormat,
        )
        return JsonRpcResponse(id = id, result = json.encodeToJsonElement(result))
    }

    private fun createErrorResponse(
        id: JsonElement? = null,
        code: Int,
        message: String
    ) = JsonRpcResponse(
        id = id,
        error = JsonRpcError(code = code, message = message)
    )
}
