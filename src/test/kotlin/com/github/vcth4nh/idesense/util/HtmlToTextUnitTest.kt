package com.github.vcth4nh.idesense.util

import junit.framework.TestCase

/**
 * Unit tests for [HtmlToText], the Quick Documentation HTML → plain text converter
 * used by ide_explain_symbol (#41).
 *
 * Contract: block-level tag boundaries (and table cells) become line breaks, all other
 * tags are stripped, entities are decoded AFTER tag stripping (so escaped markup stays
 * literal text), style/script bodies are dropped, and blank lines are removed entirely.
 */
class HtmlToTextUnitTest : TestCase() {

    fun testStripsInlineTagsAndKeepsText() {
        assertEquals("Foo bar", HtmlToText.convert("<b>Foo</b> <i>bar</i>"))
    }

    fun testBlockTagBoundariesBecomeLineBreaks() {
        assertEquals(
            "class Foo\nDocs.",
            HtmlToText.convert("<div class='definition'><pre>class Foo</pre></div><div class='content'>Docs.</div>")
        )
    }

    fun testBrAndUnclosedParagraphBecomeLineBreaks() {
        assertEquals("a\nb\nc\nd", HtmlToText.convert("a<br>b<br/>c<p>d"))
    }

    fun testTableCellBoundariesBecomeLineBreaks() {
        assertEquals(
            "See Also:\nShape",
            HtmlToText.convert("<table><tr><td class='section'>See Also:</td><td><code>Shape</code></td></tr></table>")
        )
    }

    fun testEntitiesDecoded() {
        assertEquals("List<String> & \"more\" a b 'q'", HtmlToText.convert("List&lt;String&gt; &amp; &quot;more&quot; a&nbsp;b &#39;q&#39;"))
    }

    fun testEntityDecodingHappensAfterTagStripping() {
        assertEquals("<b>not bold</b>", HtmlToText.convert("&lt;b&gt;not bold&lt;/b&gt;"))
    }

    fun testEmptyLinesDropped() {
        assertEquals("a\nb", HtmlToText.convert("<p></p><p>a</p><p>  </p><p></p><p>b</p>"))
    }

    fun testStyleAndScriptBodiesRemoved() {
        assertEquals("Text", HtmlToText.convert("<style>.a { color: red; }</style>Text<script>alert(1)</script>"))
    }

    fun testNewlinesInsidePreArePreserved() {
        assertEquals(
            "public class Circle\nextends Shape",
            HtmlToText.convert("<pre>public class <b>Circle</b>\nextends Shape</pre>")
        )
    }

    fun testRealisticQuickDoc() {
        val html = "<html><body><div class='definition'><pre>public class <b>Circle</b>\n" +
            "extends Shape</pre></div><div class='content'>A circle shape.<p>Second para.</div>" +
            "<table class='sections'><tr><td valign='top' class='section'><p>See Also:</td>" +
            "<td><a href=\"psi_element://Shape\"><code>Shape</code></a></td></tr></table></body></html>"
        assertEquals(
            "public class Circle\nextends Shape\nA circle shape.\nSecond para.\nSee Also:\nShape",
            HtmlToText.convert(html)
        )
    }
}
