package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.UsageDrop
import junit.framework.TestCase

// The notes of ide_find_usages and ide_explain_symbol give the count of each kind of usage that the tool leaves out.
class DroppedUsagesNoteUnitTest : TestCase() {

    fun testOneGoFieldKey() = assertEquals(
        listOf("1 composite literal key that names a struct field with the same name as this type is not in the list."),
        DroppedUsagesNote.build(mapOf(UsageDrop.GO_FIELD_KEY to 1), cut = false)
    )

    fun testThreeGoFieldKeys() = assertEquals(
        listOf("3 composite literal keys that name a struct field with the same name as this type are not in the list."),
        DroppedUsagesNote.build(mapOf(UsageDrop.GO_FIELD_KEY to 3), cut = false)
    )

    fun testGoFieldKeysOfACutSearch() = assertEquals(
        listOf("1 or more composite literal keys that name a struct field with the same name as this type are not in the list."),
        DroppedUsagesNote.build(mapOf(UsageDrop.GO_FIELD_KEY to 1), cut = true)
    )

    fun testOnePhpSelfReference() = assertEquals(
        listOf("1 reference to this class through \$this, self or static inside the class is not in the list."),
        DroppedUsagesNote.build(mapOf(UsageDrop.PHP_SELF_REFERENCE to 1), cut = false)
    )

    fun testThreePhpSelfReferences() = assertEquals(
        listOf("3 references to this class through \$this, self or static inside the class are not in the list."),
        DroppedUsagesNote.build(mapOf(UsageDrop.PHP_SELF_REFERENCE to 3), cut = false)
    )

    fun testPhpSelfReferencesOfACutSearch() = assertEquals(
        listOf("3 or more references to this class through \$this, self or static inside the class are not in the list."),
        DroppedUsagesNote.build(mapOf(UsageDrop.PHP_SELF_REFERENCE to 3), cut = true)
    )

    fun testOneNoteForEachKindInTheOrderOfTheMap() = assertEquals(
        listOf(
            "2 references to this class through \$this, self or static inside the class are not in the list.",
            "1 composite literal key that names a struct field with the same name as this type is not in the list.",
        ),
        DroppedUsagesNote.build(linkedMapOf(UsageDrop.PHP_SELF_REFERENCE to 2, UsageDrop.GO_FIELD_KEY to 1), cut = false)
    )

    fun testNoDroppedUsageGivesNoNote() = assertEquals(
        emptyList<String>(),
        DroppedUsagesNote.build(emptyMap(), cut = true)
    )
}
