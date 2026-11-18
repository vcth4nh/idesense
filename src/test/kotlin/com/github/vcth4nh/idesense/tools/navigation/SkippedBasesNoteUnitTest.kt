package com.github.vcth4nh.idesense.tools.navigation

import junit.framework.TestCase

// The note of ide_find_usages and ide_explain_symbol names each base method that the search does not search.
class SkippedBasesNoteUnitTest : TestCase() {

    fun testOneSkippedBase() = assertEquals(
        "The base method builtins.object.__init__ is not searched: each class is a subclass of object.",
        SkippedBasesNote.build(listOf("builtins.object.__init__"))
    )

    fun testOneSentenceForEachQualifiedName() = assertEquals(
        "The base method builtins.object.__eq__ is not searched: each class is a subclass of object. " +
            "The base method builtins.object.__hash__ is not searched: each class is a subclass of object.",
        SkippedBasesNote.build(listOf("builtins.object.__eq__", "builtins.object.__hash__", "builtins.object.__eq__"))
    )

    fun testNoSkippedBaseGivesNoNote() = assertNull(SkippedBasesNote.build(emptyList()))
}
