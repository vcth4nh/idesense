package com.github.vcth4nh.idesense.tools.navigation

import junit.framework.TestCase

// #171: the note of ide_find_usages names the base declarations that the search also covers.
class BaseDeclarationsNoteUnitTest : TestCase() {

    private fun ref(name: String, location: String?) = BaseDeclarationRef(name, location)

    fun testOneBase() = assertEquals(
        "'area' overrides or implements Shape.area (src/normal.js:16:5). The result also holds the usages of this base declaration, because a call through it can run 'area'. 1 of the 5 usages has match BASE.",
        BaseDeclarationsNote.build("area", listOf(ref("Shape.area", "src/normal.js:16:5")), baseUsages = 1, collected = 5, cut = false)
    )

    fun testTwoBases() = assertEquals(
        "'Area' overrides or implements 2 base declarations: main.Shape.Area (normal.go:12:2), main.Sized.Area (normal.go:20:2). The result also holds the usages of these base declarations, because a call through one of them can run 'Area'. 4 of the 9 usages have match BASE.",
        BaseDeclarationsNote.build("Area", listOf(ref("main.Shape.Area", "normal.go:12:2"), ref("main.Sized.Area", "normal.go:20:2")), 4, 9, false)
    )

    fun testMoreThanThreeBases() = assertEquals(
        "'m' overrides or implements 5 base declarations: A.m (a.ts:1:1), B.m (b.ts:1:1), C.m (c.ts:1:1) and 2 more (ide_find_super_methods lists them). The result also holds the usages of these base declarations, because a call through one of them can run 'm'. 0 of the 3 usages have match BASE.",
        BaseDeclarationsNote.build("m", listOf(ref("A.m", "a.ts:1:1"), ref("B.m", "b.ts:1:1"), ref("C.m", "c.ts:1:1"), ref("D.m", "d.ts:1:1"), ref("E.m", "e.ts:1:1")), 0, 3, false)
    )

    fun testCutResult() = assertEquals(
        "'Error' overrides or implements error.Error (builtin.go, library). The result also holds the usages of this base declaration, because a call through it can run 'Error'. 480 of the first 500 usages have match BASE.",
        BaseDeclarationsNote.build("Error", listOf(ref("error.Error", "builtin.go, library")), 480, 500, true)
    )

    fun testNoUsageCollected() = assertEquals(
        "'area' overrides or implements Shape.area. The result also holds the usages of this base declaration, because a call through it can run 'area'.",
        BaseDeclarationsNote.build("area", listOf(ref("Shape.area", null)), 0, 0, false)
    )
}
