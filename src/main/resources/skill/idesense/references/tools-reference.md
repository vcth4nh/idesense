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
Find semantic references to a symbol (not text search). Paginated; `totalCollected` is a collected count (each cursor caches up to an internal cap), not a guaranteed whole-project total — page with `hasMore`/`nextCursor`.

**Returns**: `{ usages: [{ file, line, column, preview, usageType, enclosingScope }], truncated, nextCursor?, hasMore, totalCollected, offset, pageSize, stale, warnings? }` — non-null `warnings` (first page) means a find-usages handler stage degraded and the list may be incomplete.

`usageType` values: `METHOD_CALL`, `FIELD_ACCESS`, `IMPORT`, `PARAMETER`, `VARIABLE`, `REFERENCE`. Paginated (see Pagination in SKILL.md).

### ide_find_definition
Go to where a symbol is defined.

**Returns**: `{ file, line, column, name, kind, preview, qualifiedName?, enclosingScope? }`

Handles packages, compiled classes, and library sources (`jar://` URLs).

### ide_find_class
Search for class-like/type declarations by name using IDE's Go to Class index (Ctrl+N / Cmd+O equivalent): classes, interfaces, enums, records, structs, traits, objects, annotations, and similar type declarations. Not methods/fields/functions — use `ide_find_symbol` (when enabled) or `ide_search_text` for those.

**Returns**: `{ classes: [{name, qualifiedName?, kind, file, line, column}], query, nextCursor?, hasMore, totalCollected, offset, pageSize, stale }`

Project results use relative paths; dependency/library results may use absolute paths or `jar://` URLs.
Exact (case-insensitive) by default; with `fuzzySearch: true`, IDE camelCase/substring matching applies (`USvc` → `UserService`).

### ide_find_file
Search for files by name using IDE's file index (Ctrl+Shift+N / Cmd+Shift+O equivalent).

**Returns**: `{ files: [{name, path, directory}], query }`

Project results use relative paths; dependency/library results may use absolute paths or `jar://` URLs.

### ide_search_text
Search for exact words using IDE's pre-built word index. O(1) lookups, not file scanning.

**Returns**: `{ matches: [{file, line, column, context, contextType}], query }`

`contextType` values: `CODE`, `COMMENT`, `STRING_LITERAL`.
**Selection note**: exact-word only (uses word index, not regex). Use `Grep` for regex patterns.

### ide_find_implementations
Find flat implementation, inheritor, and override locations for a class/interface/trait/protocol or method — anchored at a declaration or a resolvable reference. For a subtype *tree*, use `ide_type_hierarchy` with `direction: "subtypes"`. Collected up to an internal per-cursor cap; `totalCollected` is a collected count.

**Returns**: `{ implementations: [{name, qualifiedName?, file, line, column, kind}], nextCursor?, hasMore, totalCollected, offset, pageSize, stale }`

**Languages**: Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

### ide_find_super_methods
Find IDE Go-to-Super targets for one anchor: methods/functions that override or implement a member; classes/interfaces/structs/traits and their direct supertypes; lambdas/SAMs; and overridden fields/properties/constants (plus Go interface satisfaction and Rust trait fn/const/type aliases).

**Returns**: `{ method: {name, qualifiedName?, kind, file, line, column}, hierarchy: [{name, qualifiedName?, kind, file?, line?, column?}] }`

**Languages**: Java, Kotlin, Python, JS/TS, PHP. Go returns interface methods a type satisfies. Rust returns trait fn/const/type alias the impl satisfies.

### ide_type_hierarchy
Get a depth-limited type inheritance hierarchy (supertypes and subtypes), up to `maxDepth` (default 5, max 20).

**Returns**: `{ element: {name, qualifiedName?, enclosingScope?, kind, file?, line?, column?, supertypes?}, supertypes: [{name, qualifiedName?, enclosingScope?, kind, file?, line?, column?, supertypes?}], subtypes: [{name, qualifiedName?, enclosingScope?, kind, file?, line?, column?, supertypes?}] }`

Provide either `className` (FQN, preferred where the language's qualified-name provider supports it) or `file`+`line`+`column`. **Rust:** `className` is not supported (use `file`+`line`+`column`), and the flat fallback ignores `maxDepth`. Unlike other read-only navigation tools, file mode does not resolve dependency/library absolute paths or `jar://` URLs.
**Languages**: Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

### ide_call_hierarchy
Build call tree showing who calls a method or what a method calls.

**Returns**: `{ element: {name, qualifiedName?, enclosingScope?, kind, file, line, column}, calls: [{name, qualifiedName?, enclosingScope?, kind, file, line, column, children?: [...]}] }`

**Languages**: Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

### ide_find_symbol
Search for methods, fields, functions, and other symbols by name (IDE Go to Symbol).

**Returns**: `{ symbols: [{name, qualifiedName?, kind, file, line, column}], query, nextCursor?, hasMore, totalCollected, offset, pageSize, stale }`

### ide_file_structure
Get the IDE Structure-view outline for a source file.

**Returns**: `{ file, language, structure }` — `structure` is a two-space-indented text tree beginning with the file name; each node renders modifiers, name, optional signature, and line number. Empty or no-structure files return a plain-text success message instead.

**Go note**: defaults include `package_structure`, so output can include declarations from other files in the same package; pass an explicit `show` list that omits `package_structure` to scope to the single file.

---

## Intelligence Tools

### ide_diagnostics
Unified diagnostics from any combination of per-file IDE analysis, cached last-build errors/warnings, and open test-run results. At least one of `file`, `includeBuildErrors`, or `includeTestResults` is required. Test results come from the first open test-run tab (see `testSummary.runConfigName`).

**Returns** (fields present depend on which sources were requested): `{ problems: [{message, severity, file, line, column, endLine?, endColumn?}], intentions: [{name, description?}], problemCount, intentionCount, analysisFresh, analysisTimedOut, analysisMessage, buildErrors?, buildErrorCount?, buildWarningCount?, buildErrorsTruncated?, buildTimestamp?, testResults?, testSummary?, testResultsTruncated? }`

`severity` values: `ERROR`, `WARNING`, `WEAK_WARNING`. Open files use fresh daemon highlights; closed files use public batch analysis so `WEAK_WARNING` results and quick-fix intentions may be less complete.

### ide_explain_symbol
Fused symbol overview in one call: declaration + signature + quick documentation + supers + implementations + usage summary. Anchor with `symbol` (name or qualified name) OR `file`+`line`+`column`; an ambiguous name returns `candidates` instead of guessing. `includeDiagnostics: true` adds problems overlapping the declaration (slower — runs a file analysis pass).

**Returns**: `{ symbol: {file, line, column, name, kind, preview, qualifiedName?, enclosingScope?}, candidates?, message?, signature?, documentation?, documentationTruncated?, supers?, implementations? (≤10), implementationsTruncated?, usageCount? (project files, counted to 200), usagesTruncated?, topUsages? (≤5), problems?, warnings? }`

Facets are capped summaries — page through `ide_find_implementations` / `ide_find_usages` for full sets. Degraded facets are named in `warnings`; a `null` facet means not applicable or not requested, `[]` means searched-and-empty.

---

## Refactoring Tools

### ide_refactor_rename
Rename a symbol and update ALL references (semantic rename, not find-replace). Works across ALL languages. Disabled by default; enable in Settings → Tools → IdeSense.

**Returns**: `{ success, affectedFiles: [paths], changesCount, message }`

Auto-renames getters/setters, overriding methods, constructor params ↔ fields, test classes. Supports IDE undo (Ctrl+Z).

### ide_move_file
Move a file to a new directory. Language-aware reference, import, and package/namespace updates when the IDE provides a semantic move backend for that file type. Disabled by default; enable in Settings → Tools → IdeSense.

**Returns**: `{ success, affectedFiles: [paths], changesCount, message }`

Supports IDE undo (Ctrl+Z).

---

## Project Tools

### ide_index_status
Check if IDE is ready for code intelligence operations.

**Returns**: `{ isDumbMode }` — `true` while the IDE is indexing (most tools fail); poll until `false`.

When `isDumbMode: true`, most tools will fail — wait and retry.

### ide_sync_files
Force sync IDE's virtual file system with external file changes.

**Returns**: `{ syncedPaths, syncedAll, message }`

Call when files were created or modified outside the IDE and search tools miss them.

---

## Other tools

The full tool set also includes `ide_read_file`,
`ide_install_plugin`, and `ide_restart`. Any tool can be
enabled or disabled in **Settings → Tools → IdeSense**, so `tools/list` is the source of
truth for what is callable right now. If a tool documented here is missing from `tools/list`, it is
disabled in this configuration — ask the user to enable it rather than falling back to a worse approach.
