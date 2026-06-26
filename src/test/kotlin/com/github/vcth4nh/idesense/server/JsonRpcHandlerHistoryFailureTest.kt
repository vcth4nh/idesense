package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.constants.JsonRpcMethods
import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.server.models.JsonRpcRequest
import com.github.vcth4nh.idesense.server.models.JsonRpcResponse
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.McpTool
import com.github.vcth4nh.idesense.tools.ToolRegistry
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class JsonRpcHandlerHistoryFailureTest : BasePlatformTestCase() {

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    fun testToolCallStillSucceedsWhenHistoryRecordingFails() = runBlocking {
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(TestTool()) },
            recordHistory = { _, _ -> error("history record failure") }
        )

        val response = executeTestToolCall(handler)

        assertNull("Tool call should not produce JSON-RPC error", response.error)

        val result = json.decodeFromJsonElement(ToolCallResult.serializer(), response.result!!)
        assertFalse("Tool result should still succeed", result.isError)
        assertEquals("ok", (result.content.single() as ContentBlock.Text).text)
    }

    fun testToolCallStillSucceedsWhenHistoryUpdateFails() = runBlocking {
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(TestTool()) },
            recordHistory = { _, _ -> },
            updateHistory = { _, _, _, _, _ -> error("history update failure") }
        )

        val response = executeTestToolCall(handler)

        assertNull("Tool call should not produce JSON-RPC error", response.error)

        val result = json.decodeFromJsonElement(ToolCallResult.serializer(), response.result!!)
        assertFalse("Tool result should still succeed", result.isError)
        assertEquals("ok", (result.content.single() as ContentBlock.Text).text)
    }

    private suspend fun executeTestToolCall(handler: JsonRpcHandler): JsonRpcResponse {
        val request = JsonRpcRequest(
            id = JsonPrimitive(1),
            method = JsonRpcMethods.TOOLS_CALL,
            params = buildJsonObject {
                put("name", TestTool.NAME)
                put("arguments", buildJsonObject { })
            }
        )

        val responseJson = handler.handleRequest(json.encodeToString(JsonRpcRequest.serializer(), request))
        return json.decodeFromString(responseJson!!)
    }

    private class TestTool : McpTool {
        override val name: String = NAME
        override val description: String = "Test tool for history failure regression coverage"
        override val inputSchema: JsonObject = buildJsonObject {
            put("type", "object")
        }

        override suspend fun execute(
            project: com.intellij.openapi.project.Project,
            arguments: JsonObject
        ): ToolCallResult {
            return ToolCallResult(
                content = listOf(ContentBlock.Text("ok"))
            )
        }

        companion object {
            const val NAME = "ide_test_history_failure"
        }
    }
}
