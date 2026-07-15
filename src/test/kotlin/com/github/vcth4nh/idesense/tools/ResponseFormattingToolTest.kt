package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.settings.McpSettings
import com.github.vcth4nh.idesense.tools.navigation.FindFileTool
import com.github.vcth4nh.idesense.tools.navigation.SearchTextTool
import com.github.vcth4nh.idesense.tools.project.GetIndexStatusTool
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

class ResponseFormattingToolTest : BasePlatformTestCase() {

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    private lateinit var settings: McpSettings
    private lateinit var originalFormat: McpSettings.ResponseFormat

    override fun setUp() {
        super.setUp()
        settings = McpSettings.getInstance()
        originalFormat = settings.responseFormat
    }

    override fun tearDown() {
        try {
            settings.responseFormat = originalFormat
        } finally {
            super.tearDown()
        }
    }

    fun testStructuredSuccessUsesJsonByDefault() = runBlocking {
        settings.responseFormat = McpSettings.ResponseFormat.JSON
        val tool = GetIndexStatusTool()

        val result = tool.execute(project, buildJsonObject { })
        val text = (result.content.single() as ContentBlock.Text).text

        val parsed = json.parseToJsonElement(text).jsonObject
        assertNotNull(parsed["isDumbMode"])
    }

    fun testStructuredSuccessUsesToonWhenSelected() = runBlocking {
        settings.responseFormat = McpSettings.ResponseFormat.TOON
        val tool = GetIndexStatusTool()

        val result = tool.execute(project, buildJsonObject { })
        val text = (result.content.single() as ContentBlock.Text).text

        assertFalse("TOON output should not be raw JSON", text.trim().startsWith("{"))
        assertTrue(text.contains("isDumbMode:"))
    }

    fun testStructuredErrorsUseToonWhenSelected() = runBlocking {
        settings.responseFormat = McpSettings.ResponseFormat.TOON
        val tool = FindFileTool()

        val result = tool.execute(project, buildJsonObject {
            put("query", "Foo")
            put("scope", "not_a_scope")
        })
        val text = (result.content.single() as ContentBlock.Text).text

        assertTrue(result.isError)
        assertFalse("Structured TOON error should not be raw JSON", text.trim().startsWith("{"))
        assertTrue(text.contains("error: invalid_scope"))
        assertTrue(text.contains("parameter: scope"))
    }

    fun testPlainTextErrorsRemainPlainTextInToonMode() = runBlocking {
        settings.responseFormat = McpSettings.ResponseFormat.TOON
        val tool = SearchTextTool()

        // A generic tool_error (error + message only) — distinct from the rich structured
        // invalid_arguments/invalid_scope shapes, which carry violations/supportedValues.
        val result = tool.execute(project, buildJsonObject { put("query", "") })
        val text = (result.content.single() as ContentBlock.Text).text

        assertTrue(result.isError)
        assertTrue(text.contains("Query cannot be empty"))
        assertFalse("Generic errors should not carry structured detail fields", text.contains("violations"))
    }
}
