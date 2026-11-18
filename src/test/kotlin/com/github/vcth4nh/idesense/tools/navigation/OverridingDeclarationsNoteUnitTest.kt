package com.github.vcth4nh.idesense.tools.navigation

import junit.framework.TestCase

// The note of ide_find_usages names the overriding declarations that the search also covers.
class OverridingDeclarationsNoteUnitTest : TestCase() {

    private fun ref(name: String, location: String?) = BaseDeclarationRef(name, location)

    fun testOneOverridingDeclaration() = assertEquals(
        "'area' has an overriding declaration: Circle::area (src/Circle.php:12:21). The result also holds the usages of this overriding declaration. A usage with match OVERRIDE is a call on a value whose type has this overriding declaration. 1 of the 5 usages has match OVERRIDE.",
        OverridingDeclarationsNote.build("area", listOf(ref("Circle::area", "src/Circle.php:12:21")), overrideUsages = 1, collected = 5, cut = false)
    )

    fun testThreeOverridingDeclarations() = assertEquals(
        "'area' has 3 overriding declarations: Circle::area (src/Circle.php:12:21), Square::area (src/Square.php:9:21), Ring::area (src/Ring.php:7:21). The result also holds the usages of these overriding declarations. A usage with match OVERRIDE is a call on a value whose type has one of these overriding declarations. 4 of the 9 usages have match OVERRIDE.",
        OverridingDeclarationsNote.build(
            "area",
            listOf(ref("Circle::area", "src/Circle.php:12:21"), ref("Square::area", "src/Square.php:9:21"), ref("Ring::area", "src/Ring.php:7:21")),
            4, 9, false
        )
    )

    fun testMoreThanThreeOverridingDeclarations() = assertEquals(
        "'m' has 5 overriding declarations: A::m (a.php:1:1), B::m (b.php:1:1), C::m (c.php:1:1) and 2 more (ide_find_implementations lists them). The result also holds the usages of these overriding declarations. A usage with match OVERRIDE is a call on a value whose type has one of these overriding declarations. 0 of the 3 usages have match OVERRIDE.",
        OverridingDeclarationsNote.build(
            "m",
            listOf(ref("A::m", "a.php:1:1"), ref("B::m", "b.php:1:1"), ref("C::m", "c.php:1:1"), ref("D::m", "d.php:1:1"), ref("E::m", "e.php:1:1")),
            0, 3, false
        )
    )

    fun testCutResult() = assertEquals(
        "'run' has an overriding declaration: Job::run (Job.php, library). The result also holds the usages of this overriding declaration. A usage with match OVERRIDE is a call on a value whose type has this overriding declaration. 480 of the first 500 usages have match OVERRIDE.",
        OverridingDeclarationsNote.build("run", listOf(ref("Job::run", "Job.php, library")), 480, 500, true)
    )

    fun testNoUsageCollected() = assertEquals(
        "'area' has an overriding declaration: Circle::area. The result also holds the usages of this overriding declaration. A usage with match OVERRIDE is a call on a value whose type has this overriding declaration.",
        OverridingDeclarationsNote.build("area", listOf(ref("Circle::area", null)), 0, 0, false)
    )

    fun testNoOverridingDeclarationGivesNoNote() =
        assertNull(OverridingDeclarationsNote.build("area", emptyList(), 0, 5, false))
}
