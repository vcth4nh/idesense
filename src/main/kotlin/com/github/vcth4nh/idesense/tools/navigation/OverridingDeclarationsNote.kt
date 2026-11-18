package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.constants.UsageMatch

/**
 * The `notes` entry of ide_find_usages when the search also covers the declarations that override
 * or implement the symbol ([com.github.vcth4nh.idesense.handlers.SuperMethodsProvider.findOverridingDeclarations]).
 * The text follows [BaseDeclarationsNote]: it names the overriding declarations and gives the count
 * of the usages with match [UsageMatch.OVERRIDE], in terms of the code.
 */
internal object OverridingDeclarationsNote {

    /**
     * The note for [symbolName] and its [overrides]. Null when [overrides] is empty. [overrideUsages]
     * of the [collected] usages have match [UsageMatch.OVERRIDE]. [cut] is true when the search found
     * more usages than [collected]. The note has no count sentence when [collected] is 0.
     */
    fun build(symbolName: String, overrides: List<BaseDeclarationRef>, overrideUsages: Int, collected: Int, cut: Boolean): String? {
        if (overrides.isEmpty()) return null
        val symbol = "'$symbolName'"
        val max = BaseDeclarationsNote.MAX_NAMED
        val text = StringBuilder()
        if (overrides.size == 1) {
            text.append("$symbol has an overriding declaration: ${describe(overrides[0])}. ")
            text.append("The result also holds the usages of this overriding declaration. ")
            text.append("A usage with match ${UsageMatch.OVERRIDE} is a call on a value whose type has this overriding declaration.")
        } else {
            text.append("$symbol has ${overrides.size} overriding declarations: ")
            text.append(overrides.take(max).joinToString(", ") { describe(it) })
            if (overrides.size > max) {
                text.append(" and ${overrides.size - max} more (${ToolNames.FIND_IMPLEMENTATIONS} lists them)")
            }
            text.append(". ")
            text.append("The result also holds the usages of these overriding declarations. ")
            text.append("A usage with match ${UsageMatch.OVERRIDE} is a call on a value whose type has one of these overriding declarations.")
        }
        if (collected > 0) {
            val usages = if (cut) "the first $collected usages" else "the $collected usages"
            val verb = if (overrideUsages == 1) "has" else "have"
            text.append(" $overrideUsages of $usages $verb match ${UsageMatch.OVERRIDE}.")
        }
        return text.toString()
    }

    private fun describe(ref: BaseDeclarationRef): String =
        if (ref.location == null) ref.name else "${ref.name} (${ref.location})"
}
