package com.github.vcth4nh.idesense.handlers

import junit.framework.TestCase

class SameNameSymbolOrderUnitTest : TestCase() {

    private fun sym(name: String, kind: String, file: String) =
        SymbolData(name = name, qualifiedName = null, kind = kind, file = file, line = 1, column = 1)

    private fun order(vararg items: SymbolData) =
        SameNameSymbolOrder.sort(items.toList()) { it }.map { "${it.kind} ${it.file}" }

    fun testDeclarationsComeBeforeValuesOfTheSameName() {
        assertEquals(
            listOf("FUNCTION pkg/other.py", "FIELD a/view.py", "VARIABLE b/model.py"),
            order(
                sym("render", "FIELD", "a/view.py"),
                sym("render", "FUNCTION", "pkg/other.py"),
                sym("render", "VARIABLE", "b/model.py"),
            )
        )
    }

    fun testSymbolInAFileOfItsOwnNameComesFirstAmongDeclarations() {
        assertEquals(
            listOf("FUNCTION pkg/render/render.py", "FUNCTION examples/sample.py", "FIELD x/render.py"),
            order(
                sym("render", "FIELD", "x/render.py"),
                sym("render", "FUNCTION", "examples/sample.py"),
                sym("render", "FUNCTION", "pkg/render/render.py"),
            )
        )
    }

    fun testFileNameMatchIgnoresCase() {
        assertEquals(
            listOf("CLASS src/router.ts", "CLASS src/app.ts"),
            order(sym("Router", "CLASS", "src/app.ts"), sym("Router", "CLASS", "src/router.ts"))
        )
    }

    fun testNamesKeepTheirFirstAppearanceOrder() {
        val sorted = SameNameSymbolOrder.sort(
            listOf(
                sym("Foo", "FIELD", "a.kt"),
                sym("foo", "FUNCTION", "b.kt"),
                sym("Foo", "CLASS", "c.kt"),
            )
        ) { it }
        assertEquals(listOf("Foo CLASS", "Foo FIELD", "foo FUNCTION"), sorted.map { "${it.name} ${it.kind}" })
    }

    fun testRemainingTiesSortByLocation() {
        // The popup's order of equal items changes between IDE sessions; file, line and column fix it.
        assertEquals(
            listOf("METHOD a/two.java:3", "METHOD z/one.java:1", "METHOD z/one.java:7"),
            SameNameSymbolOrder.sort(
                listOf(
                    sym("run", "METHOD", "z/one.java").copy(line = 7),
                    sym("run", "METHOD", "z/one.java"),
                    sym("run", "METHOD", "a/two.java").copy(line = 3),
                )
            ) { it }.map { "${it.kind} ${it.file}:${it.line}" }
        )
    }
}
