# IdeSense - Tool Reference

This document provides detailed documentation for all MCP tools available in the IdeSense plugin.

## Tool Availability by IDE

Tools are organized into categories based on IDE compatibility:

### Universal Tools (All Supported JetBrains IDEs)

These tools work in every supported JetBrains IDE:

| Tool | Description | Default |
|------|-------------|---------|
| `ide_find_usages` | Find all references to a symbol | Enabled |
| `ide_find_definition` | Find symbol definition location | Enabled |
| `ide_find_class` | Search classes/interfaces by name | Enabled |
| `ide_find_file` | Search files by name | Enabled |
| `ide_find_symbol` | Search code symbols by name | Enabled |
| `ide_search_text` | Text search using word index | Enabled |
| `ide_diagnostics` | Analyze file problems with fresh IDE diagnostics, plus optional build/test results | Enabled |
| `ide_explain_symbol` | Fused symbol overview: declaration, signature, docs, supers, implementations, usage summary | Enabled |
| `ide_index_status` | Check indexing status | Enabled |
| `ide_sync_files` | Force sync VFS/PSI cache | Enabled |
| `ide_read_file` | Read file content by path or qualified name | Disabled |
| `ide_refactor_rename` | Rename symbol with reference updates (all languages) | Disabled |
| `ide_move_file` | Move file to new directory with IDE-aware move semantics | Disabled |
| `ide_install_plugin` | Install a locally built plugin `.zip` into this IDE (dev loop) | Disabled |
| `ide_restart` | Restart this IDE (pair with `ide_install_plugin`) | Disabled |

### Extended Tools (Language-Aware)

These tools give results for the languages in the table. The plugin always lists them, except `ide_find_super_methods`, which is listed only when the IDE has a plugin for one of its languages.

| Tool | Description | Languages |
|------|-------------|-----------|
| `ide_type_hierarchy` | Get type inheritance hierarchy | Java, Kotlin, Python, JS/TS, Go, PHP, Rust |
| `ide_call_hierarchy` | Analyze method call relationships | Java, Kotlin, Python, JS/TS, Go, PHP, Rust |
| `ide_find_implementations` | Find interface implementations | Java, Kotlin, Python, JS/TS, Go, PHP, Rust |
| `ide_find_super_methods` | Find overridden methods | Java, Kotlin, Python, JS/TS, PHP, Go, Rust |
| `ide_file_structure` | Hierarchical file structure | Java, Kotlin, Python, JS/TS, Go, PHP, Rust, Markdown |

---

## Table of Contents

- [Common Parameters](#common-parameters)
  - [Position Parameters](#position-parameters)
  - [Name Anchors](#name-anchors)
  - [Pagination and Result Size](#pagination-and-result-size)
- [Universal Tools](#universal-tools)
  - [ide_find_usages](#ide_find_usages)
  - [ide_find_definition](#ide_find_definition)
  - [ide_find_class](#ide_find_class)
  - [ide_find_file](#ide_find_file)
  - [ide_search_text](#ide_search_text)
  - [ide_diagnostics](#ide_diagnostics)
  - [ide_explain_symbol](#ide_explain_symbol)
  - [ide_index_status](#ide_index_status)
  - [ide_sync_files](#ide_sync_files)
  - [ide_read_file](#ide_read_file)
  - [ide_find_symbol](#ide_find_symbol)
  - [ide_install_plugin](#ide_install_plugin)
  - [ide_restart](#ide_restart)
- [Refactoring Tools](#refactoring-tools)
  - [ide_refactor_rename](#ide_refactor_rename-universal---all-languages)
  - [ide_move_file](#ide_move_file)
- [Extended Tools (Language-Aware)](#extended-tools-language-aware)
  - [ide_type_hierarchy](#ide_type_hierarchy)
  - [ide_call_hierarchy](#ide_call_hierarchy)
  - [ide_find_implementations](#ide_find_implementations)
  - [ide_find_super_methods](#ide_find_super_methods)
  - [ide_file_structure](#ide_file_structure)
- [Error Handling](#error-handling)

---

## Common Parameters

All tools accept an optional `project_path` parameter:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_path` | string | No | Absolute path to the project root. Required when multiple projects are open in the IDE. For a workspace project (one open project that holds sub-projects as modules with their own content root directories), use the sub-project path. |

### Position Parameters

Most tools operate on a specific location in code and require these parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `file` | string | For project files, path relative to project root (e.g., `src/main/java/MyClass.java`). `ide_read_file`, `ide_find_definition`, `ide_find_usages`, `ide_find_implementations`, `ide_find_super_methods`, `ide_call_hierarchy` and `ide_explain_symbol` also accept dependency/library paths returned by the plugin as absolute paths or `jar://` URLs. |
| `line` | integer | 1-based line number |
| `column` | integer | 1-based column number. For dotted expressions like `json.dumps()` or `os.path.join()`, point to the member token (`dumps`, `join`) when targeting the member definition. |

When `ide_find_usages`, `ide_call_hierarchy` or `ide_find_implementations` finds no symbol at `line`/`column`, the error message names up to 3 named elements of that line with their columns (or says that the line is blank). Retry with one of these columns.

### Name Anchors

`ide_find_usages`, `ide_call_hierarchy` and `ide_explain_symbol` (`symbol`) and `ide_type_hierarchy` (`className`) accept a name instead of a position:

- A declaration with the case of the name wins: `Handler` does not match a field `handler`. When no declaration has that case, the name is compared without case.
- When more than one declaration has the name, the tool returns a `candidates` list instead of a result. The list holds at most 10 declarations. The `message` gives the number of the matches, for example `103 matches, the first 10 are listed`. The search stops at 200 matches, and the message then gives a minimum: `200 or more matches`.
- Call again with a qualified name, or with the `file`/`line`/`column` of one candidate.

### Pagination and Result Size

Paginated tools (`ide_find_usages`, `ide_find_class`, `ide_find_file`, `ide_search_text`, `ide_find_implementations`, `ide_find_symbol`) return `nextCursor`, `hasMore`, `offset`, `pageSize`, `totalCollected` and `stale`:

- `pageSize` is the page size of the call (the requested value, or the value stored in the cursor). An empty page reports it too.
- `totalCollected` counts the results collected so far for this cursor. While `hasMore` is `true`, more results can exist, so the value is not a total.
- A cursor stops the collection at 5,000 results. After them `hasMore` is `false`, also when more results exist.
- `stale` is `true` when the PSI of the project (the IDE's code model) changed after the cursor was made. Search again for current results.
- A cursor expires 10 minutes after its last use. The server keeps at most 20 cursors. A new cursor then removes the cursor that was used least recently.
- An expired cursor returns `tool_error` with the message `Cursor expired. Please re-search.` An unknown or removed cursor returns `tool_error` with the message `Cursor not found. Please re-search.`
- `ide_find_usages` also returns `truncated`. Its value always equals `hasMore`.

Fields that quote a source line (`preview`, and `context` in `ide_search_text` matches) hold at most 200 characters of the line. A longer line, for example in a minified file, is cut to a 200-character window around the match, and `…` marks each cut end. Thus `pageSize` also bounds the size of a page.

---

## Universal Tools

These tools work in all JetBrains IDEs (IntelliJ, PyCharm, WebStorm, GoLand, etc.).

### ide_find_usages

Finds all references to a symbol across the entire project using IntelliJ's semantic index.

**Use when:**
- Locating where a method, class, variable, or field is called or accessed
- Understanding code dependencies
- Preparing for refactoring

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | No* | Symbol name or qualified name (e.g. `demo.UserService`, `UserService.authenticate`); alternative to `file`/`line`/`column`. An ambiguous name — including an overloaded method given without its parameter list — returns a `candidates` list instead of a result; `demo.Quirks#parse(java.lang.String)` selects one overload exactly. A file path is not a symbol. |
| `file` | string | No* | Project-relative file path, or a dependency/library absolute path or `jar://` URL previously returned by the plugin. |
| `line` | integer | No* | 1-based line number. |
| `column` | integer | No* | 1-based column number. |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files`. The last two follow the project's non-test and test source roots; in a project without such roots the tool returns a `scope_matches_no_files` error instead of an empty result. |
| `maxResults` | integer | No | Deprecated alias for `pageSize` (default: 100, max: 500) |
| `cursor` | string | No | Pagination cursor from a previous response |
| `pageSize` | integer | No | Number of results per page (default: 100, max: 500) |

*Either `symbol` OR `file`/`line`/`column` must be provided on a fresh search; a `cursor` call needs neither.

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_find_usages",
    "arguments": {
      "file": "src/main/java/com/example/UserService.java",
      "line": 15,
      "column": 20
    }
  }
}
```

**Example Response:**

```json
{
  "usages": [
    {
      "file": "src/main/java/com/example/UserController.java",
      "line": 42,
      "column": 15,
      "preview": "userService.findUser(id)",
      "usageType": "METHOD_CALL",
      "enclosingScope": ["UserController", "getUser"]
    },
    {
      "file": "src/test/java/com/example/UserServiceTest.java",
      "line": 28,
      "column": 10,
      "preview": "service.findUser(\"test\")",
      "usageType": "METHOD_CALL",
      "enclosingScope": ["UserServiceTest", "testFindUser"]
    }
  ],
  "truncated": false,
  "nextCursor": null,
  "hasMore": false,
  "totalCollected": 2,
  "offset": 0,
  "pageSize": 100,
  "stale": false,
  "warnings": null
}
```

**Reference Types:**
- `METHOD_CALL` - Method invocation
- `FIELD_ACCESS` - Field read/write
- `REFERENCE` - General reference
- `IMPORT` - Import statement
- `PARAMETER` - Method parameter
- `VARIABLE` - Variable usage
- `COMMENT` - Usage inside a comment or a doc comment

**Usages in comments:** a usage inside a comment or a doc comment has the type `COMMENT` in
every language, before the type that the language gives. This is the "Usage in comments" group
of the IDE's Find Usages window. An example is `Shape` in the PHP doc comment
`/** @var Shape[] */`. `line` and `column` point at the word in the comment, not at the start of
the comment.

**Base declarations:** a Go, Java, JavaScript, Kotlin, PHP, Python, Rust or TypeScript member can
override or implement a base declaration. Then the result is the union of the usages of the
member and the usages of each base declaration. An example is a Go method that implements an
interface method. A call through an interface value refers to the interface method, but it can
run the method. The search collects the usages of the member itself before the usages of the
base declarations. Where the IDE asks its user whether to search the base member or hides
dynamic usages by default, the tool includes and marks both. An absent call site costs an agent
more than a marked extra row. For a Go method, GoLand also shows its notification "Looking for
usages of the interface methods" in the IDE window, as it does for Find Usages. The notification
stops when the user selects "Don't show again". For a PHP method, the search of each base method
also covers the other methods that override or implement that base method, as the answer "Base
Method" of PhpStorm does. An example is a method of a class that implements an interface method:
the result also holds the calls on a value of another class that implements the interface method.

**Overriding declarations:** for a PHP method, the result also holds the usages of each method
that overrides or implements it, as Find Usages of PhpStorm lists them. An example is an interface
method: a call on a value whose type is an implementing class refers to the method of that class.
The search collects these usages after the usages of the base declarations. The declarations of
the overriding methods are not in the result; `ide_find_implementations` lists them.

**Match:** a usage that is not a sure usage of the symbol has the field `match`:
- No `match` key - the usage refers to the symbol itself.
- `BASE` - the usage refers to a base declaration, or to another declaration that overrides or
  implements a base declaration. It is a call on a value of the base type, which can run this
  symbol or another implementation, or a call on a value of another type that implements the
  base declaration.
- `OVERRIDE` - the usage refers to a PHP method that overrides or implements the symbol. It is a
  call on a value whose type has that overriding method.
- `DYNAMIC` - only the name matches, and the type of the receiver is not known. In all
  languages, a reference that does not resolve to a declaration has this mark. In JavaScript and
  TypeScript, a usage that WebStorm counts as a dynamic usage also has it. An example is a call
  `x.send()` on a value with no known type. A symbol name in a code span of a Markdown file also
  has it: only the name matches there.

**Notes:** `notes` is on the first page of a fresh search. It has these entries, in this order:

1. When the symbol overrides or implements base declarations: the entry names the base
   declarations and gives the count of the collected usages that have `match: BASE`.
2. When the search also covers the declarations that override or implement the symbol (a PHP
   method): the entry names them and gives the count of the collected usages that have
   `match: OVERRIDE`.
3. When the search does not search a base method on purpose (a method of the Python class
   `object`): `The base method <qualified name> is not searched: each class is a subclass of
   object.`, one sentence for each base method.
4. One entry for each kind of usage that the result leaves out, with the count. When the search
   stopped at its limit, the count is `<n> or more`.
   - Go, for a type: `<n> composite literal keys that name a struct field with the same name as
     this type are not in the list.` Such a key refers to the field, not to the type. A key of an
     embedded field stays in the list.
   - PHP, for a class: `<n> references to this class through $this, self or static inside the
     class are not in the list.` The Find Usages window of PhpStorm also hides these references
     by default.

An example for the JavaScript method `area` that overrides `Shape.area`:

```json
"notes": [
  "'area' overrides or implements Shape.area (src/normal.js:16:5). The result also holds the usages of this base declaration, because a call through it can run 'area'. 1 of the 5 usages has match BASE."
]
```

The key is absent when it has no entry.

**Degraded searches:** if the language's find-usages handler throws mid-expansion (e.g.
broken library roots), the search continues on the remaining targets and `warnings` lists
each failed stage (`primaryElements` / `secondaryElements` / `findReferencesToHighlight`, or
`processElementUsages` in Go) so partial coverage is visible instead of looking like a complete
result. If the handler factory of the language throws while it creates the handler, the tool
searches only the references to the anchor element, and `warnings` has the entry `Find-usages
handler factory <Name> threw while creating the handler; searched the references to the anchor
element only — usages may be incomplete.` `warnings` is `null` when the search ran complete; it
is reported on the first page of a fresh search.

---

### ide_find_definition

Finds the definition/declaration location of a symbol at a given source location.

**Use when:**
- Understanding where a method, class, variable, or field is declared
- Looking up the original definition from a usage site

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | Project-relative file path, or a dependency/library absolute path or `jar://` URL previously returned by the plugin. |
| `line` | integer | Yes | 1-based line number. |
| `column` | integer | Yes | 1-based column number. |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_find_definition",
    "arguments": {
      "file": "src/main/java/com/example/App.java",
      "line": 25,
      "column": 12
    }
  }
}
```

**Example Response:**

```json
{
  "file": "src/main/java/com/example/UserService.java",
  "line": 15,
  "column": 17,
  "name": "findUser",
  "kind": "METHOD",
  "preview": "public User findUser(String id) {",
  "qualifiedName": "com.example.UserService.findUser",
  "enclosingScope": null
}
```

---

### ide_find_class

Searches for classes and interfaces by name using the IDE's class index.

**Use when:**
- Finding a class by name when you don't know the file path
- Discovering all classes matching a pattern

**Matching modes:**
- Exact (default): an exact name match without case (`"userservice"` matches `"UserService"`)
- With `fuzzySearch: true`:
  - Substring: `"Service"` matches `"UserService"`, `"OrderService"`
  - CamelCase: `"USvc"` matches `"UserService"`
  - Wildcard: `"User*Impl"` matches `"UserServiceImpl"`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes* | Search pattern. Required for a fresh search; ignored when `cursor` is provided. |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files`. The last two follow the project's non-test and test source roots; in a project without such roots the tool returns a `scope_matches_no_files` error instead of an empty result. |
| `language` | string | No | Filter by language (e.g., `"Kotlin"`, `"Java"`, `"Python"`). Case-insensitive |
| `fuzzySearch` | boolean | No | `false` (default) = exact, case-insensitive name match; `true` = IDE camelCase/substring matching (`USvc` → `UserService`) |
| `limit` | integer | No | Deprecated alias for `pageSize` (default: 25, max: 500) |
| `cursor` | string | No | Pagination cursor from a previous response |
| `pageSize` | integer | No | Number of results per page (default: 25, max: 500) |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_find_class",
    "arguments": {
      "query": "UserService",
      "language": "Kotlin",
      "scope": "project_files"
    }
  }
}
```

**Example Response:**

```json
{
  "classes": [
    {
      "name": "UserService",
      "qualifiedName": "com.example.service.UserService",
      "kind": "INTERFACE",
      "file": "src/main/kotlin/com/example/service/UserService.kt",
      "line": 12,
      "column": 18
    }
  ],
  "totalCollected": 1,
  "query": "UserService"
}
```

---

### ide_find_file

Searches for files by name using the IDE's file index.

**Use when:**
- Finding a file when you know part of its name
- Discovering test files, config files, etc.

**Matching:** CamelCase (`"USJ"` matches `"UserService.java"`), substring, and wildcard (`"*Test.kt"`).

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes* | File name pattern. Required for a fresh search; ignored when `cursor` is provided. |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files`. The last two follow the project's non-test and test source roots; in a project without such roots the tool returns a `scope_matches_no_files` error instead of an empty result. |
| `limit` | integer | No | Deprecated alias for `pageSize` (default: 25, max: 500) |
| `cursor` | string | No | Pagination cursor from a previous response |
| `pageSize` | integer | No | Number of results per page (default: 25, max: 500) |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_find_file",
    "arguments": {
      "query": "UserService",
      "scope": "project_and_libraries"
    }
  }
}
```

**Example Response:**

```json
{
  "files": [
    {
      "name": "UserService.kt",
      "path": "src/main/kotlin/com/example/service/UserService.kt",
      "directory": "src/main/kotlin/com/example/service"
    }
  ],
  "totalCollected": 1,
  "query": "UserService",
  "warnings": null
}
```

**Degraded searches:** if a file contributor throws mid-search, the remaining contributors
still run and `warnings` names the failed contributor, so partial coverage is visible
instead of looking like a complete result. `warnings` is `null` when the search ran
complete; it is reported on the first page of a fresh search.

---

### ide_search_text

Searches for text using the IDE's pre-built word index. Significantly faster than file scanning.

**Use when:**
- Searching for exact word occurrences across the codebase
- Finding string literals, comments, or code patterns
- Filtering searches by context (code only, comments only, strings only)

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes* | Exact word to search for (not a pattern/regex). Required for a fresh search; ignored when `cursor` is provided. |
| `context` | string | No | Where to search: `"code"`, `"comments"`, `"strings"`, or `"all"` (default). A filter keeps the matches whose `contextType` is `CODE`, `COMMENT` or `STRING_LITERAL`, so each match of `"all"` is in the filtered result of its label. `CODE` is each match outside a comment and a string literal, also in a file that is no program source. A result has one match for each line: a line with the word in two contexts has one match in `"all"` and one match in each of the two filtered results. |
| `caseSensitive` | boolean | No | Case sensitive search (default: true) |
| `cursor` | string | No | Pagination cursor from a previous response. When provided, returns the next page; search parameters are ignored. |
| `pageSize` | integer | No | Results per page (default: 100, max: 500) |
| `limit` | integer | No | Deprecated alias for `pageSize` (default: 100, max: 500) |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_search_text",
    "arguments": {
      "query": "TODO",
      "context": "comments"
    }
  }
}
```

**Example Response:**

```json
{
  "matches": [
    {
      "file": "src/main/kotlin/com/example/UserService.kt",
      "line": 42,
      "column": 8,
      "context": "// TODO: add caching",
      "contextType": "COMMENT"
    }
  ],
  "totalCollected": 1,
  "query": "TODO"
}
```

**Response Notes:**
- `line` and `column` point at the occurrence itself, also inside a multi-line comment or string.
- The match's `context` is its source line; a line longer than 200 characters is cut to a window around the match (see [Pagination and Result Size](#pagination-and-result-size)).

---

### ide_diagnostics

Analyzes code diagnostics from three sources:
- fresh per-file IDE analysis for problems (errors, warnings),
- optional build output from the last build,
- optional test results from open test run tabs.

File problems are collected through explicit daemon analysis, so they do not depend on the target project window being active. Intentions/quick fixes are best-effort and require the file to already be open in an editor.

**Use when:**
- Finding code issues in a file
- Checking code quality
- Identifying potential bugs
- Discovering available code improvements
- Reading recent build errors without parsing console output
- Inspecting failing tests from open test run tabs

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | No | Path to the file relative to project root. Optional — enables per-file code analysis when provided. At least one of `file`, `includeBuildErrors`, or `includeTestResults` must be active. |
| `line` | integer | No | 1-based line number for intention lookup (default: 1). Requires `file`. |
| `column` | integer | No | 1-based column number for intention lookup (default: 1). Requires `file`. |
| `startLine` | integer | No | Filter problems to start from this line. Requires `file`. |
| `endLine` | integer | No | Filter problems to end at this line. Requires `file`. |
| `includeBuildErrors` | boolean | No | Include errors/warnings from the last build (default: `false`) |
| `includeTestResults` | boolean | No | Include test results from open test run tabs (default: `false`) |
| `severity` | string | No | Filter diagnostics by `all`, `errors`, or `warnings` (default: `all`) |
| `testResultFilter` | string | No | Filter test results by `failed` or `all` (default: `failed`) |
| `maxBuildErrors` | integer | No | Maximum build messages to return (default: 100, max: 500) |
| `maxTestResults` | integer | No | Maximum test results to return (default: 100, max: 500) |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_diagnostics",
    "arguments": {
      "file": "src/main/java/com/example/UserService.java"
    }
  }
}
```

**Example Response:**

```json
{
  "problems": [
    {
      "message": "Cannot resolve symbol 'UnknownType'",
      "severity": "ERROR",
      "file": "src/main/java/com/example/UserService.java",
      "line": 12,
      "column": 9,
      "endLine": 12,
      "endColumn": 20
    }
  ],
  "intentions": [],
  "problemCount": 1,
  "intentionCount": 0,
  "analysisFresh": true,
  "analysisTimedOut": false,
  "analysisMessage": "Intentions are unavailable because the file is not open in an editor."
}
```

**Response Notes:**
- `analysisFresh = true` means the file problems came from a fresh explicit IDE analysis pass instead of cached editor highlights. It covers the analysis of the current file text only: right after the IDE starts, background SDK setup (for example Python interpreter skeletons) can still cause transient unresolved-import problems.
- `analysisTimedOut = true` means the file analysis budget was exceeded. `problems` and `problemCount` are then `null`, because the file is not known to be clean. Build/test sections may still be returned.
- `problems` holds at most 100 entries, and no field shows that the list was cut. `problemCount` counts the returned entries.
- `analysisMessage` explains degraded cases such as timeouts or missing live editor context for intentions.
- `line` and `column` affect intention lookup only; file problems are collected for the whole file, then filtered by `startLine` / `endLine` if provided.

**Severity Values:**
- `ERROR` - Compilation error
- `WARNING` - Potential problem
- `WEAK_WARNING` - Minor issue

---

### ide_explain_symbol

Explains a symbol in one round-trip by fusing the IDE's navigation and documentation engines:
declaration location, signature, quick documentation, supers, implementations, and a usage
summary. Anchors on either a symbol name/qualified name or an exact file position; an
ambiguous name returns a `candidates` list instead of guessing.

**Use when:**
- Answering "what is this thing?" without chaining `ide_find_definition` → `ide_find_super_methods` → `ide_find_implementations` → `ide_find_usages`
- You have a name (stack trace, review comment, task description) but no coordinates yet
- You want the declaration's signature or documentation, which no other tool returns

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | No* | Symbol name or qualified name (e.g. `UserService`, `demo.UserService`, `UserService.authenticate`). Mutually exclusive with `file`/`line`/`column`. |
| `file` | string | No* | Project-relative file path, or a dependency/library absolute path or `jar://` URL previously returned by the plugin. Use with `line` and `column`. |
| `line` | integer | No* | 1-based line number. |
| `column` | integer | No* | 1-based column number. |
| `includeDiagnostics` | boolean | No | Also analyze the declaration's file and return problems overlapping the declaration. Default: `false` (the analysis pass is slower). |

*Exactly one anchor form is required: either `symbol`, or all of `file`+`line`+`column`.

**Example Request:**

```json
{
  "symbol": "Shape"
}
```

**Example Response** (implementations/topUsages trimmed for brevity):

```json
{
  "symbol": {"file": "src/main/java/demo/Normal.java", "line": 15, "column": 16, "name": "Shape", "kind": "ABSTRACT_CLASS", "preview": "abstract class Shape {", "qualifiedName": "demo.Shape", "enclosingScope": null},
  "candidates": null,
  "message": null,
  "signature": "[java] demo\nabstract class Shape extends Object",
  "documentation": "demo\nabstract class Shape",
  "documentationTruncated": null,
  "supers": [],
  "implementations": [
    {"name": "Circle", "file": "src/main/java/demo/Normal.java", "line": 25, "column": 7, "kind": "CLASS", "qualifiedName": "demo.Circle"},
    {"name": "Rectangle", "file": "src/main/java/demo/Normal.java", "line": 43, "column": 7, "kind": "CLASS", "qualifiedName": "demo.Rectangle"}
  ],
  "implementationsTruncated": false,
  "usageCount": 11,
  "usagesTruncated": false,
  "topUsages": [
    {"file": "src/main/java/demo/Normal.java", "line": 25, "column": 22, "preview": "class Circle extends Shape implements Drawable {", "usageType": "REFERENCE", "enclosingScope": ["Circle"]},
    {"file": "src/main/java/demo/Normal.java", "line": 76, "column": 14, "preview": "void add(Shape shape) {", "usageType": "REFERENCE", "enclosingScope": ["ShapeCollection", "add", "shape"]}
  ],
  "problems": null,
  "warnings": null
}
```

**Response Notes:**
- Facets are capped summaries: `implementations` up to 10 (`implementationsTruncated`), `usageCount` counted up to 200 (`usagesTruncated`), `topUsages` up to 5, `documentation` up to 4000 characters (`documentationTruncated`). Page through the dedicated tools for full sets.
- A `null` facet means not applicable, not requested, or degraded (degradations are named in `warnings`); an empty list means searched-and-empty — the same convention as `ide_diagnostics`.
- Usage counting and implementation search run over project files; library usages are not counted.
- `usageCount` and `topUsages` come from the same search as `ide_find_usages`. For a Go, Java, JavaScript, Kotlin, PHP, Python, Rust or TypeScript member with base declarations, `usageCount` counts the same union as `ide_find_usages`. For a PHP method, `usageCount` also counts the usages of the methods that override or implement it. `usageCount` includes the `COMMENT` usages. `topUsages` lists the code usages with no `match` first, then the `BASE` usages, then the `OVERRIDE` usages, then the `DYNAMIC` usages, then the `COMMENT` usages. A `topUsages` row can have `match` (`BASE`, `OVERRIDE` or `DYNAMIC`), as in `ide_find_usages`.
- `usageCount` and `topUsages` do not hold a usage that `ide_find_usages` leaves out. `notes` (absent when it has no entry) has the same entries as the notes of `ide_find_usages` for the base methods that the search does not search and for each kind of usage that it leaves out.
- On an ambiguous `symbol`, only `candidates` and `message` are populated — re-call with a qualified name or position from the list.
- `problems` is only populated with `includeDiagnostics: true` and covers problems overlapping the declaration's line range.

---

### ide_index_status

Checks if the IDE is in dumb mode (indexing) or smart mode.

**Use when:**
- Checking if index-dependent operations will work
- Waiting for indexing to complete

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | | | No parameters required |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_index_status",
    "arguments": {}
  }
}
```

**Example Response:**

```json
{
  "isDumbMode": false
}
```

Without `project_path` while several projects are open, the tool returns the status of every open project. The top-level `isDumbMode` is then `true` when any project is indexing:

```json
{
  "isDumbMode": false,
  "projects": [
    { "name": "backend", "path": "/home/user/backend", "isDumbMode": false },
    { "name": "frontend", "path": "/home/user/frontend", "isDumbMode": false }
  ]
}
```

---

### ide_sync_files

Force the IDE to synchronize its virtual file system and PSI cache with external file changes.

**Use when:**
- Files were created, modified, or deleted outside the IDE (e.g., by coding agents)
- Other IDE tools report stale results or miss references in recently changed files

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `paths` | array of strings | No | File or directory paths relative to project root to sync. If omitted, syncs the entire project |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_sync_files",
    "arguments": {
      "paths": ["src/main/java/com/example/NewFile.java"]
    }
  }
}
```

**Example Response:**

```json
{
  "syncedPaths": ["src/main/java/com/example/NewFile.java"],
  "syncedAll": false,
  "message": "Synchronized 1 path(s)."
}
```

A requested path that the tool does not find is not in `syncedPaths`, and `message` names it after `Not found:`.

If a requested path is excluded from the project and is not part of a library, `message` names it: the IDE refreshes it, but it does not index or analyze it.

---

### ide_read_file

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Read file content by file path or fully qualified class name.

**Use when:**
- Reading library/dependency source code from JARs
- Looking up class source by qualified name (e.g., `java.util.ArrayList`)
- Reading project files with metadata

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | No* | File path (relative, absolute, or jar path with `!/` or `jar://`) |
| `qualifiedName` | string | No* | Fully qualified class name (e.g., `java.util.ArrayList`) |
| `startLine` | integer | No | Starting line (1-based, inclusive). Without `endLine`, the tool returns only this line. |
| `endLine` | integer | No | Ending line (1-based, inclusive). Requires `startLine`. |

*Either `file` or `qualifiedName` must be provided.

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_read_file",
    "arguments": {
      "qualifiedName": "java.util.ArrayList",
      "startLine": 1,
      "endLine": 50
    }
  }
}
```

**Example Response:**

```json
{
  "file": "jar:///path/to/jdk/src.zip!/java.base/java/util/ArrayList.java",
  "content": "...",
  "language": "JAVA",
  "lineCount": 1750,
  "startLine": 1,
  "endLine": 50,
  "isLibraryFile": true
}
```

---

### ide_find_symbol

Searches for code symbols (classes, interfaces, methods, fields, and functions) by name using the IDE's semantic index and IntelliJ's Go to Symbol matching.

**Use when:**
- Finding a class or interface by name (e.g., find "UserService")
- Locating methods across the codebase (e.g., find all "findById" methods)
- Discovering fields or constants by name
- Navigating to code when you know the symbol name but not the file location

**Supports Go to Symbol matching:**
- Exact (default): an exact name match without case
- With `fuzzySearch: true`:
  - Substring: "Service" matches "UserService", "OrderService"
  - CamelCase: "USvc" matches "UserService", "US" matches "UserService"
- Qualified queries: "BasicSolver.run" matches a method in its containing class or module

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes* | Search pattern. Required for a fresh search; ignored when `cursor` is provided. |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files`. The last two follow the project's non-test and test source roots; in a project without such roots the tool returns a `scope_matches_no_files` error instead of an empty result. |
| `language` | string | No | Filter by language (e.g., `"Kotlin"`, `"Java"`). Case-insensitive |
| `fuzzySearch` | boolean | No | When `true`, use the IDE's Go to Symbol fuzzy matching (camelCase + substring). When `false` (default), match the symbol name exactly, case-insensitively. |
| `cursor` | string | No | Pagination cursor from a previous response |
| `pageSize` | integer | No | Number of results per page (default: 25, max: 500) |
| `limit` | integer | No | Deprecated alias for `pageSize` (default: 25, max: 500) |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_find_symbol",
    "arguments": {
      "query": "UserService"
    }
  }
}
```

**Example Request (camelCase matching):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_find_symbol",
    "arguments": {
      "query": "USvc",
      "fuzzySearch": true,
      "pageSize": 50
    }
  }
}
```

**Example Response** (camelCase request):

```json
{
  "symbols": [
    {
      "name": "UserService",
      "qualifiedName": "com.example.service.UserService",
      "kind": "INTERFACE",
      "file": "src/main/java/com/example/service/UserService.java",
      "line": 12,
      "column": 18
    },
    {
      "name": "UserServiceImpl",
      "qualifiedName": "com.example.service.UserServiceImpl",
      "kind": "CLASS",
      "file": "src/main/java/com/example/service/UserServiceImpl.java",
      "line": 15,
      "column": 14
    }
  ],
  "totalCollected": 2,
  "query": "USvc"
}
```

**Kind Values:**
- `CLASS` - Concrete class
- `ABSTRACT_CLASS` - Abstract class
- `INTERFACE` - Interface
- `ENUM` - Enum type
- `ANNOTATION` - Annotation type
- `RECORD` - Record class (Java 16+)
- `METHOD` - Method
- `FIELD` - Field, for example a Rust struct field or a Python class attribute
- `FUNCTION` - Function
- `SYMBOL` - Generic symbol when the IDE contributor does not expose a more specific kind
- `DATA_CLASS`, `SEALED_CLASS`, `OBJECT` - Kotlin data class, sealed class, object
- `STRUCT` - Go or Rust struct
- `TRAIT` - PHP or Rust trait
- `ENUM_VARIANT`, `IMPL`, `MACRO`, `MODULE` - Rust enum variant, impl block, macro, module
- `CONSTANT` - Constant, for example a Rust `const` or a PHP class constant
- `PROPERTY`, `VARIABLE`, `TYPE_ALIAS`, `TYPE`, `PARAMETER`, `CONSTRUCTOR`, `PACKAGE`, `LABEL` - Other declarations

The list is open, and other values can occur. When the plugin does not map the IDE's name for an element type, `kind` is that name in upper case, with `_` for each space.

For Markdown heading outlines, use `ide_file_structure`.

---

### ide_install_plugin

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Install a locally built plugin distribution (`.zip`) into THIS IDE's custom plugins directory, replacing any existing copy of the same plugin. Used as half of the local plugin dev loop: build → `ide_install_plugin` → `ide_restart`.

The new code only takes effect after an IDE restart — call `ide_restart` afterward.

The zip must resolve inside the open project (symlinks followed); out-of-root paths are
rejected. When the target IDE has a different project open than the one the zip was built in,
copy the zip into that project first.

**Use when:**
- Deploying a freshly built plugin zip to the running IDE during development

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | No | Path to the plugin `.zip`. Absolute, or relative to the project root; must resolve inside the open project. Default: newest `*.zip` in `<project>/build/distributions/`. |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_install_plugin",
    "arguments": {}
  }
}
```

**Returns**: `{ "installed": true, "source": "/abs/path/plugin.zip", "pluginDir": "/abs/path/plugins/myplugin", "pluginId": "com.example.plugin", "pluginVersion": "1.0.0", "restartRequired": true, "message": "…" }`

---

### ide_restart

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Restart THIS IDE. Use after `ide_install_plugin` to load a freshly installed plugin build.

The restart is scheduled after this tool's response is flushed (default 2 s delay) so the MCP client receives the result before the connection drops. In remote-dev / serverMode the backend relaunches and the thin client reconnects automatically. If a modal dialog is open in the IDE, the restart waits until it closes; the server keeps answering meanwhile, and each further call queues one more restart.

**Use when:**
- Loading a freshly installed plugin build (pair with `ide_install_plugin`)

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `delaySeconds` | integer | No | Seconds to wait before restarting (lets the response flush). Default: 2. Range: 0–60. |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_restart",
    "arguments": {
      "delaySeconds": 5
    }
  }
}
```

**Returns**: `{ "restarting": true, "delaySeconds": 5, "message": "IDE will restart in 5s. …" }`

---

## Refactoring Tools

> **Note**: All refactoring tools modify source files. Changes can be undone with Ctrl/Cmd+Z.

### ide_refactor_rename (Universal - All Languages)

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Renames a symbol and updates all references across the project. This tool uses IntelliJ's `RenameProcessor` which is language-agnostic and works across **all languages** supported by your IDE.

**Supported Languages:** Java, Kotlin, Python, JavaScript, TypeScript, Go, PHP, Rust, Ruby, and any language with IntelliJ plugin support.

**Features:**
- Language-specific name validation (identifier rules, keyword detection)
- **Headless with the default strategies** (no popups or dialogs)
- **Automatic related element renaming** - getters/setters, overriding methods, test classes are renamed automatically
- Conflict detection before rename execution (returns error instead of showing dialog)
- Single atomic operation - all renames (primary + related) can be undone with one Ctrl/Cmd+Z

**Use when:**
- Renaming identifiers to improve code clarity
- Following naming conventions
- Refactoring code structure

**Two modes:**
- **Symbol rename**: provide `file` + `line` + `column` + `newName`. Renames the symbol at the caret and all its references.
- **File rename**: provide `file` + `newName`, omit `line`/`column`. Works for all file types including binary files and Android resource files (updates XML references across the project).

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | Path to the file relative to project root |
| `line` | integer | No | 1-based line number. Required for symbol rename; omit for file rename. |
| `column` | integer | No | 1-based column number. Required for symbol rename; omit for file rename. |
| `newName` | string | Yes | The new name for the symbol or file. For file renames, include the file extension (e.g., `"new_name.webp"`). |
| `overrideStrategy` | string | No | How to handle overriding methods: `"rename_base"` (default), `"rename_only_current"`, or `"ask"`. `"ask"` shows an IDE dialog for an interactive choice, and the call waits until a person answers it at the IDE. |
| `relatedRenamingStrategy` | string | No | How to handle automatic renaming of related symbols: `"all"` (default), `"none"`, `"accessors_and_tests"`, or `"ask"`. `"ask"` shows an IDE dialog for an interactive choice, and the call waits until a person answers it at the IDE. |

**Example Request (Java):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_refactor_rename",
    "arguments": {
      "file": "src/main/java/com/example/UserService.java",
      "line": 15,
      "column": 17,
      "newName": "findUserById"
    }
  }
}
```

**Example Request (Python):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_refactor_rename",
    "arguments": {
      "file": "src/services/user_service.py",
      "line": 10,
      "column": 5,
      "newName": "fetch_user_data"
    }
  }
}
```

**Example Request (PHP):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_refactor_rename",
    "arguments": {
      "file": "src/Models/User.php",
      "line": 25,
      "column": 21,
      "newName": "getFullName"
    }
  }
}
```

**Example Request (file rename):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_refactor_rename",
    "arguments": {
      "file": "src/main/res/drawable/ic_launcher.webp",
      "newName": "ic_app_icon.webp"
    }
  }
}
```

**Example Response:**

```json
{
  "success": true,
  "affectedFiles": [
    "src/main/java/com/example/UserService.java",
    "src/main/java/com/example/UserController.java",
    "src/test/java/com/example/UserServiceTest.java"
  ],
  "changesCount": 3,
  "message": "Successfully renamed 'findUser' to 'findUserById' (also renamed 2 related element(s))"
}
```

**Automatic Related Renames:**

With the default strategies, related elements are renamed without any prompts or dialogs:

| Language | What Gets Auto-Renamed |
|----------|------------------------|
| Java/Kotlin | Getters/setters for fields, constructor parameters matching fields, overriding methods in subclasses, test classes |
| All Languages | Method implementations in subclasses, interface method implementations |

All renames happen in a single atomic operation, so one undo (Ctrl/Cmd+Z) reverts everything.

---

### ide_move_file

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Move a file to a new directory using the IDE's refactoring engine. Applies language-aware reference, import, and namespace/package updates when the IDE provides a semantic move backend for that file type.

**Supported Languages:** All project file types for literal file moves. Semantic updates depend on the active JetBrains language plugin. Java, Kotlin, and Python are known to provide file-move semantics; PHP class files are routed through PhpStorm's higher-level semantic move flow when available.

**Features:**
- Uses the IDE's file move refactoring for literal file relocation
- Applies semantic namespace/package/import updates when the language plugin supports them
- Routes PHP class-file moves through PhpStorm's semantic move dispatcher instead of the plain file-move backend
- Automatically creates destination directory if it doesn't exist
- Detects name conflicts at the destination
- Fails fast for ambiguous PHP semantic moves instead of reporting a false success

**Use when:**
- Reorganizing project structure
- Moving classes to different packages or namespaces when the IDE supports a semantic backend
- Relocating files while preserving IDE-managed references when available

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | Path to the source file to move, relative to project root |
| `destination` | string | Yes | Target directory path relative to project root |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_move_file",
    "arguments": {
      "file": "src/main/java/com/old/MyService.java",
      "destination": "src/main/java/com/new/services"
    }
  }
}
```

**Example Request (config file):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_move_file",
    "arguments": {
      "file": "config/old-config.yml",
      "destination": "config/archive"
    }
  }
}
```

**Example Response:**

```json
{
  "success": true,
  "affectedFiles": [
    "src/main/java/com/old/MyService.java",
    "src/main/java/com/new/services/MyService.java"
  ],
  "changesCount": 2,
  "message": "Successfully moved 'src/main/java/com/old/MyService.java' to 'src/main/java/com/new/services/MyService.java' using IDE file move semantics"
}
```

---

## Extended Tools (Language-Aware)

These tools give results for a language when the IDE has its plugin:
- **Java/Kotlin** - IntelliJ IDEA, Android Studio
- **Python** - PyCharm (all editions), IntelliJ with Python plugin
- **JavaScript/TypeScript** - WebStorm, IntelliJ Ultimate, PhpStorm
- **Go** - GoLand, IntelliJ Ultimate with Go plugin
- **PHP** - PhpStorm, IntelliJ Ultimate with PHP plugin
- **Rust** - RustRover, IntelliJ Ultimate with Rust plugin, CLion
- **Markdown** - heading outlines in file structure for IDEs with the bundled Markdown plugin

The plugin always lists these tools, except `ide_find_super_methods`, which is listed only when the IDE has a plugin for one of its languages. Markdown file structure can appear even in IDEs without a code-language handler when the bundled Markdown plugin is enabled.

### ide_type_hierarchy

Retrieves a depth-limited type hierarchy (supertypes and subtypes) for a class or interface (up to `maxDepth`, default 5 / max 20).

**Use when:**
- Exploring class inheritance chains
- Understanding polymorphism
- Finding all subclasses or implementations
- Analyzing interface implementations

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | No* | Path to the file relative to project root |
| `line` | integer | No* | 1-based line number. Required if using `file`. |
| `column` | integer | No* | 1-based column number. Required if using `file`. |
| `className` | string | No* | Class name or qualified name (alternative to position); works on every language. An ambiguous name returns a `candidates` list instead of a hierarchy. |
| `direction` | string | No | Which direction to traverse: `"supertypes"` (ancestors), `"subtypes"` (descendants), or `"both"` (default). `"both"` returns the union of the supertypes and subtypes walks. |
| `maxDepth` | integer | No | How many levels deep to traverse (default: 5, max: 20) |
| `scope` | string | No | Hierarchy scope. One of `all` (default), `production`, `test`. (`production` = production sources only — empty in projects without production roots.) |

*Either `file`/`line`/`column` OR `className` must be provided.

**Example Request (by position):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_type_hierarchy",
    "arguments": {
      "file": "src/main/java/com/example/ArrayList.java",
      "line": 5,
      "column": 14
    }
  }
}
```

**Example Request (by class name - Java):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_type_hierarchy",
    "arguments": {
      "className": "java.util.ArrayList",
      "direction": "supertypes"
    }
  }
}
```

**Example Request (by class name - PHP):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_type_hierarchy",
    "arguments": {
      "className": "App\\Models\\User"
    }
  }
}
```

**Example Response:**

```json
{
  "element": {
    "name": "UserServiceImpl",
    "qualifiedName": "com.example.UserServiceImpl",
    "kind": "CLASS",
    "file": "src/main/java/com/example/UserServiceImpl.java"
  },
  "supertypes": [
    {
      "name": "UserService",
      "qualifiedName": "com.example.UserService",
      "kind": "INTERFACE",
      "file": "src/main/java/com/example/UserService.java"
    },
    {
      "name": "BaseService",
      "qualifiedName": "com.example.BaseService",
      "kind": "ABSTRACT_CLASS",
      "file": "src/main/java/com/example/BaseService.java"
    }
  ],
  "subtypes": [
    {
      "name": "AdminUserServiceImpl",
      "qualifiedName": "com.example.AdminUserServiceImpl",
      "kind": "CLASS",
      "file": "src/main/java/com/example/AdminUserServiceImpl.java"
    }
  ]
}
```

**Response Notes:**
- `supertypes` is a tree. Each entry has its own `supertypes` list, down to `maxDepth` levels. The list is `null` when the entry has none.
- `subtypes` is one flat list of the subtypes, up to `maxDepth` levels. Its entries have no `supertypes` and no link to their parent.
- Each entry also has `line`, `column` and `enclosingScope`. `enclosingScope` is `null` when `qualifiedName` has a value.

**Kind Values:**
- `CLASS` - Concrete class
- `ABSTRACT_CLASS` - Abstract class
- `INTERFACE` - Interface
- `ENUM` - Enum type
- `ANNOTATION` - Annotation type
- `RECORD` - Record class (Java 16+)
- `DATA_CLASS`, `SEALED_CLASS`, `OBJECT` - Kotlin data class, sealed class, object
- `STRUCT` - Go or Rust struct
- `TRAIT` - PHP or Rust trait

The list is open, and other values can occur (see the kind values of [ide_find_symbol](#ide_find_symbol)).

---

### ide_call_hierarchy

Analyzes method call relationships to find callers or callees.

**Use when:**
- Tracing execution flow
- Understanding code dependencies
- Analyzing impact of method changes
- Debugging to understand how a method is reached

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | No* | Symbol name or qualified name (e.g. `demo.UserService`, `UserService.authenticate`); alternative to `file`/`line`/`column`. An ambiguous name — including an overloaded method given without its parameter list — returns a `candidates` list instead of a result; `demo.Quirks#parse(java.lang.String)` selects one overload exactly. A file path is not a symbol. |
| `file` | string | No* | Project-relative file path, or a dependency/library absolute path or `jar://` URL previously returned by the plugin. |
| `line` | integer | No* | 1-based line number. |
| `column` | integer | No* | 1-based column number. |
| `direction` | string | Yes | `"callers"` or `"callees"` |
| `maxDepth` | integer | No | How many levels deep to traverse (default: 3, max: 20) |
| `scope` | string | No | Hierarchy scope. One of `all` (default), `production`, `test`, `this_class`, `this_module`. (`production` = production sources only.) |

*Either `symbol` OR `file`/`line`/`column` (the declaration position) must be provided.

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_call_hierarchy",
    "arguments": {
      "file": "src/main/java/com/example/UserService.java",
      "line": 20,
      "column": 10,
      "direction": "callers"
    }
  }
}
```

**Example Response:**

```json
{
  "element": {
    "name": "validateUser",
    "qualifiedName": "com.example.UserService.validateUser",
    "kind": "METHOD",
    "file": "src/main/java/com/example/UserService.java",
    "line": 20,
    "column": 17
  },
  "calls": [
    {
      "name": "createUser",
      "qualifiedName": "com.example.UserController.createUser",
      "kind": "METHOD",
      "file": "src/main/java/com/example/UserController.java",
      "line": 45,
      "column": 17
    },
    {
      "name": "updateUser",
      "qualifiedName": "com.example.UserController.updateUser",
      "kind": "METHOD",
      "file": "src/main/java/com/example/UserController.java",
      "line": 62,
      "column": 17
    }
  ],
  "truncated": false
}
```

**Response Notes:**
- Each entry of `calls` holds the next level of the tree in `children` (its callers, or its callees). `children` is `null` when the entry has no next level.
- The tree holds at most 200 nodes, filled depth-first. When the walk reaches this limit, `truncated` is `true`, and the nodes after that point show no children, even if they have some. Then lower `maxDepth`, start from one caller, or use `ide_find_usages` (paginated) for the full flat list of direct callers.

---

### ide_find_implementations

Finds implementation, inheritor, and override locations for a class/interface/trait/protocol or method (anchored at a declaration or a resolvable reference). Only results whose file is in the `scope` are returned. A large result is paged: while `hasMore` is `true`, a cursor call continues the search. A Go method that a type gets through an embedded pointer is listed one time, at its declaration. An implementation that a Rust macro writes is listed at the macro call.

**Languages:** Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

**Use when:**
- Locating classes that implement an interface
- Finding classes that extend an abstract class
- Finding all overriding methods for polymorphic behavior analysis

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes* | Project-relative file path, or a dependency/library absolute path or `jar://` URL previously returned by the plugin. |
| `line` | integer | Yes* | 1-based line number. |
| `column` | integer | Yes* | 1-based column number. |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files`. The last two follow the project's non-test and test source roots; in a project without such roots the tool returns a `scope_matches_no_files` error instead of an empty result. |
| `cursor` | string | No | Pagination cursor from a previous response |
| `pageSize` | integer | No | Number of results per page (default: 100, max: 500) |

*Required for a fresh search; a `cursor` call needs none of them.

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_find_implementations",
    "arguments": {
      "file": "src/main/java/com/example/Repository.java",
      "line": 8,
      "column": 10
    }
  }
}
```

**Example Response:**

```json
{
  "implementations": [
    {
      "name": "JpaUserRepository",
      "qualifiedName": "com.example.JpaUserRepository",
      "file": "src/main/java/com/example/JpaUserRepository.java",
      "line": 12,
      "column": 14,
      "kind": "CLASS"
    },
    {
      "name": "InMemoryUserRepository",
      "qualifiedName": "com.example.InMemoryUserRepository",
      "file": "src/main/java/com/example/InMemoryUserRepository.java",
      "line": 8,
      "column": 14,
      "kind": "CLASS"
    }
  ],
  "nextCursor": null,
  "hasMore": false,
  "totalCollected": 2,
  "offset": 0,
  "pageSize": 100,
  "stale": false
}
```

---

### ide_find_super_methods

Finds IDE Go-to-Super targets for a code element — methods that override/implement a member, the direct supertypes of a class/interface/struct/trait, the SAM a lambda implements, or an overridden field/property/constant.

**Languages:** Java, Kotlin, Python, JS/TS, PHP, Go (returns interface method(s) a struct method satisfies), Rust (returns trait fn/const/type alias the impl satisfies).

**Go interface methods:** A method that a Go interface declares has no super method, so the result is that method with an empty hierarchy. At that position Go to Super of GoLand shows the interfaces that the enclosing type satisfies. A position on the type name returns them.

**Use when:**
- Finding which interface method an implementation overrides
- Navigating to the original method declaration in a parent class
- Understanding the full inheritance chain for a method with @Override
- Seeing all levels of method overriding (not just immediate parent)

**Position flexibility:** The position (line/column) can be anywhere within the method - on the name, inside the body, or on the @Override annotation. The tool automatically finds the enclosing method.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | Project-relative file path, or a dependency/library absolute path or `jar://` URL previously returned by the plugin. |
| `line` | integer | Yes | 1-based line number (any line within the method). |
| `column` | integer | Yes | 1-based column number (any position within the method). |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_find_super_methods",
    "arguments": {
      "file": "src/main/java/com/example/UserServiceImpl.java",
      "line": 25,
      "column": 10
    }
  }
}
```

**Example Response:**

```json
{
  "method": {
    "name": "findUser",
    "qualifiedName": "com.example.UserServiceImpl.findUser",
    "kind": "METHOD",
    "file": "src/main/java/com/example/UserServiceImpl.java",
    "line": 25,
    "column": 17
  },
  "hierarchy": [
    {
      "name": "findUser",
      "qualifiedName": "com.example.AbstractUserService.findUser",
      "kind": "METHOD",
      "file": "src/main/java/com/example/AbstractUserService.java",
      "line": 18,
      "column": 17
    },
    {
      "name": "findUser",
      "qualifiedName": "com.example.UserService.findUser",
      "kind": "METHOD",
      "file": "src/main/java/com/example/UserService.java",
      "line": 12,
      "column": 10
    }
  ]
}
```

**hierarchy entries** walk from the immediate parent upward; the first entry is the nearest ancestor that defines or declares the method.

**kind Values** (for both `method` and `hierarchy` entries):
- `METHOD` - Regular method
- `FUNCTION` - Function (dynamic languages)
- `FIELD` - Field or property override
- `CLASS`, `ABSTRACT_CLASS`, `INTERFACE`, `STRUCT` and the other class kinds of [ide_find_symbol](#ide_find_symbol) - A class-like anchor and its direct supertypes
- `CONSTANT`, `TYPE_ALIAS` - Rust trait constant or type alias

The list is open, and other values can occur.

---

### ide_file_structure

Get the hierarchical structure of a source file, similar to the IDE's Structure view (<kbd>Cmd+7</kbd> / <kbd>Alt+7</kbd>).

**Languages:** Java, Kotlin, Python, JavaScript, TypeScript, Go, PHP, Rust, Markdown.

**Use when:**
- Getting an overview of a file's classes, methods, fields, or Markdown heading outline
- Understanding code organization without reading the full file
- Navigating large files

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | Path to the file relative to project root |
| `show` | array of strings | No | Optional list of filter category names to show. Omit to use language defaults. Per-language values (* = on by default): python: `fields`*, `inherited`; java: `anonymous_classes`, `fields`*, `inherited`, `lambdas`*, `non_public`*; kotlin: `inherited`, `non_public`*, `properties`*; javascript/typescript: `fields`*, `inherited`, `inherited_from_object`*; php: `anonymous_classes`, `inherited`, `lambdas`*, `constants`*, `includes`*, `private_members`*, `properties`*, `protected_members`*; go: `package_structure`*, `private_members`*; rust: `macro_expanded`. |
| `sort` | string | No | Optional sort order. One of `"visibility"` (groups public/exported before non-public). Default: declaration order. No-op for Python and JS/TS. |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_file_structure",
    "arguments": {
      "file": "src/main/kotlin/com/example/UserService.kt"
    }
  }
}
```

**Example Response:**

```json
{
  "file": "src/main/kotlin/com/example/UserService.kt",
  "language": "Kotlin",
  "structure": "UserService.kt\n\ninterface UserService (line 15)\n  fun findUser(id: String): User (line 16)\n  fun deleteUser(id: String) (line 17)\nclass UserServiceImpl (line 20)\n  val repository: UserRepository (line 21)\n  override fun findUser(id: String): User (line 23)\n  override fun deleteUser(id: String) (line 30)\n  private fun validate(id: String) (line 37)"
}
```

**Response Notes:**
- `structure` starts with the file name and an empty line. Each node is `<modifiers> <name> [<signature>] (line N)`, indented two spaces for each level.
- A name is one line: each run of white space becomes one space. A name that had a line break (source text of several lines) and is longer than 80 characters is cut to 80 characters that end with `…`. A name with no line break stays complete, so a long signature stays whole. A JavaScript or TypeScript object literal that the IDE shows with no text, for example an object in an array, has the name `{}`.
- A signature is also one line: each run of white space becomes one space, and the text is not cut.
- A file with no structure returns plain text that starts with `File is empty or has no parseable structure.`, with no JSON.
- In dumb mode the tool returns `index_not_ready`, as the other tools that need the index. The Structure view of the IDE shows a reduced outline in dumb mode, for example a Java outline with no types.

---

## Error Handling

### JSON-RPC Standard Errors

| Code | Name | When It Occurs |
|------|------|----------------|
| -32700 | Parse Error | Invalid JSON in request |
| -32600 | Invalid Request | Missing required JSON-RPC fields |
| -32601 | Method Not Found | Unknown method or tool, or the tool is disabled in Settings (message: `Tool disabled by user settings: <name>. …`) |
| -32602 | Invalid Params | `params` or the tool `name` is absent (bad tool arguments return `invalid_arguments`) |
| -32603 | Internal Error | Unexpected server error |

### Tool Errors (resolved tool failures)

Pre-dispatch failures (parse error, unknown method, missing params) use JSON-RPC numeric error objects. Once a tool is dispatched and fails, it returns a **normal MCP result** with `isError: true` and a structured payload:

```json
{
  "error": "<snake_case_code>",
  "message": "<human-readable description>"
}
```

Common `error` codes:

| When It Occurs | Code |
|----------------|------|
| IDE is indexing (dumb mode) | `index_not_ready` |
| Parameter validation failed (a schema failure includes a `violations` array; a bad `symbol` or `file`/`line`/`column` anchor, for example both or neither, has only `message`) | `invalid_arguments` |
| The `scope` matches no files: the project has no production (or test) source roots | `scope_matches_no_files` |
| The IDE's index does not match a file (temporary, the IDE rebuilds it; retry later) | `index_out_of_sync` |
| Generic tool failure | `tool_error` |
| Unexpected server error | `internal_error` |
| Project resolution errors | `no_project_open` / `project_not_found` / `multiple_projects_open` |

A missing file, a symbol that is not found and a rename conflict return `tool_error`. The `message` names the cause.

For a `file` that the IDE does not find, `ide_file_structure`, `ide_diagnostics`, `ide_read_file` and `ide_refactor_rename` give the message `File not found: <path>. If the file exists on the disk, the IDE does not know it yet: call ide_sync_files, then call again.` `ide_file_structure`, `ide_read_file` and `ide_refactor_rename` do not refresh the file system for the `file`: a file that was created outside the IDE gives this error until `ide_sync_files` makes it known.

### Example Tool Error Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "isError": true,
    "content": [
      {
        "type": "text",
        "text": "{\"error\":\"index_not_ready\",\"message\":\"IDE is in dumb mode, indexes not available. Wait for the end of the indexing (ide_index_status shows isDumbMode: false), then call again.\"}"
      }
    ],
    "structuredContent": {
      "error": "index_not_ready",
      "message": "IDE is in dumb mode, indexes not available. Wait for the end of the indexing (ide_index_status shows isDumbMode: false), then call again."
    }
  }
}
```

### Handling Dumb Mode

Before calling index-dependent tools, you can check the index status:

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_index_status",
    "arguments": {}
  }
}
```

If `isDumbMode` is `true`, wait and retry later.

After its dumb mode check, a tool that needs the index starts its search, and starts it again, only in smart mode: it waits for the end of a dumb mode or of a scan of the files, and it returns `index_not_ready` when the wait comes to 10 seconds. The analysis of `ide_diagnostics` and the rename or move of `ide_refactor_rename` and `ide_move_file` do not wait. During a scan of the files `isDumbMode` is `false`, but such a call can still return `index_not_ready`: wait and retry later.
