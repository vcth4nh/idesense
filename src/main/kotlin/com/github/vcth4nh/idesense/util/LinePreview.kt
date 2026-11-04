package com.github.vcth4nh.idesense.util

import com.intellij.openapi.editor.Document

/**
 * Bounds the source-line text that tools return as `context` or `preview`.
 *
 * A minified file can hold megabytes on one line. A whole-line preview of such a line makes one
 * result item larger than a client accepts, and a smaller `pageSize` cannot help.
 */
object LinePreview {
    const val MAX_CHARS = 200
    private const val CUT = "…"

    /**
     * [around] for line [line] (0-based) of [document]. Reads the line as a view of the document
     * text, so only the returned window is copied.
     */
    fun ofLine(document: Document, line: Int, matchStart: Int, matchLength: Int = 0): String =
        around(
            document.charsSequence.subSequence(document.getLineStartOffset(line), document.getLineEndOffset(line)),
            matchStart,
            matchLength
        )

    /**
     * Returns [line] trimmed when it fits in [MAX_CHARS] characters. Otherwise returns a window of
     * [MAX_CHARS] characters of the trimmed line that holds the match at [matchStart] (0-based
     * offset in [line]); "…" marks each cut end. A match longer than the window shows its start.
     */
    fun around(line: CharSequence, matchStart: Int, matchLength: Int = 0): String {
        val text = line.trim()
        if (text.length <= MAX_CHARS) return text.toString()
        val match = (matchStart - (line.length - line.trimStart().length)).coerceIn(0, text.length)
        var start = (match - (MAX_CHARS - matchLength.coerceIn(0, MAX_CHARS)) / 2)
            .coerceIn(0, text.length - MAX_CHARS)
        var end = start + MAX_CHARS
        // Never cut a surrogate pair in half.
        if (start > 0 && text[start].isLowSurrogate()) start++
        if (end < text.length && text[end - 1].isHighSurrogate()) end--
        return (if (start > 0) CUT else "") + text.subSequence(start, end) + (if (end < text.length) CUT else "")
    }
}
