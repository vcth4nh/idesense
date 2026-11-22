package com.jetbrains.python.psi.search

import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.types.TypeEvalContext

/** Test stub. [search] gives the result of [onSearch], which a test sets. */
class PySuperMethodsSearch {
    companion object {
        var onSearch: (PyFunction) -> Any = { throw UnsupportedOperationException("no search in this test") }

        @JvmStatic
        fun search(function: PyFunction, deepSearch: Boolean, context: TypeEvalContext): Any = onSearch(function)
    }
}
