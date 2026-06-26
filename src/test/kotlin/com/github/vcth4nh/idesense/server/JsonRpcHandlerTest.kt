package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.constants.JsonRpcMethods
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.models.JsonRpcRequest
import com.github.vcth4nh.idesense.server.models.JsonRpcResponse
import com.github.vcth4nh.idesense.tools.ToolRegistry
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Platform-dependent tests that require IntelliJ Platform indexing.
 * For JSON-RPC protocol tests that don't need the platform, see JsonRpcHandlerUnitTest.
 */
class JsonRpcHandlerTest : BasePlatformTestCase() {

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

    fun testToolCallWithValidTool() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(9),
            method = "tools/call",
            params = buildJsonObject {
                put("name", ToolNames.INDEX_STATUS)
                put("arguments", buildJsonObject { })
            }
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNull("${ToolNames.INDEX_STATUS} should not return JSON-RPC error", response.error)
        assertNotNull("${ToolNames.INDEX_STATUS} should return result", response.result)
    }

    fun testToolsListRequest() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(2),
            method = JsonRpcMethods.TOOLS_LIST
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNull("${JsonRpcMethods.TOOLS_LIST} should not return error", response.error)
        assertNotNull("${JsonRpcMethods.TOOLS_LIST} should return result", response.result)

        val result = response.result!!.jsonObject
        assertNotNull("Result should contain tools array", result["tools"])
    }

    // Single-project BasePlatformTestCase: ProjectResolver picks the only open project.
    fun testToolCallWithUnknownKeyReturnsInvalidArguments() = runBlocking {
        val req = """{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ide_find_class","arguments":{"query":"Foo","maxResult":5}}}"""
        val resp = handler.handleRequest(req)!!
        val result = Json.parseToJsonElement(resp).jsonObject["result"]!!.jsonObject
        assertEquals(true, result["isError"]!!.jsonPrimitive.boolean)
        val structured = result["structuredContent"]!!.jsonObject
        assertEquals("invalid_arguments", structured["error"]!!.jsonPrimitive.content)
        val problems = structured["violations"]!!.jsonArray.map { it.jsonObject["problem"]!!.jsonPrimitive.content }
        assertTrue(problems.contains("unknown_parameter"))
    }

    fun testToolCallWithValidArgsDoesNotTripValidation() = runBlocking {
        val req = """{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ide_index_status","arguments":{}}}"""
        val resp = handler.handleRequest(req)!!
        val result = Json.parseToJsonElement(resp).jsonObject["result"]!!.jsonObject
        val structured = result["structuredContent"]?.jsonObject
        assertTrue(structured == null || structured["error"]?.jsonPrimitive?.content != "invalid_arguments")
    }
}
