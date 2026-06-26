# IdeSense - Tools Reference

This reference documents **return shapes and tool selection** for the IDE MCP tools enabled by
default. Parameters are provided by the live JSON schema in `tools/list` — consult that payload
for parameter names, types, defaults, and enum values. The remaining tools are listed under
**Other tools** at the end.

**Path conventions**: file paths for project files are relative to the project root;
library/dependency paths returned by the plugin (absolute paths or `jar://` URLs) must
be passed back unchanged. Line and column numbers are **1-based**.

---

## Navigation Tools

### ide_find_usages
Find all usages of a symbol (semantic, not text search).

**Returns**: `{ usages: [{ file, line, column, preview, usageType, enclosingScope }], totalCount, truncated, nextCursor?, hasMore, totalCollected, offset, pageSize, stale }`

`usageType` values: `METHOD_CALL`, `FIELD_ACCESS`, `IMPORT`, `PARAMETER`, `VARIABLE`, `REFERENCE`. Paginated (see Pagination in SKILL.md).

### ide_find_definition
Go to where a symbol is defined.

**Returns**: `{ file, line, column, name, kind, preview, qualifiedName?, enclosingScope? }`

Handles packages, compiled classes, and library sources (`jar://` URLs).

### ide_find_class
Search for classes/interfaces by name using IDE's class index (Ctrl+N / Cmd+O equivalent).

**Returns**: `{ classes: [{name, qualifiedName, kind, file, line, column}], totalCount, query }`

Project results use relative paths; dependency/library results may use absolute paths or `jar://` URLs.
Exact (case-insensitive) by default; with `fuzzySearch: true`, IDE camelCase/substring matching applies (`USvc` → `UserService`).

### ide_find_file
Search for files by name using IDE's file index (Ctrl+Shift+N / Cmd+Shift+O equivalent).

**Returns**: `{ files: [{name, path, directory}], totalCount, query }`

Project results use relative paths; dependency/library results may use absolute paths or `jar://` URLs.

### ide_search_text
Search for exact words using IDE's pre-built word index. O(1) lookups, not file scanning.

**Returns**: `{ matches: [{file, line, column, context, contextType}], totalCount, query }`

`contextType` values: `CODE`, `COMMENT`, `STRING_LITERAL`.
**Selection note**: exact-word only (uses word index, not regex). Use `Grep` for regex patterns.

### ide_find_implementations
Find implementations of interfaces, abstract classes, or abstract methods.

**Returns**: `{ implementations: [{name, qualifiedName?, file, line, column, kind}], totalCount, nextCursor?, hasMore, totalCollected, offset, pageSize, stale }`

**Languages**: Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

### ide_find_super_methods
Find parent methods that a given method overrides or implements.

**Returns**: `{ method: {name, qualifiedName?, kind, file, line, column}, hierarchy: [{name, qualifiedName?, kind, file?, line?, column?}] }`

**Languages**: Java, Kotlin, Python, JS/TS, PHP. Go returns interface methods a type satisfies. Rust returns trait fn/const/type alias the impl satisfies.

### ide_type_hierarchy
Get complete type inheritance hierarchy (supertypes and subtypes).

**Returns**: `{ element: {name, qualifiedName?, enclosingScope?, kind, file?, line?, column?, supertypes?}, supertypes: [{name, qualifiedName?, enclosingScope?, kind, file?, line?, column?, supertypes?}], subtypes: [{name, qualifiedName?, enclosingScope?, kind, file?, line?, column?, supertypes?}] }`

Provide either `className` (FQN, preferred) or `file`+`line`+`column`. Unlike other read-only navigation tools, file mode does not resolve dependency/library absolute paths or `jar://` URLs.
**Languages**: Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

### ide_call_hierarchy
Build call tree showing who calls a method or what a method calls.

**Returns**: `{ element: {name, qualifiedName?, enclosingScope?, kind, file, line, column}, calls: [{name, qualifiedName?, enclosingScope?, kind, file, line, column, children?: [...]}] }`

**Languages**: Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

---

## Intelligence Tools

### ide_diagnostics
Analyze a file for errors, warnings, and available quick fixes/intentions.

**Returns**: `{ problems: [{message, severity, file, line, column, endLine?, endColumn?}], intentions: [{name, description?}], problemCount, intentionCount, analysisFresh, analysisTimedOut, analysisMessage }`

`severity` values: `ERROR`, `WARNING`, `WEAK_WARNING`. Open files use fresh daemon highlights; closed files use public batch analysis so `WEAK_WARNING` results and quick-fix intentions may be less complete.

---

## Refactoring Tools

### ide_refactor_rename
Rename a symbol and update ALL references (semantic rename, not find-replace). Works across ALL languages.

**Returns**: `{ success, affectedFiles: [paths], changesCount, message }`

Auto-renames getters/setters, overriding methods, constructor params ↔ fields, test classes. Supports IDE undo (Ctrl+Z).

### ide_move_file
Move a file to a new directory. Language-aware reference, import, and package/namespace updates when the IDE provides a semantic move backend for that file type.

**Returns**: `{ success, affectedFiles: [paths], changesCount, message }`

Supports IDE undo (Ctrl+Z).

### ide_refactor_safe_delete (Java/Kotlin only)
Delete a symbol or file, checking for usages first.

**Returns (success)**: `{ success, affectedFiles, changesCount, message }`
**Returns (blocked)**: `{ canDelete: false, elementName, elementType, usageCount, blockingUsages: [{file, line, column, context}], message }`

**Availability**: IntelliJ IDEA, Android Studio (requires Java plugin).

---

## Project Tools

### ide_index_status
Check if IDE is ready for code intelligence operations.

**Returns**: `{ isDumbMode, isIndexing, indexingProgress? }`

When `isDumbMode: true`, most tools will fail — wait and retry.

### ide_sync_files
Force sync IDE's virtual file system with external file changes.

**Returns**: `{ syncedPaths, syncedAll, message }`

Call when files were created or modified outside the IDE and search tools miss them.

---

## Other tools

The full tool set also includes `ide_find_symbol`, `ide_file_structure`, `ide_read_file`,
`ide_reformat_code`, `ide_optimize_imports`, `ide_convert_java_to_kotlin`, `ide_build_project`,
`ide_install_plugin`, `ide_restart`, `ide_open_file`, and `ide_get_active_file`. Any tool can be
enabled or disabled in **Settings → Tools → IdeSense**, so `tools/list` is the source of
truth for what is callable right now. If a tool documented here is missing from `tools/list`, it is
disabled in this configuration — ask the user to enable it rather than falling back to a worse approach.
