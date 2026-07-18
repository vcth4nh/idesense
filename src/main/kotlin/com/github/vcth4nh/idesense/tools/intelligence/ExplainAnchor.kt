package com.github.vcth4nh.idesense.tools.intelligence

import com.github.vcth4nh.idesense.constants.ParamNames
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive

/**
 * The resolved anchor for ide_explain_symbol: either a symbol name/qualified name or an
 * exact file position. Exactly one of the two forms must be supplied (#41).
 */
internal sealed interface ExplainAnchor {
    data class BySymbol(val symbol: String) : ExplainAnchor
    data class ByPosition(val file: String, val line: Int, val column: Int) : ExplainAnchor
    data class Invalid(val message: String) : ExplainAnchor

    companion object {
        fun parse(arguments: JsonObject): ExplainAnchor {
            val symbol = arguments[ParamNames.SYMBOL]?.jsonPrimitive?.content
            val file = arguments[ParamNames.FILE]?.jsonPrimitive?.content
            val line = arguments[ParamNames.LINE]?.jsonPrimitive?.intOrNull
            val column = arguments[ParamNames.COLUMN]?.jsonPrimitive?.intOrNull

            val hasAnyPosition = file != null || line != null || column != null
            if (symbol != null && hasAnyPosition) {
                return Invalid("Provide either 'symbol' or 'file'+'line'+'column', not both.")
            }
            if (symbol != null) {
                if (symbol.isBlank()) return Invalid("'symbol' cannot be blank.")
                return BySymbol(symbol)
            }
            if (!hasAnyPosition) {
                return Invalid("Provide a 'symbol' name or a 'file'+'line'+'column' position.")
            }
            val missing = listOfNotNull(
                ParamNames.FILE.takeIf { file == null },
                ParamNames.LINE.takeIf { line == null },
                ParamNames.COLUMN.takeIf { column == null },
            )
            if (missing.isNotEmpty()) {
                return Invalid("Position anchor incomplete: missing ${missing.joinToString(", ") { "'$it'" }}.")
            }
            return ByPosition(file!!, line!!, column!!)
        }
    }
}
