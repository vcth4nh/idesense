package com.github.vcth4nh.idesense.util

/**
 * Converts Quick Documentation HTML (DocumentationProvider output) to compact plain text
 * for MCP tool responses.
 *
 * Block-level tag boundaries (and table cells) become line breaks, every other tag is
 * stripped, entities decode AFTER stripping so escaped markup stays literal text, and
 * blank lines are dropped for compactness.
 */
object HtmlToText {

    private val STYLE_SCRIPT = Regex("(?is)<(style|script)\\b[^>]*>.*?</\\1>")
    private val BREAK_TAGS =
        Regex("(?i)</?(?:p|br|div|pre|li|tr|td|th|table|tbody|thead|ul|ol|blockquote|hr|h[1-6])\\b[^>]*>")
    private val ANY_TAG = Regex("<[^>]+>")
    private val NUMERIC_ENTITY = Regex("&#(\\d+);")

    fun convert(html: String): String {
        val withBreaks = BREAK_TAGS.replace(STYLE_SCRIPT.replace(html, ""), "\n")
        val decoded = decodeEntities(ANY_TAG.replace(withBreaks, ""))
        return decoded.lines()
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .joinToString("\n")
    }

    private fun decodeEntities(text: String): String {
        val numeric = NUMERIC_ENTITY.replace(text) { it.groupValues[1].toInt().toChar().toString() }
        // &amp; must decode last so "&amp;lt;" yields the literal "&lt;", not "<".
        return numeric
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .replace("&apos;", "'")
            .replace("&nbsp;", " ")
            .replace("&amp;", "&")
    }
}
