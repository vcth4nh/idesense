package com.github.vcth4nh.idesense.constants

/**
 * The kinds of usage that the find usages search leaves out, although the search of the IDE gives
 * them ([com.github.vcth4nh.idesense.handlers.SuperMethodsProvider.droppedUsageKind]). The tools
 * give the count of each kind in a `notes` entry: no silent drop.
 * - [GO_FIELD_KEY]: a key of a Go composite literal that names a struct field with the same name
 *   as the type of the query.
 * - [PHP_SELF_REFERENCE]: a reference to a PHP class through `$this`, `self` or `static` inside
 *   that class.
 */
object UsageDrop {
    const val GO_FIELD_KEY = "GO_FIELD_KEY"
    const val PHP_SELF_REFERENCE = "PHP_SELF_REFERENCE"
}
