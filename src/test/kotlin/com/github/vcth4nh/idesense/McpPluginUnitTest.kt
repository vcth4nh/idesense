package com.github.vcth4nh.idesense

import com.github.vcth4nh.idesense.constants.JsonRpcMethods
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.models.JsonRpcErrorCodes
import com.github.vcth4nh.idesense.server.models.JsonRpcRequest
import com.github.vcth4nh.idesense.server.models.JsonRpcResponse
import com.github.vcth4nh.idesense.tools.ToolRegistry
import junit.framework.TestCase
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive

class McpPluginUnitTest : TestCase() {

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    fun testJsonRpcRequestSerialization() {
        val request = JsonRpcRequest(
            id = JsonPrimitive(1),
            method = JsonRpcMethods.TOOLS_LIST
        )

        val serialized = json.encodeToString(request)
        val deserialized = json.decodeFromString<JsonRpcRequest>(serialized)

        assertEquals(McpConstants.JSON_RPC_VERSION, deserialized.jsonrpc)
        assertEquals(JsonRpcMethods.TOOLS_LIST, deserialized.method)
    }

    fun testJsonRpcResponseSerialization() {
        val response = JsonRpcResponse(
            id = JsonPrimitive(1),
            result = JsonPrimitive("test")
        )

        val serialized = json.encodeToString(response)
        val deserialized = json.decodeFromString<JsonRpcResponse>(serialized)

        assertEquals(McpConstants.JSON_RPC_VERSION, deserialized.jsonrpc)
        assertNull(deserialized.error)
    }

    fun testToolRegistry() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val tools = registry.getAllTools()
        assertTrue("Should have registered tools", tools.isNotEmpty())

        val findReferencesTool = registry.getTool(ToolNames.FIND_USAGES)
        assertNotNull("${ToolNames.FIND_USAGES} tool should be registered", findReferencesTool)

        val findDefTool = registry.getTool(ToolNames.FIND_DEFINITION)
        assertNotNull("${ToolNames.FIND_DEFINITION} tool should be registered", findDefTool)

        val indexStatusTool = registry.getTool(ToolNames.INDEX_STATUS)
        assertNotNull("${ToolNames.INDEX_STATUS} tool should be registered", indexStatusTool)
    }

    fun testJsonRpcErrorCodes() {
        assertEquals(-32700, JsonRpcErrorCodes.PARSE_ERROR)
        assertEquals(-32600, JsonRpcErrorCodes.INVALID_REQUEST)
        assertEquals(-32601, JsonRpcErrorCodes.METHOD_NOT_FOUND)
        assertEquals(-32602, JsonRpcErrorCodes.INVALID_PARAMS)
        assertEquals(-32603, JsonRpcErrorCodes.INTERNAL_ERROR)
    }
}
