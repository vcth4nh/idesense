# IdeSense - Tools Reference

This reference documents **return shapes and tool selection** for the IDE MCP tools enabled by
default. Parameters are provided by the live JSON schema in `tools/list` — consult that payload
for parameter names, types, defaults, and enum values. The remaining tools are listed under
**Other tools** at the end.

**Path conventions**: file paths for project files are relative to the project root;
library/dependency paths returned by the plugin (absolute paths or `jar://` URLs) must
be passed back unchanged. Line and column numbers are **1-based**.

**`stale`**: each paginated tool returns this field. `true` means that the code of the project changed in the IDE after the first call of this search. Then the results can differ from the current code: search again with no `cursor`.

---

## Navigation Tools

### ide_find_usages
Find semantic references to a symbol (not text search). Anchor by `symbol` (name or qualified name) or by `file`+`line`+`column`; an ambiguous `symbol` returns `{ candidates, message }`. Paginated; `totalCollected` is a collected count (a cursor stops its collection at 5,000 usages; see Pagination in SKILL.md), not a guaranteed whole-project total — page with `hasMore`/`nextCursor`.

**Returns**: `{ usages: [{ file, line, column, preview, usageType, enclosingScope, match? }], truncated, nextCursor?, hasMore, totalCollected, offset, pageSize, stale, warnings?, notes? }` — non-null `warnings` (first page) means that the find-usages code of the IDE for this language failed in a part of the search. The search skipped that part, so the list can be incomplete: check with `ide_search_text`. `notes` (first page, absent when it has no entry) names the base declarations and gives the count of the `BASE` usages. An example: `'area' overrides or implements Shape.area (src/normal.js:16:5). The result also holds the usages of this base declaration, because a call through it can run 'area'. 1 of the 5 usages has match BASE.` After that entry, `notes` names the overriding declarations that the search also covers (for a PHP method), with the count of the `OVERRIDE` usages; each base method that the search does not search (`The base method <qualified name> is not searched: each class is a subclass of object.`, a method of the Python class `object`); and each kind of usage that the result leaves out, with the count (`<n> or more` when the search stopped after 5,000 usages):
- `<n> composite literal keys that name a struct field with the same name as this type are not in the list.` (Go, for a type: the key refers to the field. A key of an embedded field stays.)
- `<n> references to this class through $this, self or static inside the class are not in the list.` (PHP, for a class.)

**Base declarations**: a Go, Java, JavaScript, Kotlin, PHP, Python, Rust or TypeScript member can override or implement a base declaration. Then the result is the union of the usages of the member and the usages of each base declaration. The search collects the usages of the member itself before the usages of the base declarations. For a PHP method, the search of each base method also covers the other methods that override or implement that base method. For a PHP method, the result also holds the usages of each method that overrides or implements it, after the usages of the base declarations; the declarations of these methods are not in the result (`ide_find_implementations` lists them). `match` marks a usage that is not sure:
- no `match`: the usage refers to the symbol itself.
- `BASE`: the usage refers to a base declaration, or to another declaration that overrides or implements a base declaration. It is a call on a value of the base type, which can run this symbol or another implementation, or a call on a value of another type that implements the base declaration.
- `OVERRIDE`: the usage refers to a PHP method that overrides or implements this symbol. It is a call on a value whose type has that overriding method.
- `DYNAMIC`: only the name matches, and the type of the receiver is not known. In all languages, a reference that does not resolve to a declaration has this mark. In JavaScript and TypeScript, a reference that the language plugin cannot resolve to the symbol with certainty also has this mark. Examples are `s.area()` on a value with no known type, and a name in a string literal. A symbol name in a code span of a Markdown file also has this mark.

`usageType` values: `METHOD_CALL`, `FIELD_ACCESS`, `IMPORT`, `PARAMETER`, `VARIABLE`, `REFERENCE`, `COMMENT` (a usage inside a comment or a doc comment, in every language). Paginated (see Pagination in SKILL.md).

### ide_find_definition
Go to where a symbol is defined.

**Returns**: `{ file, line, column, name, kind, preview, qualifiedName?, enclosingScope? }`

Handles packages, compiled classes, and library sources (`jar://` URLs).

### ide_find_class
Search for class-like/type declarations by name using IDE's Go to Class index (Ctrl+N / Cmd+O equivalent): classes, interfaces, enums, records, structs, traits, objects, annotations, and similar type declarations. Not methods/fields/functions — use `ide_find_symbol` or `ide_search_text` for those.

**Returns**: `{ classes: [{name, qualifiedName?, kind, file, line?, column?}], query, nextCursor?, hasMore, totalCollected, offset, pageSize, stale }`

`line` and `column` are `null` for a class with no position, for example a compiled class that the IDE cannot match to the decompiled text of its class file.

Project results use relative paths; dependency/library results may use absolute paths or `jar://` URLs.
Exact (case-insensitive) by default; with `fuzzySearch: true`, IDE camelCase/substring matching applies (`USvc` → `UserService`).

### ide_find_file
Search for files by name using IDE's file index (Ctrl+Shift+N / Cmd+Shift+O equivalent).

**Returns**: `{ files: [{name, path, directory}], query, nextCursor?, hasMore, totalCollected, offset, pageSize, stale, warnings? }`. Non-null `warnings` (first page) means a file contributor failed and the list may be incomplete.

Project results use relative paths; dependency/library results may use absolute paths or `jar://` URLs.

### ide_search_text
Search for exact words using IDE's pre-built word index. O(1) lookups, not file scanning.

**Returns**: `{ matches: [{file, line, column, context, contextType}], query, nextCursor?, hasMore, totalCollected, offset, pageSize, stale }` — `line`/`column` point at the occurrence; `context` is its source line, cut to a 200-character window around the match when longer. The result has one match for each line. Other occurrences on that line are not listed.

`contextType` values: `CODE`, `COMMENT`, `STRING_LITERAL`.
**Selection note**: exact-word only (uses word index, not regex). Use `Grep` for regex patterns.

### ide_find_implementations
Find flat implementation, inheritor, and override locations for a class/interface/trait/protocol or method — anchored at a declaration or a resolvable reference. `ide_type_hierarchy` with `direction: "subtypes"` gives the subtypes, up to `maxDepth` levels, as a flat list with no parent links. A cursor stops its collection at 5,000 results; `totalCollected` is a collected count.

**Returns**: `{ implementations: [{name, qualifiedName?, file, line, column, kind}], nextCursor?, hasMore, totalCollected, offset, pageSize, stale }`

**Languages**: Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

### ide_find_super_methods
Find IDE Go-to-Super targets for one anchor: methods/functions that override or implement a member; classes/interfaces/structs/traits and their direct supertypes; lambdas/SAMs; and overridden fields/properties/constants (plus Go interface satisfaction and Rust trait fn/const/type aliases).

**Returns**: `{ method: {name, qualifiedName?, kind, file, line, column}, hierarchy: [{name, qualifiedName?, kind, file?, line?, column?}] }`

**Languages**: Java, Kotlin, Python, JS/TS, PHP. Go returns interface methods a type satisfies. Rust returns trait fn/const/type alias the impl satisfies.

### ide_type_hierarchy
Get a depth-limited type inheritance hierarchy (supertypes and subtypes), up to `maxDepth` (default 5, max 20).

**Returns**: `{ element: {name, qualifiedName?, enclosingScope?, kind, file?, line?, column?, supertypes?}, supertypes: [{name, qualifiedName?, enclosingScope?, kind, file?, line?, column?, supertypes?}], subtypes: [{name, qualifiedName?, enclosingScope?, kind, file?, line?, column?, supertypes?}] }`

`supertypes` is a tree. Each entry holds its own `supertypes`, down to `maxDepth` levels. `subtypes` is a flat list. Its entries have no `supertypes` and no link to their parent.

Provide either `className` (name or qualified name; works on every language, an ambiguous name returns `{ candidates, message }`) or `file`+`line`+`column`. **Rust:** the tool returns one level only, whatever `maxDepth` is. For a trait, `supertypes` is empty, because the tool does not find the supertraits, and `subtypes` has the types that implement it. For a struct or an enum, `supertypes` has the traits of its `impl <Trait> for <Type>` blocks. Like `ide_file_structure`, file mode accepts project files only.
**Languages**: Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

### ide_call_hierarchy
Build call tree showing who calls a method or what a method calls. Anchor by `symbol` (name or qualified name) or by the declaration position `file`+`line`+`column`; an ambiguous `symbol` returns `{ candidates, message }`.

**Returns**: `{ element: {name, qualifiedName?, enclosingScope?, kind, file, line, column}, calls: [{name, qualifiedName?, enclosingScope?, kind, file, line, column, children?: [...]}], truncated }` — `maxDepth` defaults to 3; the tree holds at most 200 nodes (depth-first), and `truncated: true` means that the walk reached this limit: the nodes after that point show no children, even if they have some.

**Languages**: Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

### ide_find_symbol
Search for methods, fields, functions, and other symbols by name (IDE Go to Symbol).

**Returns**: `{ symbols: [{name, qualifiedName?, kind, file, line, column}], query, nextCursor?, hasMore, totalCollected, offset, pageSize, stale }`

### ide_file_structure
Get the IDE Structure-view outline for a source file.

**Returns**: `{ file, language, structure }` — `structure` is a two-space-indented text tree beginning with the file name; each node renders modifiers, name, optional signature, and line number. Empty or no-structure files return a plain-text success message instead.

A name is one line: each run of white space becomes one space. A name that had a line break (source text of several lines) and is longer than 80 characters is cut at 80 characters and ends with `…`; a name with no line break stays complete, so a long signature stays whole. A JavaScript/TypeScript object literal with no text in the IDE (for example an object in an array) has the name `{}`. A signature is also one line: the white space at its two ends goes away, and then the rule of a name applies (a signature that had a line break and is longer than 80 characters is cut at 80 characters and ends with `…`; a signature with no line break stays complete).

**Go note**: defaults include `package_structure`, so output can include declarations from other files in the same package; pass an explicit `show` list that omits `package_structure` to scope to the single file.

---

## Intelligence Tools

### ide_diagnostics
Unified diagnostics from any combination of per-file IDE analysis, cached last-build errors/warnings, and open test-run results. At least one of `file`, `includeBuildErrors`, or `includeTestResults` is required. Test results come from the first open test-run tab (see `testSummary.runConfigName`).

**Returns** (fields present depend on which sources were requested): `{ problems: [{message, severity, file, line, column, endLine?, endColumn?}], intentions: [{name, description?}], problemCount, intentionCount, analysisFresh, analysisTimedOut, analysisMessage, buildErrors?, buildErrorCount?, buildWarningCount?, buildErrorsTruncated?, buildTimestamp?, testResults?, testSummary?, testResultsTruncated? }`

`analysisFresh` is `true` when the tool analyzed the current file text in this call. When it is `false`, the tool has no analysis result for the file, so an empty `problems` list does not mean a clean file. `analysisMessage` is `null` when the file result is complete; else it says which results are absent or incomplete, and why. When `analysisTimedOut` is `true`, `problems` and `problemCount` are `null` (the file is not known to be clean). `severity` values: `ERROR`, `WARNING`, `WEAK_WARNING`. `problems` holds at most 100 entries and has no truncation flag. `problemCount` is the size of that list. If it is 100, call again with `startLine`/`endLine` or `severity`, because these filters apply before the limit. For a file that is open in an IDE editor, the tool runs the highlighting of that editor again and returns its problems. For a file that is not open in an IDE editor, the tool runs a batch analysis. Then `intentions` is empty, the result has no weak warnings, and `analysisMessage` says which results need the file open in an editor (intentions, and also weak warnings unless `severity` is `errors`).

### ide_explain_symbol
Fused symbol overview in one call: declaration + signature + quick documentation + supers + implementations + usage summary. Anchor with `symbol` (name or qualified name) OR `file`+`line`+`column`; an ambiguous name returns `candidates` instead of guessing. `includeDiagnostics: true` adds problems overlapping the declaration (slower — runs a file analysis pass).

**Returns**: `{ symbol: {file, line, column, name, kind, preview, qualifiedName?, enclosingScope?}, candidates?, message?, signature?, documentation?, documentationTruncated?, supers?, implementations? (≤10), implementationsTruncated?, usageCount? (project files, counted to 200), usagesTruncated?, topUsages? (≤5), problems? (≤50), warnings?, notes? }`

Facets are capped summaries — page through `ide_find_implementations` / `ide_find_usages` for full sets. Degraded facets are named in `warnings`; a `null` facet means not applicable or not requested, `[]` means searched-and-empty.

`usageCount` and `topUsages` come from the same search as `ide_find_usages`. For a Go, Java, JavaScript, Kotlin, PHP, Python, Rust or TypeScript member with base declarations, `usageCount` counts the same union. For a PHP method, `usageCount` also counts the usages of the methods that override or implement it. `topUsages` lists the code usages with no `match` first, then the `BASE` usages, then the `OVERRIDE` usages, then the `DYNAMIC` usages, then the `COMMENT` usages. A `topUsages` row can have `match` (`BASE`, `OVERRIDE` or `DYNAMIC`). `usageCount` and `topUsages` do not hold a usage that `ide_find_usages` leaves out; `notes` (absent when it has no entry) has the same entries as `ide_find_usages` for the base methods that the search does not search and for the usages that it leaves out, but its count is `<n> or more` when the search stopped after 200 usages.

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

**Returns**: `{ isDumbMode }` — `true` while the IDE is indexing (most tools fail); poll until `false`. During a scan of the files the value is `false`, but a tool can wait and then return `index_not_ready`. Without `project_path` while several projects are open: `{ isDumbMode, projects: [{name, path, isDumbMode}] }`, where the top-level value is `true` when any project is indexing.

### ide_sync_files
Force sync IDE's virtual file system with external file changes.

**Returns**: `{ syncedPaths, syncedAll, message }`

Call when files were created or modified outside the IDE and search tools miss them.

---

## Other tools

The full tool set also includes `ide_read_file`,
`ide_install_plugin`, and `ide_restart`. If a tool is missing from `tools/list`, see Tool Availability in SKILL.md.
