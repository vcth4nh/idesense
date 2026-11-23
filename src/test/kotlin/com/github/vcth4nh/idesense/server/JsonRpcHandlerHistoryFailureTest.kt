package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.constants.JsonRpcMethods
import com.github.vcth4nh.idesense.history.CommandHistoryService
import com.github.vcth4nh.idesense.history.CommandStatus
import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.server.models.JsonRpcRequest
import com.github.vcth4nh.idesense.server.models.JsonRpcResponse
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.testutil.LogRecorder
import com.github.vcth4nh.idesense.tools.McpTool
import com.github.vcth4nh.idesense.tools.ToolRegistry
import com.intellij.ide.startup.ServiceNotReadyException
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.serviceContainer.AlreadyDisposedException
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
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

    // A cancelled call leaves the handler as a cancellation with no log entry (#127). Its history
    // entry gets the status CANCELLED, with a text and the duration (#284).
    fun testACancelledToolCallGetsNoLogAndTheStatusCancelled() {
        val started = CompletableDeferred<Unit>()
        val updates = mutableListOf<CommandStatus>()
        val texts = mutableListOf<String?>()
        val durations = mutableListOf<Long?>()
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(SuspendingTool(started)) },
            recordHistory = { _, _ -> },
            updateHistory = { _, _, status, result, duration ->
                updates += status
                texts += result
                durations += duration
            }
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
        assertEquals(listOf(CommandStatus.CANCELLED), updates)
        assertFalse("The entry needs a text: $texts", texts.single().isNullOrBlank())
        assertNotNull("The entry needs the duration", durations.single())
        assertEquals(emptyList<String>(), log.entries)
    }

    // A cancellation from the IDE while the call is active (an index that is not ready): the
    // client gets the same answer as for another failure, the history gets its update, and the
    // log gets no error and no throwable (#127).
    fun testACancellationInAnActiveToolCallGetsTheErrorAnswer() {
        val updates = mutableListOf<Pair<CommandStatus, String?>>()
        fun handlerFor(failure: Exception) = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(TestTool(failure)) },
            recordHistory = { _, _ -> },
            updateHistory = { _, _, status, result, _ -> updates += status to result }
        )

        val otherFailure = LogRecorder()
        val answerToAnotherFailure = otherFailure.recordCall(handlerFor(IllegalStateException("Index is not ready")))
        updates.clear()

        val log = LogRecorder()
        val answer = log.recordCall(handlerFor(ServiceNotReadyException("Index is not ready")))

        assertNotNull("The client must get an answer", answer)
        assertEquals(answerToAnotherFailure, answer)
        assertEquals(listOf(CommandStatus.ERROR to "Index is not ready"), updates)
        assertEquals(emptyList<String>(), log.errorsAndThrowables())
        assertTrue("One line about the cancellation: ${log.entries}", log.entries.single().contains("ServiceNotReadyException: Index is not ready"))
    }

    // A cancellation from the IDE in the record of the history while the call is active (a
    // disposed service): the record does not occur, and the tool runs and answers (#127).
    fun testACancellationOfTheHistoryRecordInAnActiveCallSkipsTheRecord() {
        val tool = TestTool()
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(tool) },
            recordHistory = { _, _ -> throw AlreadyDisposedException("Already disposed") }
        )

        val log = LogRecorder()
        val answer = log.recordCall(handler)

        assertTrue("The tool must run", tool.executed)
        assertEquals("ok", answer?.let(::resultText))
        assertEquals(emptyList<String>(), log.errorsAndThrowables())
        assertTrue("One line about the cancellation: ${log.entries}", log.entries.single().contains("AlreadyDisposedException: Already disposed"))
    }

    // A cancellation of the call in the record of the history stops the call before the tool
    // runs, with no log entry (#127).
    fun testACancellationOfTheCallInTheHistoryRecordLeavesTheCall() {
        val tool = TestTool()
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(tool) },
            recordHistory = { _, _ ->
                call!!.cancel()
                throw ProcessCanceledException()
            }
        )

        val log = LogRecorder()
        val answer = log.recordCall(handler)

        assertTrue("The call must end as cancelled", call!!.isCancelled)
        assertNull("No answer after the cancellation of the call", answer)
        assertFalse("The tool must not run after the cancellation", tool.executed)
        assertEquals(emptyList<String>(), log.entries)
    }

    // A cancellation from the IDE in the update of the history while the call is active: the
    // update does not occur, and the client gets the answer of the tool (#127).
    fun testACancellationOfTheHistoryUpdateInAnActiveCallSkipsTheUpdate() {
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(TestTool()) },
            recordHistory = { _, _ -> },
            updateHistory = { _, _, _, _, _ -> throw AlreadyDisposedException("Already disposed") }
        )

        val log = LogRecorder()
        val answer = log.recordCall(handler)

        assertEquals("ok", answer?.let(::resultText))
        assertEquals(emptyList<String>(), log.errorsAndThrowables())
        assertTrue("One line about the cancellation: ${log.entries}", log.entries.single().contains("AlreadyDisposedException: Already disposed"))
    }

    // A cancellation of the call in the update of the history leaves the call with no answer and
    // no log entry (#127).
    fun testACancellationOfTheCallInTheHistoryUpdateLeavesTheCall() {
        val handler = JsonRpcHandler(
            toolRegistry = ToolRegistry().apply { register(TestTool()) },
            recordHistory = { _, _ -> },
            updateHistory = { _, _, _, _, _ ->
                call!!.cancel()
                throw ProcessCanceledException()
            }
        )

        val log = LogRecorder()
        val answer = log.recordCall(handler)

        assertTrue("The call must end as cancelled", call!!.isCancelled)
        assertNull("No answer after the cancellation of the call", answer)
        assertEquals(emptyList<String>(), log.entries)
    }

    // A time limit of a service of the IDE ends inside an active call, as the withTimeout of the
    // TypeScript service of WebStorm does: the error ide_service_timeout with a hint to call again,
    // one warning and no error in the log, and the status ERROR with the same text (#333). The
    // second call has the shape of the log of #333: a ProcessCanceledException around the timeout.
    fun testATimeoutOfAServiceOfTheIdeGetsIdeServiceTimeout() {
        for (wrap in listOf<(TimeoutCancellationException) -> Exception>({ it }, { ProcessCanceledException(it) })) {
            val updates = mutableListOf<Pair<CommandStatus, String?>>()
            val handler = JsonRpcHandler(
                toolRegistry = ToolRegistry().apply { register(ServiceTimeoutTool(wrap)) },
                recordHistory = { _, _ -> },
                updateHistory = { _, _, status, result, _ -> updates += status to result }
            )

            val log = LogRecorder()
            val answer = log.recordCall(handler, ServiceTimeoutTool.NAME)

            val body = json.parseToJsonElement(resultText(answer!!)).jsonObject
            assertEquals(answer, "ide_service_timeout", body["error"]?.jsonPrimitive?.content)
            val message = body["message"]!!.jsonPrimitive.content
            assertTrue(message, message.startsWith("A service of the IDE did not answer in its time limit"))
            assertTrue(message, message.endsWith("Try again later."))
            assertEquals(listOf(CommandStatus.ERROR to message), updates)
            assertEquals(emptyList<String>(), log.errorsAndThrowables())
            assertTrue("One warning with the tool name: ${log.entries}", log.entries.single().contains(ServiceTimeoutTool.NAME))
        }
    }

    // A timeout in a call whose coroutine is cancelled takes the path of the cancellation of the
    // call: no answer, no log entry, the status CANCELLED (#284, #333). The second call has the
    // timeout inside an exception that is no cancellation.
    fun testATimeoutInACancelledCallTakesTheCancellationPath() {
        for (wrap in listOf<(TimeoutCancellationException) -> Exception>({ it }, { RuntimeException(it) })) {
            val updates = mutableListOf<CommandStatus>()
            val handler = JsonRpcHandler(
                toolRegistry = ToolRegistry().apply {
                    register(ServiceTimeoutTool { timeout -> call!!.cancel(); wrap(timeout) })
                },
                recordHistory = { _, _ -> },
                updateHistory = { _, _, status, _, _ -> updates += status }
            )

            val log = LogRecorder()
            val answer = log.recordCall(handler, ServiceTimeoutTool.NAME)

            assertTrue("The call must end as cancelled", call!!.isCancelled)
            assertNull("No answer after the cancellation of the call", answer)
            assertEquals(listOf(CommandStatus.CANCELLED), updates)
            assertEquals(emptyList<String>(), log.entries)
        }
    }

    // The real history of the project gets CANCELLED for a cancelled call (#284). The update runs
    // in the cancelled coroutine, so a suspension point on that path would leave the entry PENDING.
    fun testACancelledToolCallGetsTheStatusCancelledInTheRealHistory() {
        val history = CommandHistoryService.getInstance(project)
        history.clearHistory()
        val started = CompletableDeferred<Unit>()
        val handler = JsonRpcHandler(toolRegistry = ToolRegistry().apply { register(SuspendingTool(started)) })

        runBlocking {
            val job = launch { handler.handleRequest(toolCallRequest(SuspendingTool.NAME)) }
            started.await()
            job.cancelAndJoin()
        }

        val entry = history.entries.single { it.toolName == SuspendingTool.NAME }
        assertEquals(CommandStatus.CANCELLED, entry.status)
        assertNotNull("The entry needs the duration", entry.durationMs)
    }

    /** The job of the call in [recordCall]; a test lambda cancels it to cancel the call. */
    private var call: Job? = null

    /**
     * Runs a call of the tool [toolName] as the job [call] in [LogRecorder.record]. Gives the
     * answer, or null when the call ends with no answer.
     */
    private fun LogRecorder.recordCall(handler: JsonRpcHandler, toolName: String = TestTool.NAME): String? {
        var answer: String? = null
        record {
            runBlocking {
                call = launch { answer = handler.handleRequest(toolCallRequest(toolName)) }
                call!!.join()
            }
        }
        return answer
    }

    private fun resultText(answer: String): String {
        val response = json.decodeFromString<JsonRpcResponse>(answer)
        val result = json.decodeFromJsonElement(ToolCallResult.serializer(), response.result!!)
        return (result.content.single() as ContentBlock.Text).text
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

    /** A tool that answers "ok", or that throws [failure] when it is not null. */
    private class TestTool(private val failure: Exception? = null) : McpTool {
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
            failure?.let { throw it }
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

    /**
     * A tool whose `withTimeout` ends inside the call, as `CommandQueue.awaitAnswerCancellable` of
     * the JavaScript plugin does. It throws what [wrap] makes of the timeout.
     */
    private class ServiceTimeoutTool(private val wrap: (TimeoutCancellationException) -> Exception) : McpTool {
        override val name: String = NAME
        override val description: String = "Test tool whose wait for a service ends at a time limit"
        override val inputSchema: JsonObject = buildJsonObject {
            put("type", "object")
        }

        override suspend fun execute(
            project: com.intellij.openapi.project.Project,
            arguments: JsonObject
        ): ToolCallResult = try {
            withTimeout(1) { delay(10_000) }
            error("The time limit must end the wait")
        } catch (timeout: TimeoutCancellationException) {
            throw wrap(timeout)
        }

        companion object {
            const val NAME = "ide_test_service_timeout"
        }
    }
}
