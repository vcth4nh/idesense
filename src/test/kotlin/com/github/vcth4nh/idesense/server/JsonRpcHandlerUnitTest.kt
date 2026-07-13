package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.McpConstants
import com.github.vcth4nh.idesense.constants.JsonRpcMethods
import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.models.JsonRpcErrorCodes
import com.github.vcth4nh.idesense.server.models.JsonRpcRequest
import com.github.vcth4nh.idesense.server.models.JsonRpcResponse
import com.github.vcth4nh.idesense.tools.ToolRegistry
import junit.framework.TestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

class JsonRpcHandlerUnitTest : TestCase() {

    private lateinit var handler: JsonRpcHandler
    private lateinit var toolRegistry: ToolRegistry

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    override fun setUp() {
        super.setUp()
        toolRegistry = ToolRegistry()
        toolRegistry.registerBuiltInTools()
        handler = JsonRpcHandler(toolRegistry)
    }

    fun testInitializeRequest() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(1),
            method = JsonRpcMethods.INITIALIZE,
            params = buildJsonObject {
                put("protocolVersion", McpConstants.MCP_PROTOCOL_VERSION)
                put("clientInfo", buildJsonObject {
                    put("name", "test-client")
                    put("version", "1.0.0")
                })
            }
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNull("Initialize should not return error", response.error)
        assertNotNull("Initialize should return result", response.result)

        val result = response.result!!.jsonObject
        assertNotNull("Result should contain serverInfo", result["serverInfo"])
        assertNotNull("Result should contain capabilities", result["capabilities"])

        val serverInfo = result["serverInfo"]!!.jsonObject
        assertEquals(McpConstants.SERVER_NAME, serverInfo["name"]?.jsonPrimitive?.content)
        assertNotNull("serverInfo should contain description", serverInfo["description"])
        assertTrue(
            "description should mention code intelligence",
            serverInfo["description"]?.jsonPrimitive?.content?.contains("code intelligence", ignoreCase = true) == true
        )
    }

    fun testInitializeRequestCanOverrideProtocolVersion() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(1),
            method = JsonRpcMethods.INITIALIZE,
            params = buildJsonObject {
                put("protocolVersion", "2024-11-05")
                put("clientInfo", buildJsonObject {
                    put("name", "test-client")
                    put("version", "1.0.0")
                })
            }
        )

        val responseJson = handler.handleRequest(
            json.encodeToString(JsonRpcRequest.serializer(), request),
            protocolVersion = "2024-11-05"
        )
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNull("Initialize should not return error", response.error)
        assertEquals(
            "2024-11-05",
            response.result!!.jsonObject["protocolVersion"]!!.jsonPrimitive.content
        )
    }

    fun testPingRequest() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(4),
            method = JsonRpcMethods.PING
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNull("${JsonRpcMethods.PING} should not return error", response.error)
        assertNotNull("${JsonRpcMethods.PING} should return result", response.result)
    }

    fun testMethodNotFound() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(5),
            method = "unknown/method"
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNotNull("Unknown method should return error", response.error)
        assertEquals(JsonRpcErrorCodes.METHOD_NOT_FOUND, response.error?.code)
    }

    fun testToolCallMissingParams() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(6),
            method = JsonRpcMethods.TOOLS_CALL
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNotNull("${JsonRpcMethods.TOOLS_CALL} without params should return error", response.error)
        assertEquals(JsonRpcErrorCodes.INVALID_PARAMS, response.error?.code)
    }

    fun testToolCallMissingToolName() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(7),
            method = JsonRpcMethods.TOOLS_CALL,
            params = buildJsonObject {
                put(ParamNames.ARGUMENTS, buildJsonObject { })
            }
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNotNull("${JsonRpcMethods.TOOLS_CALL} without tool name should return error", response.error)
        assertEquals(JsonRpcErrorCodes.INVALID_PARAMS, response.error?.code)
    }

    fun testToolCallUnknownTool() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(8),
            method = JsonRpcMethods.TOOLS_CALL,
            params = buildJsonObject {
                put(ParamNames.NAME, "unknown_tool")
                put(ParamNames.ARGUMENTS, buildJsonObject { })
            }
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNotNull("${JsonRpcMethods.TOOLS_CALL} with unknown tool should return error", response.error)
        assertEquals(JsonRpcErrorCodes.METHOD_NOT_FOUND, response.error?.code)
    }

    fun testParseError() = runBlocking {
        val responseJson = handler.handleRequest("not valid json")
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNotNull("Invalid JSON should return error", response.error)
        assertEquals(JsonRpcErrorCodes.PARSE_ERROR, response.error?.code)
    }

    fun testInvalidJsonRpcVersion() = runBlocking {
        val requestJson = """{"jsonrpc":"1.0","id":1,"method":"ping"}"""

        val responseJson = handler.handleRequest(requestJson)
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNotNull("Invalid jsonrpc version should return error", response.error)
        assertEquals(JsonRpcErrorCodes.INVALID_REQUEST, response.error?.code)
        assertTrue(
            "Error message should mention version",
            response.error?.message?.contains("2.0") == true
        )
    }

    fun testNotificationReturnsNull() = runBlocking {
        val requestJson = """{"jsonrpc":"2.0","method":"notifications/initialized"}"""

        val responseJson = handler.handleRequest(requestJson)

        assertNull("Notification should return null (no response)", responseJson)
    }

    fun testInitializeEchoesRequestedSupportedVersion() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(1),
            method = JsonRpcMethods.INITIALIZE,
            params = buildJsonObject { put("protocolVersion", "2025-11-25") }
        )
        val responseJson = handler.handleRequest(
            json.encodeToString(JsonRpcRequest.serializer(), request),
            protocolVersion = "2025-11-25"
        )
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)
        assertEquals("2025-11-25", response.result!!.jsonObject["protocolVersion"]!!.jsonPrimitive.content)
    }

    fun testInitializeNegotiatesDownToOlderSupportedVersion() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(1),
            method = JsonRpcMethods.INITIALIZE,
            params = buildJsonObject { put("protocolVersion", "2025-03-26") }
        )
        val responseJson = handler.handleRequest(
            json.encodeToString(JsonRpcRequest.serializer(), request),
            protocolVersion = "2025-11-25"
        )
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)
        assertEquals("2025-03-26", response.result!!.jsonObject["protocolVersion"]!!.jsonPrimitive.content)
    }

    fun testToolCallDisabledToolIsRejected() = runBlocking {
        val gated = JsonRpcHandler(
            toolRegistry,
            isToolEnabled = { it != ToolNames.INSTALL_PLUGIN }
        )
        val request = JsonRpcRequest(
            id = JsonPrimitive(9),
            method = JsonRpcMethods.TOOLS_CALL,
            params = buildJsonObject {
                put(ParamNames.NAME, ToolNames.INSTALL_PLUGIN)
                put(ParamNames.ARGUMENTS, buildJsonObject { })
            }
        )

        val responseJson = gated.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNotNull("Disabled tool call should return an error", response.error)
        assertEquals(JsonRpcErrorCodes.METHOD_NOT_FOUND, response.error?.code)
        assertTrue(
            "Error should say the tool is disabled, got: ${response.error?.message}",
            response.error?.message?.contains("disabled", ignoreCase = true) == true
        )
    }

    fun testToolCallEnabledToolIsNotRejectedAsDisabled() = runBlocking {
        val gated = JsonRpcHandler(
            toolRegistry,
            isToolEnabled = { true }
        )
        val request = JsonRpcRequest(
            id = JsonPrimitive(10),
            method = JsonRpcMethods.TOOLS_CALL,
            params = buildJsonObject {
                put(ParamNames.NAME, ToolNames.INSTALL_PLUGIN)
                put(ParamNames.ARGUMENTS, buildJsonObject { })
            }
        )

        // Without a platform, an enabled call legitimately dies AFTER the gate (project
        // resolution logs an error, which the test-mode logger rethrows). Reaching post-gate
        // processing — whether it then returns or throws — must never be the disabled rejection.
        val responseJson = try {
            gated.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        } catch (e: AssertionError) {
            return@runBlocking
        }
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertTrue(
            "Enabled tool must not be rejected as disabled, got: ${response.error?.message}",
            response.error?.message?.contains("disabled", ignoreCase = true) != true
        )
    }

    fun testInitializeFallsBackForUnsupportedRequestedVersion() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(1),
            method = JsonRpcMethods.INITIALIZE,
            params = buildJsonObject { put("protocolVersion", "1999-01-01") }
        )
        val responseJson = handler.handleRequest(
            json.encodeToString(JsonRpcRequest.serializer(), request),
            protocolVersion = "2025-11-25"
        )
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)
        assertEquals("2025-11-25", response.result!!.jsonObject["protocolVersion"]!!.jsonPrimitive.content)
    }
}
