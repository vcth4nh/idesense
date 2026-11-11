package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.tools.intelligence.ExplainSymbolTool
import com.github.vcth4nh.idesense.tools.models.ExplainSymbolResult
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Platform tests for the case rule of the name anchors (#131). The classes are in a package,
 * so a plain name is no qualified name and the anchor uses the Go to Symbol search.
 */
class SymbolAnchorCaseTest : BasePlatformTestCase() {

    private val json = Json { ignoreUnknownKeys = true }

    override fun setUp() {
        super.setUp()
        myFixture.addFileToProject("demo/Handler.java", "package demo;\n\npublic class Handler {}\n")
        myFixture.addFileToProject("demo/Holder.java", "package demo;\n\npublic class Holder {\n    int handler;\n}\n")
        myFixture.addFileToProject("demo/Shape.java", "package demo;\n\npublic class Shape {}\n")
        IndexingTestUtil.waitUntilIndexesAreReady(project)
    }

    private fun explain(symbol: String): ExplainSymbolResult = runBlocking {
        val result = ExplainSymbolTool().execute(project, buildJsonObject { put("symbol", symbol) })
        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("The call must succeed: $text", result.isError)
        json.decodeFromString<ExplainSymbolResult>(text)
    }

    // The field `handler` is not the class `Handler`.
    fun testADeclarationWithTheCaseOfTheNameWins() {
        val result = explain("Handler")

        assertNull("One declaration has this case: ${result.message}", result.candidates)
        assertEquals("demo.Handler", result.symbol?.qualifiedName)
    }

    // A name of a language that ignores case must stay usable: with no declaration in the case
    // of the query, the anchor takes the declaration with another case.
    fun testANameWithNoDeclarationOfItsCaseIsFoundWithoutCase() {
        val result = explain("shape")

        assertNull("One declaration has this name: ${result.message}", result.candidates)
        assertEquals("demo.Shape", result.symbol?.qualifiedName)
    }
}
