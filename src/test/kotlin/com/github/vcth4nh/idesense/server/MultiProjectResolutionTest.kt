package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.models.JsonRpcRequest
import com.github.vcth4nh.idesense.server.models.JsonRpcResponse
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.ToolRegistry
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Platform-dependent tests for multi-project resolution.
 * For schema validation tests that don't need the platform, see ToolsUnitTest.
 */
class MultiProjectResolutionTest : BasePlatformTestCase() {

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

    fun testToolCallWithSingleProject() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(1),
            method = "tools/call",
            params = buildJsonObject {
                put("name", ToolNames.INDEX_STATUS)
                put("arguments", buildJsonObject { })
            }
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNull("Single project should not return JSON-RPC error", response.error)
        assertNotNull("Should return result", response.result)

        val result = json.decodeFromJsonElement(ToolCallResult.serializer(), response.result!!)
        assertFalse("Tool should succeed with single project", result.isError)
    }

    fun testToolCallWithExplicitProjectPath() = runBlocking {
        val projectPath = project.basePath

        val request = JsonRpcRequest(
            id = JsonPrimitive(2),
            method = "tools/call",
            params = buildJsonObject {
                put("name", ToolNames.INDEX_STATUS)
                put("arguments", buildJsonObject {
                    put("project_path", projectPath ?: "")
                })
            }
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNull("Explicit project_path should not return JSON-RPC error", response.error)
        assertNotNull("Should return result", response.result)

        val result = json.decodeFromJsonElement(ToolCallResult.serializer(), response.result!!)
        assertFalse("Tool should succeed with explicit project_path", result.isError)
    }

    fun testToolCallWithInvalidProjectPath() = runBlocking {
        val request = JsonRpcRequest(
            id = JsonPrimitive(3),
            method = "tools/call",
            params = buildJsonObject {
                put("name", ToolNames.INDEX_STATUS)
                put("arguments", buildJsonObject {
                    put("project_path", "/non/existent/project/path")
                })
            }
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        val response = json.decodeFromString<JsonRpcResponse>(responseJson!!)

        assertNull("Should not return JSON-RPC level error", response.error)
        assertNotNull("Should return result", response.result)

        val result = json.decodeFromJsonElement(ToolCallResult.serializer(), response.result!!)
        assertTrue("Tool should return error for invalid project_path", result.isError)

        val content = result.content.firstOrNull()
        assertNotNull("Should have error content", content)

        val errorJson = json.parseToJsonElement(
            (content as? com.github.vcth4nh.idesense.server.models.ContentBlock.Text)?.text ?: ""
        ).jsonObject

        assertEquals("project_not_found", errorJson["error"]?.jsonPrimitive?.content)
        assertNotNull("Should include available_projects", errorJson["available_projects"])
    }
}
