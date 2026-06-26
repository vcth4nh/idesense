package com.github.vcth4nh.idesense.util

import com.github.vcth4nh.idesense.settings.McpSettings
import dev.toonformat.jtoon.JToon

object ResponseFormatter {

    fun formatStructuredPayload(jsonText: String, format: McpSettings.ResponseFormat): String {
        return when (format) {
            McpSettings.ResponseFormat.JSON -> jsonText
            McpSettings.ResponseFormat.TOON -> JToon.encodeJson(jsonText)
        }
    }
}
