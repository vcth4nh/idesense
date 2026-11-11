package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.tools.models.SearchTextResult
import com.github.vcth4nh.idesense.tools.models.TextMatch
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class SearchTextToolContextTest : BasePlatformTestCase() {

    private val json = Json { ignoreUnknownKeys = true }

    private val labelOfContext = mapOf("code" to "CODE", "comments" to "COMMENT", "strings" to "STRING_LITERAL")

    private fun search(context: String?): Set<TextMatch> = runBlocking {
        val result = SearchTextTool().execute(project, buildJsonObject {
            put("query", "zorbleword")
            if (context != null) put("context", context)
        })
        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("The search must succeed: $text", result.isError)
        json.decodeFromString<SearchTextResult>(text).matches.toSet()
    }

    // The word index puts plain text under its own occurrence mask, and the label of such a
    // match is CODE. A search with the index mask of one context lost these matches (#133).
    fun testEachMatchIsInTheFilteredResultOfItsLabel() {
        myFixture.addFileToProject("notes.txt", "zorbleword in plain text\n")
        myFixture.addFileToProject(
            "Sample.java",
            """
            class Sample {
                // zorbleword in a comment
                String text = "zorbleword in a string";
                int zorbleword = 1;
                int other = zorbleword; // zorbleword in code and in a comment
            }
            """.trimIndent()
        )
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        val all = search(null)

        assertEquals("One match for each of the five lines: $all", 5, all.size)
        assertEquals(
            "The plain text match has the label CODE",
            listOf("CODE"),
            all.filter { it.file.endsWith("notes.txt") }.map { it.contextType }
        )
        for ((context, label) in labelOfContext) {
            val filtered = search(context)
            assertTrue(
                "The result of '$context' holds each match with the label $label: $filtered",
                filtered.containsAll(all.filter { it.contextType == label })
            )
            assertEquals("The result of '$context' holds only the label $label", setOf(label), filtered.map { it.contextType }.toSet())
        }
    }

    // A result has one match for each line. The line with the word in code and in a comment has
    // its code match in the result of all, and its comment match only in the result of comments.
    fun testALineWithTheWordInTwoContextsIsInTheResultOfEachContext() {
        myFixture.addFileToProject(
            "Sample.java",
            """
            class Sample {
                int other = zorbleword; // zorbleword in code and in a comment
            }
            """.trimIndent()
        )
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        assertEquals(listOf("CODE"), search(null).map { it.contextType })
        assertEquals(listOf("CODE"), search("code").map { it.contextType })
        assertEquals(listOf("COMMENT"), search("comments").map { it.contextType })
        assertEquals(emptyList<String>(), search("strings").map { it.contextType })
    }
}
