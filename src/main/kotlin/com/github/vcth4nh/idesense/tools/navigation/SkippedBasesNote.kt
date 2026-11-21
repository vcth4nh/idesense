package com.github.vcth4nh.idesense.tools.navigation

/**
 * The `notes` entry of ide_find_usages and ide_explain_symbol for the base methods that the search
 * does not search on purpose ([com.github.vcth4nh.idesense.handlers.SuperMethodsProvider.skippedBaseDeclarations]):
 * today the methods of the Python class `object`.
 */
internal object SkippedBasesNote {

    /** One sentence for each different name of [qualifiedNames], in their order. Null when [qualifiedNames] is empty. */
    fun build(qualifiedNames: List<String>): String? {
        if (qualifiedNames.isEmpty()) return null
        return qualifiedNames.distinct().joinToString(" ") { name ->
            "The base method $name is not searched: each class is a subclass of object."
        }
    }
}
