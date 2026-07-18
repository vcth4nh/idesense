package com.github.vcth4nh.idesense.constants

object ToolNames {
    // Navigation tools
    const val FIND_USAGES = "ide_find_usages"
    const val FIND_DEFINITION = "ide_find_definition"
    const val TYPE_HIERARCHY = "ide_type_hierarchy"
    const val CALL_HIERARCHY = "ide_call_hierarchy"
    const val FIND_IMPLEMENTATIONS = "ide_find_implementations"
    const val FIND_SYMBOL = "ide_find_symbol"
    const val FIND_SUPER_METHODS = "ide_find_super_methods"
    const val FILE_STRUCTURE = "ide_file_structure"
    const val FIND_CLASS = "ide_find_class"
    const val FIND_FILE = "ide_find_file"
    const val SEARCH_TEXT = "ide_search_text"
    const val READ_FILE = "ide_read_file"

    // Intelligence tools
    const val DIAGNOSTICS = "ide_diagnostics"
    const val EXPLAIN_SYMBOL = "ide_explain_symbol"

    // Project tools
    const val INDEX_STATUS = "ide_index_status"
    const val SYNC_FILES = "ide_sync_files"
    const val INSTALL_PLUGIN = "ide_install_plugin"
    const val RESTART_IDE = "ide_restart"

    // Refactoring tools
    const val REFACTOR_RENAME = "ide_refactor_rename"
    const val REFACTOR_MOVE = "ide_move_file"

    /**
     * All known tool names, sorted alphabetically.
     * Keep this list in sync when adding or removing tool name constants.
     */
    val ALL: List<String> = listOf(
        CALL_HIERARCHY,
        DIAGNOSTICS,
        EXPLAIN_SYMBOL,
        FILE_STRUCTURE,
        FIND_CLASS,
        FIND_DEFINITION,
        FIND_FILE,
        FIND_IMPLEMENTATIONS,
        FIND_SUPER_METHODS,
        FIND_SYMBOL,
        FIND_USAGES,
        INDEX_STATUS,
        INSTALL_PLUGIN,
        REFACTOR_MOVE,
        READ_FILE,
        REFACTOR_RENAME,
        RESTART_IDE,
        SEARCH_TEXT,
        SYNC_FILES,
        TYPE_HIERARCHY
    )
}
