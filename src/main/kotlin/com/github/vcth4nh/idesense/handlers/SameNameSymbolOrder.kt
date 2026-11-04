package com.github.vcth4nh.idesense.handlers

/**
 * Orders the same-name symbols of a headless Go to Symbol search.
 *
 * The popup keeps names in match-degree order and sorts the elements of one name by proximity to
 * the file open in the editor (`DefaultChooseByNameItemProvider.processByNames`,
 * idea/262.8665.337). A headless call has no editor ([PopupFaithfulSymbolSearch] passes no
 * context element off the EDT), so that order carries no signal, and a field assignment can rank
 * above the declaration. Inside one name, this puts declarations (class, function, ...) before
 * values (field, variable, ...), then a symbol declared in a file of its own name, then sorts by
 * file, line and column: the popup's order of equal items changes between IDE sessions, and a
 * fixed order gives the same answer every time. The order of the names stays as the popup gives it.
 */
internal object SameNameSymbolOrder {
    private val VALUE_KINDS = setOf("FIELD", "VARIABLE", "PROPERTY", "CONSTANT", "PARAMETER")

    fun <T> sort(items: List<T>, symbol: (T) -> SymbolData): List<T> {
        val nameOrder = HashMap<String, Int>()
        for (item in items) nameOrder.putIfAbsent(symbol(item).name, nameOrder.size)
        return items.sortedWith(
            compareBy(
                { nameOrder.getValue(symbol(it).name) },
                { if (symbol(it).kind in VALUE_KINDS) 1 else 0 },
                { if (fileStem(symbol(it).file).equals(symbol(it).name, ignoreCase = true)) 0 else 1 },
                { symbol(it).file },
                { symbol(it).line },
                { symbol(it).column },
            )
        )
    }

    private fun fileStem(path: String): String = path.substringAfterLast('/').substringBeforeLast('.')
}
