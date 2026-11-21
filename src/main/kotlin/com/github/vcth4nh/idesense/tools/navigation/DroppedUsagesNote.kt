package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.UsageDrop

/**
 * The `notes` entries of ide_find_usages and ide_explain_symbol for the usages that the search
 * leaves out ([UsageDrop]): one entry for each kind, with the count, in terms of the code.
 */
internal object DroppedUsagesNote {

    /**
     * One note for each kind of [dropped] (a [UsageDrop] value to its count), in the order of the
     * map. [cut] is true when the search stopped at its limit: then the count is a lower bound.
     */
    fun build(dropped: Map<String, Int>, cut: Boolean): List<String> =
        dropped.map { (kind, count) -> sentence(kind, count, cut) }

    private fun sentence(kind: String, count: Int, cut: Boolean): String {
        val (one, many) = when (kind) {
            UsageDrop.GO_FIELD_KEY ->
                "composite literal key that names a struct field with the same name as this type is" to
                    "composite literal keys that name a struct field with the same name as this type are"
            UsageDrop.PHP_SELF_REFERENCE ->
                "reference to this class through \$this, self or static inside the class is" to
                    "references to this class through \$this, self or static inside the class are"
            else -> "usage of the kind $kind is" to "usages of the kind $kind are"
        }
        val number = if (cut) "$count or more" else "$count"
        val phrase = if (cut || count != 1) many else one
        return "$number $phrase not in the list."
    }
}
