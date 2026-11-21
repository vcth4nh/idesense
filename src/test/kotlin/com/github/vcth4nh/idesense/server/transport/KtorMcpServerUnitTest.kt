package com.github.vcth4nh.idesense.server.transport

import com.github.vcth4nh.idesense.McpConstants
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.JsonRpcHandler
import com.github.vcth4nh.idesense.testutil.LogRecorder
import com.github.vcth4nh.idesense.tools.ToolRegistry
import io.ktor.http.HttpStatusCode
import junit.framework.TestCase
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.job
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.BufferedReader
import java.io.InputStream
import java.net.ServerSocket
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse

class KtorMcpServerUnitTest : TestCase() {

    private val httpClient = HttpClient.newHttpClient()
    private val json = Json { ignoreUnknownKeys = true }
    private val mcpSessionIdHeader = "Mcp-Session-Id"

    private lateinit var toolRegistry: ToolRegistry
    private lateinit var coroutineScope: CoroutineScope
    private lateinit var sseSessionManager: KtorSseSessionManager
    private lateinit var server: KtorMcpServer
    private var port: Int = 0

    override fun setUp() {
        super.setUp()
        toolRegistry = ToolRegistry().also { it.registerBuiltInTools() }
        coroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        sseSessionManager = KtorSseSessionManager()
        port = findFreePort()
        server = createServer(port)
        assertEquals(KtorMcpServer.StartResult.Success, server.start())
    }

    override fun tearDown() {
        server.stop()
        coroutineScope.cancel()
        super.tearDown()
    }

    fun testStreamableInitializeEchoesCurrentProtocolVersion() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = initializeRequestBody("2025-11-25")
        )

        assertEquals(HttpStatusCode.OK.value, response.statusCode())
        assertFalse(
            "Streamable HTTP should not return an Mcp-Session-Id header in stateless mode",
            response.headers().firstValue(mcpSessionIdHeader).isPresent
        )

        val responseBody = json.parseToJsonElement(response.body()).jsonObject
        assertEquals(
            "2025-11-25",
            responseBody["result"]!!.jsonObject["protocolVersion"]!!.jsonPrimitive.content
        )
    }

    fun testLegacyPostInitializeReturns2024ProtocolVersion() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.MCP_ENDPOINT_PATH,
            body = initializeRequestBody("2024-11-05")
        )

        assertEquals(HttpStatusCode.OK.value, response.statusCode())

        val responseBody = json.parseToJsonElement(response.body()).jsonObject
        assertEquals(
            "2024-11-05",
            responseBody["result"]!!.jsonObject["protocolVersion"]!!.jsonPrimitive.content
        )
    }

    fun testStreamableBatchRequestsReturnJsonArray() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = """
                [
                  {"jsonrpc":"2.0","id":1,"method":"ping"},
                  {"jsonrpc":"2.0","id":2,"method":"ping"}
                ]
            """.trimIndent()
        )

        assertEquals(HttpStatusCode.OK.value, response.statusCode())

        val responseArray = json.parseToJsonElement(response.body()).jsonArray
        assertEquals(2, responseArray.size)
        assertEquals("1", responseArray[0].jsonObject["id"]!!.jsonPrimitive.content)
        assertEquals("2", responseArray[1].jsonObject["id"]!!.jsonPrimitive.content)
    }

    fun testStreamableScalarJsonReturnsInvalidRequestError() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = "1"
        )

        assertEquals(HttpStatusCode.BadRequest.value, response.statusCode())

        val responseBody = json.parseToJsonElement(response.body()).jsonObject
        assertEquals("-32600", responseBody["error"]!!.jsonObject["code"]!!.jsonPrimitive.content)
    }

    fun testStreamableInvalidNotificationReturnsInvalidRequestError() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = """{"jsonrpc":"2.0"}"""
        )

        assertEquals(HttpStatusCode.BadRequest.value, response.statusCode())

        val responseBody = json.parseToJsonElement(response.body()).jsonObject
        assertEquals("-32600", responseBody["error"]!!.jsonObject["code"]!!.jsonPrimitive.content)
    }

    fun testStreamableMixedBatchReturnsInvalidRequestError() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = """
                [
                  {"jsonrpc":"2.0","id":1,"method":"ping"},
                  {"jsonrpc":"2.0","id":1,"result":{}}
                ]
            """.trimIndent()
        )

        assertEquals(HttpStatusCode.BadRequest.value, response.statusCode())

        val responseBody = json.parseToJsonElement(response.body()).jsonObject
        assertEquals("-32600", responseBody["error"]!!.jsonObject["code"]!!.jsonPrimitive.content)
    }

    fun testStreamableNotificationBatchReturnsAcceptedWithoutResponseBody() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = """
                [
                  {"jsonrpc":"2.0","method":"ping"},
                  {"jsonrpc":"2.0","method":"notifications/initialized"}
                ]
            """.trimIndent()
        )

        assertEquals(HttpStatusCode.Accepted.value, response.statusCode())
        assertTrue("Expected empty body for notification batch", response.body().isEmpty())
    }

    fun testStreamableDeleteReturnsMethodNotAllowedInStatelessMode() {
        val response = sendRequest(
            method = "DELETE",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH
        )

        assertEquals(HttpStatusCode.MethodNotAllowed.value, response.statusCode())
        assertEquals("POST", response.headers().firstValue("allow").orElse(""))
    }

    fun testStreamableRequestSucceedsWithoutInitialize() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = """{"jsonrpc":"2.0","id":1,"method":"ping"}"""
        )

        assertEquals(HttpStatusCode.OK.value, response.statusCode())

        val responseBody = json.parseToJsonElement(response.body()).jsonObject
        assertEquals("1", responseBody["id"]!!.jsonPrimitive.content)
        assertNotNull(responseBody["result"])
    }

    fun testRejectsNonLocalOrigin() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = initializeRequestBody("2025-03-26"),
            headers = mapOf("Origin" to "https://evil.example")
        )

        assertEquals(HttpStatusCode.Forbidden.value, response.statusCode())
    }

    fun testAcceptsIpv6LoopbackOrigin() {
        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = initializeRequestBody("2025-03-26"),
            headers = mapOf("Origin" to "http://[::1]:3000")
        )

        assertEquals(HttpStatusCode.OK.value, response.statusCode())
    }

    fun testLegacySseHandshakeAdvertisesEndpointAndStreamsResponses() {
        val response = openSseStream(McpConstants.SSE_ENDPOINT_PATH)
        response.body().use {
            assertEquals(HttpStatusCode.OK.value, response.statusCode())
            assertTrue(
                response.headers().firstValue("content-type").orElse("").startsWith("text/event-stream")
            )

            val reader = it.bufferedReader()
            val endpointEvent = readSseEvent(reader)
            assertEquals("endpoint", endpointEvent.eventType())

            val endpointPath = endpointEvent.data()
            assertTrue(endpointPath.startsWith("${McpConstants.MCP_ENDPOINT_PATH}?${McpConstants.SESSION_ID_PARAM}="))

            val postResponse = sendRequest(
                method = "POST",
                path = endpointPath,
                body = """{"jsonrpc":"2.0","id":1,"method":"ping"}"""
            )

            assertEquals(HttpStatusCode.Accepted.value, postResponse.statusCode())

            val messageEvent = readSseEvent(reader)
            assertEquals("message", messageEvent.eventType())

            val messageBody = json.parseToJsonElement(messageEvent.data()).jsonObject
            assertEquals("1", messageBody["id"]!!.jsonPrimitive.content)
            assertNotNull(messageBody["result"])
        }
    }

    fun testStreamableRequestStillWorksAfterRestart() {
        server.stop()

        port = findFreePort()
        server = createServer(port)
        assertEquals(KtorMcpServer.StartResult.Success, server.start())

        val response = sendRequest(
            method = "POST",
            path = McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
            body = """{"jsonrpc":"2.0","id":1,"method":"ping"}"""
        )

        assertEquals(HttpStatusCode.OK.value, response.statusCode())
    }

    // A cancellation that leaves the JSON-RPC handler also leaves the request handlers of the
    // server: no log entry and no answer of the handler after it (#127). The cancellation comes
    // from the tool gate, because a unit test has no project for the call of a tool.
    fun testACancelledStreamableRequestGetsNoLogAndNoErrorAnswer() {
        useCancellingHandler()

        val log = LogRecorder()
        var response: HttpResponse<String>? = null
        log.record {
            response = sendRequest("POST", McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH, cancelledCallBody(id = 1))
        }

        assertEquals(emptyList<String>(), log.entries)
        assertFalse("No error answer after the cancellation: ${response!!.body()}", response!!.body().contains("-32603"))
    }

    fun testACancelledStreamableNotificationGetsNoAcceptedAnswer() {
        useCancellingHandler()

        val response = sendRequest("POST", McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH, cancelledCallBody(id = null))

        assertFalse(
            "No 202 Accepted after the cancellation",
            response.statusCode() == HttpStatusCode.Accepted.value
        )
    }

    fun testACancelledStreamableBatchMessageGetsNoLogAndNoErrorAnswer() {
        useCancellingHandler()

        val log = LogRecorder()
        var response: HttpResponse<String>? = null
        log.record {
            response = sendRequest(
                "POST",
                McpConstants.STREAMABLE_HTTP_ENDPOINT_PATH,
                "[${cancelledCallBody(id = 1)},{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"ping\"}]"
            )
        }

        assertEquals(emptyList<String>(), log.entries)
        assertFalse("No error answer after the cancellation: ${response!!.body()}", response!!.body().contains("-32603"))
    }

    fun testACancelledLegacyStatelessRequestGetsNoLogAndNoErrorAnswer() {
        useCancellingHandler()

        val log = LogRecorder()
        var response: HttpResponse<String>? = null
        log.record {
            response = sendRequest("POST", McpConstants.MCP_ENDPOINT_PATH, cancelledCallBody(id = 1))
        }

        assertEquals(emptyList<String>(), log.entries)
        assertFalse("No error answer after the cancellation: ${response!!.body()}", response!!.body().contains("-32603"))
    }

    fun testACancelledSseRequestGetsNoLogAndNoErrorEvent() {
        useCancellingHandler()

        val log = LogRecorder()
        log.record {
            val stream = openSseStream(McpConstants.SSE_ENDPOINT_PATH)
            stream.body().use {
                val reader = it.bufferedReader()
                val endpointPath = readSseEvent(reader).data()

                assertEquals(HttpStatusCode.Accepted.value, sendRequest("POST", endpointPath, cancelledCallBody(id = 1)).statusCode())
                val ping = """{"jsonrpc":"2.0","id":2,"method":"ping"}"""
                assertEquals(HttpStatusCode.Accepted.value, sendRequest("POST", endpointPath, ping).statusCode())

                val messageBody = json.parseToJsonElement(readSseEvent(reader).data()).jsonObject
                assertEquals("The first message must be the answer to the ping", "2", messageBody["id"]?.jsonPrimitive?.content)
            }
            runBlocking { coroutineScope.coroutineContext.job.children.forEach { it.join() } }
        }

        assertEquals(emptyList<String>(), log.entries)
    }

    private fun useCancellingHandler() {
        server.stop()
        port = findFreePort()
        server = createServer(port, JsonRpcHandler(toolRegistry, isToolEnabled = { throw CancellationException("cancelled") }))
        assertEquals(KtorMcpServer.StartResult.Success, server.start())
    }

    private fun cancelledCallBody(id: Int?): String {
        val idField = if (id == null) "" else "\"id\":$id,"
        return """{"jsonrpc":"2.0",$idField"method":"tools/call","params":{"name":"${ToolNames.INDEX_STATUS}","arguments":{}}}"""
    }

    private fun createServer(port: Int, jsonRpcHandler: JsonRpcHandler = JsonRpcHandler(toolRegistry)): KtorMcpServer {
        return KtorMcpServer(
            port = port,
            jsonRpcHandler = jsonRpcHandler,
            sseSessionManager = sseSessionManager,
            coroutineScope = coroutineScope
        )
    }

    private fun sendRequest(
        method: String,
        path: String,
        body: String? = null,
        headers: Map<String, String> = emptyMap()
    ): HttpResponse<String> {
        val builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:$port$path"))
            .header("Accept", "application/json, text/event-stream")

        headers.forEach { (name, value) -> builder.header(name, value) }

        if (body != null) {
            builder.header("Content-Type", "application/json")
        }

        when (method) {
            "GET" -> builder.GET()
            "POST" -> builder.POST(HttpRequest.BodyPublishers.ofString(body ?: ""))
            "DELETE" -> builder.DELETE()
            else -> error("Unsupported method: $method")
        }

        return httpClient.send(builder.build(), HttpResponse.BodyHandlers.ofString())
    }

    private fun openSseStream(
        path: String,
        headers: Map<String, String> = emptyMap()
    ): HttpResponse<InputStream> {
        val builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:$port$path"))
            .header("Accept", "text/event-stream")
            .GET()

        headers.forEach { (name, value) -> builder.header(name, value) }

        return httpClient.send(builder.build(), HttpResponse.BodyHandlers.ofInputStream())
    }

    private fun readSseEvent(reader: BufferedReader, timeoutMillis: Long = 5_000): List<String> {
        val deadline = System.currentTimeMillis() + timeoutMillis
        while (!reader.ready() && System.currentTimeMillis() < deadline) {
            Thread.sleep(10)
        }

        assertTrue("Timed out waiting for SSE event", reader.ready())

        val lines = mutableListOf<String>()
        while (true) {
            val line = reader.readLine() ?: break
            if (line.isEmpty()) {
                if (lines.isNotEmpty()) {
                    break
                }
                continue
            }
            lines += line
        }

        return lines
    }

    private fun List<String>.eventType(): String = first { it.startsWith("event: ") }.substringAfter("event: ")

    private fun List<String>.data(): String = filter { it.startsWith("data: ") }
        .joinToString("\n") { it.substringAfter("data: ") }

    private fun initializeRequestBody(protocolVersion: String) = """
        {
          "jsonrpc": "2.0",
          "id": 1,
          "method": "initialize",
          "params": {
            "protocolVersion": "$protocolVersion",
            "clientInfo": {
              "name": "test-client",
              "version": "1.0.0"
            }
          }
        }
    """.trimIndent()

    private fun findFreePort(): Int = ServerSocket(0).use { it.localPort }
}
