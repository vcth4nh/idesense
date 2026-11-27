package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.server.PaginationService
import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.tools.models.SearchTextResult
import com.github.vcth4nh.idesense.tools.models.TextMatch
import com.intellij.find.FindManager
import com.intellij.find.FindModel
import com.intellij.lang.injection.InjectedLanguageManager
import com.intellij.openapi.application.ReadAction
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiFile
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class SearchTextToolContextTest : BasePlatformTestCase() {

    private val json = Json { ignoreUnknownKeys = true }

    private val labelOfContext = mapOf("code" to "CODE", "comments" to "COMMENT", "strings" to "STRING_LITERAL")

    private fun call(arguments: JsonObject): SearchTextResult = runBlocking {
        val result = SearchTextTool().execute(project, arguments)
        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("The search must succeed: $text", result.isError)
        json.decodeFromString<SearchTextResult>(text)
    }

    private fun search(context: String?, query: String = "zorbleword", caseSensitive: Boolean = true): Set<TextMatch> =
        call(buildJsonObject {
            put("query", query)
            if (context != null) put("context", context)
            if (!caseSensitive) put("caseSensitive", false)
        }).matches.toSet()

    private fun labelsByLine(query: String = "zorbleword"): Map<String, String> =
        search(null, query).associate { "${it.file}:${it.line}" to it.contextType }

    /**
     * The lines that the per-file matcher of Find in Files finds with [context], with "Match
     * case" and "Words" on: the loop of `FindInProjectUtil.processSomeOccurrencesInFile`.
     */
    private fun findInFilesLines(files: List<PsiFile>, query: String, context: FindModel.SearchContext): Set<String> =
        ReadAction.compute<Set<String>, RuntimeException> {
            val findManager = FindManager.getInstance(project)
            val model = FindModel().apply {
                stringToFind = query
                isCaseSensitive = true
                isWholeWordsOnly = true
                searchContext = context
            }
            val lines = mutableSetOf<String>()
            for (file in files) {
                val document = PsiDocumentManager.getInstance(project).getDocument(file)!!
                val text = document.charsSequence
                var offset = 0
                while (offset < text.length) {
                    val result = findManager.findString(text, offset, model, file.virtualFile)
                    if (!result.isStringFound) break
                    lines += "${file.name}:${document.getLineNumber(result.startOffset) + 1}"
                    val previous = offset
                    offset = result.endOffset
                    if (previous == offset || offset == result.startOffset) offset++
                }
            }
            lines
        }

    private fun addJavaSample(): PsiFile = myFixture.addFileToProject(
        "Sample.java",
        """
        class Sample {
            // zorbleword in a line comment
            /* zorbleword in a block comment */
            /** zorbleword in a doc comment */
            String text = "zorbleword in a string";
            String block = ${"\"\"\""}
                zorbleword in a text block
                ${"\"\"\""};
            int zorbleword = 1;
            int answer() { return 42; }
        }
        """.trimIndent()
    )

    private fun addMarkdownSample(): PsiFile = myFixture.addFileToProject(
        "notes.md",
        """
        # Notes

        Plain zorbleword text.

        Inline `zorbleword` span.

        ```kotlin
        val zorbleword = 1
        ```

        ```
        zorbleword in a fence with no info string
        ```
        """.trimIndent()
    )

    private fun addKotlinSample(): PsiFile = myFixture.addFileToProject(
        "Greeting.kt",
        """
        /**
         * zorbleword in a KDoc comment
         */
        fun greet(name: String) = "zorbleword, ${'$'}name"
        """.trimIndent()
    )

    // The label follows the filters of Find in Files (#144). A number literal is no string: the
    // labels by substrings of the type names gave STRING_LITERAL to the type INTEGER_LITERAL.
    fun testJavaLabelsFollowFindInFiles() {
        addJavaSample()
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        assertEquals(
            mapOf(
                "Sample.java:2" to "COMMENT",
                "Sample.java:3" to "COMMENT",
                "Sample.java:4" to "COMMENT",
                "Sample.java:5" to "STRING_LITERAL",
                "Sample.java:7" to "STRING_LITERAL",
                "Sample.java:9" to "CODE",
            ),
            labelsByLine()
        )
        assertEquals(mapOf("Sample.java:10" to "CODE"), labelsByLine("42"))
    }

    // Find in Files takes the lines of a Markdown code fence as string literals, also with no info
    // string, and a backtick span as neither a comment nor a string literal (#144).
    fun testMarkdownLabelsFollowFindInFiles() {
        addMarkdownSample()
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        assertEquals(
            mapOf(
                "notes.md:3" to "CODE",
                "notes.md:5" to "CODE",
                "notes.md:8" to "STRING_LITERAL",
                "notes.md:12" to "STRING_LITERAL",
            ),
            labelsByLine()
        )
        assertEquals(setOf(8, 12), search("strings").map { it.line }.toSet())
        assertEquals(setOf(3, 5), search("code").map { it.line }.toSet())
    }

    fun testKotlinLabelsFollowFindInFiles() {
        addKotlinSample()
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        assertEquals(mapOf("Greeting.kt:2" to "COMMENT", "Greeting.kt:4" to "STRING_LITERAL"), labelsByLine())
    }

    // Each line of the samples has one occurrence. The three filtered results together are the
    // result of "all", and "code" shares no match with the two others. A match can be in the
    // results of "comments" and of "strings" (a match that both filters of the IDE find), so
    // the test does not ask these two to be disjoint.
    fun testTheThreeContextsCoverAllAndCodeIsApart() {
        addJavaSample()
        addMarkdownSample()
        addKotlinSample()
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        val all = search(null)
        val code = search("code")
        val comments = search("comments")
        val strings = search("strings")
        assertEquals(all, code + comments + strings)
        assertEquals(emptySet<TextMatch>(), code intersect comments)
        assertEquals(emptySet<TextMatch>(), code intersect strings)
    }

    /**
     * The differential test: for each `context` value, the lines of the tool are the lines of the
     * per-file matcher of Find in Files. For "code" the matcher runs with
     * EXCEPT_COMMENTS_AND_STRING_LITERALS and for "all" with ANY. The predicate of the IDE for
     * "Except" (`FindExceptCommentsOrLiteralsData`) and the plain search are other paths of the
     * platform than the code of the tool, so these two are real comparisons. For "comments" and
     * "strings" the matcher of the test is the matcher of the tool, so the test pins the wiring.
     */
    private fun assertEachContextGivesTheLinesOfTheIde(files: List<PsiFile>, query: String) {
        val filterOfContext = mapOf(
            "comments" to FindModel.SearchContext.IN_COMMENTS,
            "strings" to FindModel.SearchContext.IN_STRING_LITERALS,
            "code" to FindModel.SearchContext.EXCEPT_COMMENTS_AND_STRING_LITERALS,
            null to FindModel.SearchContext.ANY,
        )
        for ((context, filter) in filterOfContext) {
            assertEquals(
                "The lines of '$context' for '$query'",
                findInFilesLines(files, query, filter),
                search(context, query).map { "${it.file}:${it.line}" }.toSet()
            )
        }
    }

    fun testEachContextGivesTheLinesOfTheFindInFilesFilter() {
        val files = listOf(addJavaSample(), addMarkdownSample(), addKotlinSample())
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        for (filter in listOf(
            FindModel.SearchContext.IN_COMMENTS,
            FindModel.SearchContext.IN_STRING_LITERALS,
            FindModel.SearchContext.EXCEPT_COMMENTS_AND_STRING_LITERALS,
        )) {
            assertFalse("The filter $filter must find a line", findInFilesLines(files, "zorbleword", filter).isEmpty())
        }
        assertEachContextGivesTheLinesOfTheIde(files, "zorbleword")
    }

    private fun addOverlapSample(): PsiFile = myFixture.addFileToProject(
        "Overlap.java",
        """
        class Overlap {
            String ip = "0.0.0.0";
            // 1.1.1
        }
        """.trimIndent()
    )

    // The word index gives each occurrence, also one that overlaps the occurrence before: "0.0"
    // at three offsets of "0.0.0.0". The run of the IDE goes on at the end of a match, so it
    // gives the first and the third. "Except Comments and String Literals" also rejects an
    // occurrence that starts inside a run occurrence or at its end
    // (`FindExceptCommentsOrLiteralsData.test`), so the second one is in the set too.
    fun testAnOccurrenceThatOverlapsAStringOccurrenceIsInTheStringSet() {
        val file = addOverlapSample()
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        assertEquals(mapOf("Overlap.java:2" to "STRING_LITERAL"), labelsByLine("0.0"))
        assertEquals(emptySet<TextMatch>(), search("code", "0.0"))
        assertEachContextGivesTheLinesOfTheIde(listOf(file), "0.0")
    }

    fun testAnOccurrenceThatOverlapsACommentOccurrenceIsInTheCommentSet() {
        val file = addOverlapSample()
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        assertEquals(mapOf("Overlap.java:3" to "COMMENT"), labelsByLine("1.1"))
        assertEquals(emptySet<TextMatch>(), search("code", "1.1"))
        assertEachContextGivesTheLinesOfTheIde(listOf(file), "1.1")
    }

    // A later page comes from extendSearchText when the first collection
    // (PaginationService.DEFAULT_OVERCOLLECT matches) is used up. Each page holds only matches of
    // the set of the filter.
    fun testALaterPageOfAFilteredSearchHoldsOnlyMatchesOfTheSet() {
        val count = PaginationService.DEFAULT_OVERCOLLECT + 20
        val body = (0 until count).joinToString("\n") { "    String s$it = \"zorbleword $it\";\n    // zorbleword $it" }
        myFixture.addFileToProject("Many.java", "class Many {\n$body\n}\n")
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        val first = call(buildJsonObject {
            put("query", "zorbleword")
            put("context", "strings")
            put("pageSize", PaginationService.MAX_PAGE_SIZE)
        })
        val cursor = first.nextCursor
        assertNotNull("The first page must have a cursor", cursor)
        val second = call(buildJsonObject {
            put("cursor", cursor!!)
            put("pageSize", PaginationService.MAX_PAGE_SIZE)
        })

        assertEquals(20, second.matches.size)
        for (page in listOf(first.matches, second.matches)) {
            assertEquals(setOf("STRING_LITERAL"), page.map { it.contextType }.toSet())
        }
        assertEquals((0 until count).map { 2 + 2 * it }.toSet(), (first.matches + second.matches).map { it.line }.toSet())
    }

    fun testACaseInsensitiveSearchKeepsTheSetOfEachFilter() {
        myFixture.addFileToProject(
            "Cases.java",
            """
            class Cases {
                String text = "ZorbleWord in a string";
                // ZORBLEWORD in a comment
                int zorbleWord = 1;
            }
            """.trimIndent()
        )
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        assertEquals(setOf(2), search("strings", caseSensitive = false).map { it.line }.toSet())
        assertEquals(setOf(3), search("comments", caseSensitive = false).map { it.line }.toSet())
        assertEquals(setOf(4), search("code", caseSensitive = false).map { it.line }.toSet())
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

    // A word inside an injected language fragment is one match of the host file. The search
    // also walked the fragment and gave a second match with the path of the fragment, a line of
    // the fragment and the label CODE (#184). The test platform has no IntelliLang plugin, so
    // the fragment is the Java code that the Java plugin injects into a Javadoc snippet.
    fun testAWordInAnInjectedFragmentIsOneMatchOfTheHostFile() {
        val java = myFixture.addFileToProject(
            "Documented.java",
            """
            class Documented {
                /**
                 * {@snippet :
                 * int zorbleword = 1;
                 * }
                 */
                void method() {}
            }
            """.trimIndent()
        )
        IndexingTestUtil.waitUntilIndexesAreReady(project)
        assertNotNull(
            "The snippet must be an injected fragment",
            InjectedLanguageManager.getInstance(project).findInjectedElementAt(java, java.text.indexOf("zorbleword"))
        )

        assertEquals(setOf(TextMatch("Documented.java", 4, 12, "* int zorbleword = 1;", "COMMENT")), search(null))
        assertEquals(emptySet<TextMatch>(), search("code"))
    }
}
