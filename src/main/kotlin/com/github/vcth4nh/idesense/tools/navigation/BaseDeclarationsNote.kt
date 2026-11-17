package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.constants.UsageMatch

/** A base declaration for the note: its printed name and its place, or null when the place is not known. */
internal class BaseDeclarationRef(val name: String, val location: String?)

/**
 * The `notes` entry of ide_find_usages when the symbol overrides or implements base declarations
 * (#171). The text names the base declarations and gives the count of the usages with match
 * [UsageMatch.BASE], in terms of the code.
 */
internal object BaseDeclarationsNote {
    /** The note names this number of base declarations. It gives only the count of the others. */
    const val MAX_NAMED = 3

    /**
     * The note for [symbolName] and its [bases] (not empty). [baseUsages] of the [collected] usages
     * have match [UsageMatch.BASE]. [cut] is true when the search found more usages than [collected].
     * The note has no count sentence when [collected] is 0.
     */
    fun build(symbolName: String, bases: List<BaseDeclarationRef>, baseUsages: Int, collected: Int, cut: Boolean): String {
        val symbol = "'$symbolName'"
        val text = StringBuilder()
        if (bases.size == 1) {
            text.append("$symbol overrides or implements ${describe(bases[0])}. ")
            text.append("The result also holds the usages of this base declaration, because a call through it can run $symbol.")
        } else {
            text.append("$symbol overrides or implements ${bases.size} base declarations: ")
            text.append(bases.take(MAX_NAMED).joinToString(", ") { describe(it) })
            if (bases.size > MAX_NAMED) {
                text.append(" and ${bases.size - MAX_NAMED} more (${ToolNames.FIND_SUPER_METHODS} lists them)")
            }
            text.append(". ")
            text.append("The result also holds the usages of these base declarations, because a call through one of them can run $symbol.")
        }
        if (collected > 0) {
            val usages = if (cut) "the first $collected usages" else "the $collected usages"
            val verb = if (baseUsages == 1) "has" else "have"
            text.append(" $baseUsages of $usages $verb match ${UsageMatch.BASE}.")
        }
        return text.toString()
    }

    private fun describe(base: BaseDeclarationRef): String =
        if (base.location == null) base.name else "${base.name} (${base.location})"
}
