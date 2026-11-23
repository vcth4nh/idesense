---
name: idesense
description: >
  Guide for using JetBrains IdeSense tools for code navigation and analysis (plus the retained
  rename/move refactorings).
  TRIGGER: When ANY of these MCP tools are available in the current session: ide_find_usages,
  ide_find_definition, ide_find_class, ide_find_file, ide_search_text, ide_diagnostics,
  ide_explain_symbol, ide_index_status, ide_sync_files, ide_find_symbol, ide_file_structure,
  ide_type_hierarchy, ide_call_hierarchy, ide_find_implementations, ide_find_super_methods.
  Use when performing code navigation (find usages, go to definition, find class),
  code analysis (diagnostics, type hierarchy, call hierarchy),
  refactoring (rename, move),
  or searching code (text search, symbol search, file search).
  Prefer IDE tools over grep/find/sed for ALL semantic code operations.
---

# IdeSense - Agent Guide

The IdeSense server exposes JetBrains IDE indexing and analysis capabilities (plus rename/move refactoring). These tools provide **semantic** code understanding superior to text-based search/replace.

## Core Rule

**Always prefer IDE MCP tools over built-in tools (grep, find, sed) for semantic code operations.** IDE tools understand code structure, types, inheritance, and references. Built-in tools only see text.

## When to Use IDE Tools vs Built-In Tools

| Task | Use IDE Tool | Use Built-In Tool |
|------|-------------|-------------------|
| Find all usages of a method/class/variable | `ide_find_usages` | Never - grep misses renamed imports, aliases, overrides |
| Go to a symbol's definition | `ide_find_definition` | Never - grep can't resolve through imports/generics |
| Find a class by name | `ide_find_class` | Only if IDE unavailable |
| Find a file by name | `ide_find_file` | `Glob` is fine for simple patterns |
| Search for a word in code | `ide_search_text` | `Grep` is fine for regex patterns (IDE tool is exact-word only) |
| Rename a symbol across project | `ide_refactor_rename` | Never - sed/replace breaks code |
| Move a file to another directory | `ide_move_file` | Never - mv/git mv bypasses IDE move semantics |
| Check errors/warnings, build output, or test results | `ide_diagnostics` | Never - no equivalent |
| Understand class hierarchy | `ide_type_hierarchy` | Never - no equivalent |
| Find who calls a method | `ide_call_hierarchy` | Never - grep misses indirect calls |
| Find interface implementations | `ide_find_implementations` | Never - grep can't resolve type relationships |
| Find what a method overrides | `ide_find_super_methods` | Never - no equivalent |
| Read file content | `ide_read_file` (disabled by default) only for library/jar sources | Built-in Read tool |

## Pre-Flight Check

Before using any IDE tool that requires smart mode, check IDE readiness:

```
ide_index_status -> if isDumbMode: true, wait a few seconds and retry
index_not_ready  -> wait a few seconds and retry, also when isDumbMode is false (the IDE scans files)
ide_service_timeout -> a service of the IDE did not answer in its time limit; call again later
```

Most tools require smart mode (IDE finished indexing). Tools that work in dumb mode: `ide_index_status`, `ide_sync_files`. After its dumb mode check, a tool waits for the end of a dumb mode or of a scan of the files, and it returns `index_not_ready` when the wait comes to 10 seconds. The analysis of `ide_diagnostics` and the rename or move of `ide_refactor_rename` and `ide_move_file` do not wait. During each scan of the files `ide_index_status` shows `isDumbMode: false`, so a long scan can give `index_not_ready` while `isDumbMode` is `false`.

## File Sync Rule

If you created or modified files outside the IDE (via Write/Edit tools) and an IDE search tool returns incomplete/missing results, call `ide_sync_files` first, then retry.

The error `File not found: <path>. The file is on the disk, but the IDE does not know it yet: call ide_sync_files, then call again.` comes for a file of the project that is on the disk and that the IDE does not know yet: call `ide_sync_files` with that path, then call the tool again.

```json
{ "paths": ["src/new_file.java", "src/modified_file.java"] }
```

Omit `paths` to sync the entire project.

## Pagination

`ide_find_usages`, `ide_find_class`, `ide_find_file`, `ide_search_text`, `ide_find_implementations`, and `ide_find_symbol` return paginated results. The first response carries `nextCursor` and `hasMore` (`ide_find_usages` also includes a legacy `truncated` field mirroring `hasMore`). To fetch the next page, call the **same tool** again with `cursor: "<nextCursor>"` — on a cursor call the search arguments (query, file/line/column, scope) are ignored; only `cursor`, `pageSize`, and `project_path` are read. Stop when `hasMore` is `false`. For `ide_find_implementations`, a fresh search requires `file` + `line` + `column` together. `ide_find_usages` requires `symbol` or all three. The schema marks them optional so that cursor calls can omit them.

`totalCollected` counts the results collected so far for the cursor, not a project-wide total: while `hasMore` is `true`, more results can exist. A cursor stops the collection at 5,000 results. After them `hasMore` is `false`, also when more results exist. `pageSize` echoes the page size of the call. Fields that quote a source line (`preview`, the `context` of `ide_search_text` matches) hold at most 200 characters of the line, cut to a window around the match with `…` at each cut end, so `pageSize` also bounds the size of a page.

## Parameter Rules

1. **Line and column are 1-based** (first line = 1, first column = 1)
2. **Project file paths are relative** to project root (e.g., `src/main/java/App.java`, NOT absolute paths). If an IDE tool returns a dependency/library file, keep the returned path unchanged when passing it back to `ide_find_definition`, `ide_find_usages`, `ide_find_implementations`, `ide_find_super_methods`, `ide_call_hierarchy`, `ide_explain_symbol` or `ide_read_file` — it may be an absolute path, a `.jar!/` jar path, or a `jar://` URL. `ide_type_hierarchy` (file mode) and `ide_file_structure` accept project files only.
3. **Column must point to the symbol name**, not whitespace or punctuation. For `public void myMethod()`, column should land on `m` of `myMethod`. For dotted expressions like `json.dumps()` or `os.path.join()`, put the column on the member token (`dumps`, `join`) when you want the member definition rather than the module/package. For `ide_call_hierarchy`, anchor on the **declaration** of the target method/function/constructor: a column on a call site resolves to the *enclosing* function, not the callee — if you only have a call site, run `ide_find_definition` first and use the returned location — or pass `symbol` (name or qualified name) instead of a position: `ide_call_hierarchy` and `ide_find_usages` accept it, and an ambiguous name returns `candidates`. If the column misses, the errors of `ide_find_usages`, `ide_call_hierarchy` and `ide_find_implementations` list the named elements of that line with their columns; retry with one of them.
4. **project_path is only needed** when more than one project is open in the IDE. Omit it when one project is open. The `multiple_projects_open` error lists the open projects in `available_projects`. When needed, use the absolute path to the project root. In a workspace with sub-projects, the workspace root, a sub-project root and a directory below the workspace root all select the workspace project. `ide_sync_files` with a sub-project root and no `paths` syncs only that sub-project.
5. **Use search scope intentionally**: `ide_find_usages`, `ide_find_implementations`, `ide_find_class`, `ide_find_file`, and `ide_find_symbol` accept `scope`. Use `project_files` for the default project-only view, `project_and_libraries` when dependency code matters, `project_production_files` to stay out of tests, and `project_test_files` when you want test-only results. These two scopes follow the project's non-test and test source roots: in a project without such roots (common in Python projects with no marked sources root) the tool returns a `scope_matches_no_files` error, not an empty result — then omit `scope`. The hierarchy tools `ide_type_hierarchy` and `ide_call_hierarchy` use the IDE's native hierarchy scope instead: `all` (default), `production`, `test` (plus `this_class` and `this_module` for `ide_call_hierarchy`). This scope is IDE-native and provider-dependent: `production`/`test` narrow results only when the language's hierarchy provider honors those roots — otherwise they behave like `all` (type-hierarchy scope is currently a no-op in several languages).

## Tool Selection by Task

### "I need to understand how X is used"
1. `ide_find_usages` - all call sites, field accesses, imports. A usage with `match` is not sure. [tools-reference.md](references/tools-reference.md) (ide_find_usages) defines the marks `BASE`, `OVERRIDE` and `DYNAMIC`.
2. `ide_call_hierarchy` with `direction: "callers"` - full call chain upward

### "I need to understand what X is"
1. `ide_explain_symbol` - one-call fused overview: declaration + signature + docs + supers + implementations + usage summary; takes a name (`symbol`) or a position — start here
2. `ide_find_definition` - jump to source
3. `ide_type_hierarchy` - inheritance chain
4. `ide_find_super_methods` - what interface/base method it implements

### "I need to find a class/file/symbol"
1. `ide_find_class` - classes by name (exact by default; `fuzzySearch: true` for CamelCase: `USvc` finds `UserService`)
2. `ide_find_file` - files by name
3. `ide_search_text` - exact word occurrences across project
4. `ide_find_symbol` - methods, fields, functions, and other symbols by name

### "I need to refactor"
1. `ide_refactor_rename` - rename symbol + all references atomically *(disabled by default; enable in Settings → Tools → IdeSense)*
2. `ide_move_file` - move file and let the IDE apply semantic updates when that language/backend supports them *(disabled by default; enable in Settings → Tools → IdeSense)*

### "I need to check for problems"
1. `ide_diagnostics` - per-file errors/warnings (quick fixes only for a file open in an IDE editor); also cached last-build errors and open test-run results via `includeBuildErrors` / `includeTestResults` (at least one source required)

### "I need to find implementations of an interface"
1. `ide_find_implementations` - anchor on a class/interface/trait/protocol or method (declaration or resolvable reference); returns a flat list of implementations, inheritors, and overrides

### "I need to trace call chains"
1. `ide_call_hierarchy` with `direction: "callers"` - who calls this?
2. `ide_call_hierarchy` with `direction: "callees"` - what does this call?

## Common Mistakes to Avoid

1. **Using grep instead of `ide_find_usages`**: Grep finds text, not semantic usages. Misses aliased imports, includes false positives from comments/strings.

2. **Using sed/replace instead of `ide_refactor_rename`**: Text replacement breaks code. IDE rename updates all references, getters/setters, overrides, test classes, imports.

3. **Using mv/git mv instead of `ide_move_file`**: File system moves bypass IDE move semantics. `ide_move_file` can preserve IDE-managed package/namespace/reference updates when the active language backend supports them.

4. **Forgetting to check index status**: If IDE is indexing (dumb mode), most tools error. Check `ide_index_status` first if a tool fails unexpectedly.

5. **Using 0-based line/column**: All IDE tools use **1-based**. Line 5 in file = `line: 5`.

6. **Passing absolute project file paths**: Use relative paths for project files. `src/main/App.java`, not `/Users/me/project/src/main/App.java`.

7. **Rewriting plugin-returned library paths**: If a search or read tool returns a dependency/library path (an absolute path, a `.jar!/` jar path, or a `jar://` URL), pass that path back unchanged to the tools that Parameter Rules item 2 names.

8. **Not syncing after external file changes**: After creating files via Write tool, call `ide_sync_files` before searching.

9. **Asking for a deep call tree of a frequently called function**: `ide_call_hierarchy` (default `maxDepth` 3) holds at most 200 nodes. When the result has `truncated: true`, lower `maxDepth`, start from one caller, or use `ide_find_usages` for the full flat list of direct callers.

10. **Using `ide_find_class` for methods/functions**: It searches class-like/type declarations (classes, interfaces, enums, records, structs, traits, objects, annotations, and similar), not methods/fields/functions. Use `ide_find_symbol`, or `ide_search_text` for a quick word lookup.

## Tool Availability

`tools/list` is authoritative for what's callable in this session — any tool can be enabled or disabled in Settings → Tools → IdeSense. If a capability you need is documented (here or in [references/tools-reference.md](references/tools-reference.md)) but missing from `tools/list`, it is disabled in this config, or this IDE has no language plugin for it (`ide_find_super_methods` is listed only when the IDE has a plugin for one of its languages). Tell the user which tool you need instead of falling back to a worse approach.

## Return Shapes and Tool Selection

For return shapes and tool selection guidance, see [tools-reference.md](references/tools-reference.md).
