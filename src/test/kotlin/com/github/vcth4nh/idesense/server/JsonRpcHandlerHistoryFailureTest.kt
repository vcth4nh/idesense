package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.constants.JsonRpcMethods
import com.github.vcth4nh.idesense.history.CommandStatus
import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.server.models.JsonRpcRequest
import com.github.vcth4nh.idesense.server.models.JsonRpcResponse
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.testutil.LogRecorder
import com.github.vcth4nh.idesense.tools.McpTool
import com.github.vcth4nh.idesense.tools.ToolRegistry
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Job
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
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

    // A cancelled call leaves the handler as a cancellation: no log entry, no history update (#127).
    fun testACancelledToolCallGetsNoLogAndNoHistoryUpdate() {
        val started = CompletableDeferred<Unit>()
        val updates = mutableListOf<CommandStatus>()
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(SuspendingTool(started)) },
            recordHistory = { _, _ -> },
            updateHistory = { _, _, status, _, _ -> updates += status }
        )

        val log = LogRecorder()
        var job: Job? = null
        log.record {
            runBlocking {
                job = launch { handler.handleRequest(toolCallRequest(SuspendingTool.NAME)) }
                started.await()
                job!!.cancelAndJoin()
            }
        }

        assertTrue("The call must end as cancelled", job!!.isCancelled)
        assertEquals("No history update after the cancellation", emptyList<CommandStatus>(), updates)
        assertEquals(emptyList<String>(), log.entries)
    }

    // A cancellation in the record of the history stops the call before the tool runs (#127).
    fun testACancellationOfTheHistoryRecordStopsTheCall() {
        val tool = TestTool()
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(tool) },
            recordHistory = { _, _ -> throw ProcessCanceledException() }
        )

        val log = LogRecorder()
        val thrown = log.recordCancellation { handler.handleRequest(toolCallRequest(TestTool.NAME)) }

        assertTrue("The cancellation must leave handleRequest, got $thrown", thrown is ProcessCanceledException)
        assertFalse("The tool must not run after the cancellation", tool.executed)
        assertEquals(emptyList<String>(), log.entries)
    }

    // A cancellation in the update of the history leaves the handler with no log entry (#127).
    fun testACancellationOfTheHistoryUpdateLeavesTheCall() {
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(TestTool()) },
            recordHistory = { _, _ -> },
            updateHistory = { _, _, _, _, _ -> throw ProcessCanceledException() }
        )

        val log = LogRecorder()
        val thrown = log.recordCancellation { handler.handleRequest(toolCallRequest(TestTool.NAME)) }

        assertTrue("The cancellation must leave handleRequest, got $thrown", thrown is ProcessCanceledException)
        assertEquals(emptyList<String>(), log.entries)
    }

    /** Runs [call] in [LogRecorder.record] and gives the cancellation that leaves it, else null. */
    private fun LogRecorder.recordCancellation(call: suspend () -> String?): Throwable? {
        var thrown: Throwable? = null
        record {
            try {
                runBlocking { call() }
            } catch (e: CancellationException) {
                thrown = e
            }
        }
        return thrown
    }

    private fun toolCallRequest(toolName: String): String = json.encodeToString(
        JsonRpcRequest.serializer(),
        JsonRpcRequest(
            id = JsonPrimitive(1),
            method = JsonRpcMethods.TOOLS_CALL,
            params = buildJsonObject {
                put("name", toolName)
                put("arguments", buildJsonObject { })
            }
        )
    )

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
        var executed = false

        override suspend fun execute(
            project: com.intellij.openapi.project.Project,
            arguments: JsonObject
        ): ToolCallResult {
            executed = true
            return ToolCallResult(
                content = listOf(ContentBlock.Text("ok"))
            )
        }

        companion object {
            const val NAME = "ide_test_history_failure"
        }
    }

    /** A tool that completes [started] and then waits until its call is cancelled. */
    private class SuspendingTool(private val started: CompletableDeferred<Unit>) : McpTool {
        override val name: String = NAME
        override val description: String = "Test tool that waits for its cancellation"
        override val inputSchema: JsonObject = buildJsonObject {
            put("type", "object")
        }

        override suspend fun execute(
            project: com.intellij.openapi.project.Project,
            arguments: JsonObject
        ): ToolCallResult {
            started.complete(Unit)
            awaitCancellation()
        }

        companion object {
            const val NAME = "ide_test_cancelled_call"
        }
    }
}
