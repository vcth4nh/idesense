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
| `ide_find_symbol` | Search code symbols by name *(disabled by default)* | Disabled |
| `ide_search_text` | Text search using word index | Enabled |
| `ide_diagnostics` | Analyze file problems with fresh IDE diagnostics, plus optional build/test results | Enabled |
| `ide_index_status` | Check indexing status | Enabled |
| `ide_sync_files` | Force sync VFS/PSI cache | Enabled |
| `ide_build_project` | Build project with structured errors | Disabled |
| `ide_read_file` | Read file content by path or qualified name | Disabled |
| `ide_refactor_rename` | Rename symbol with reference updates (all languages) | Enabled |
| `ide_move_file` | Move file to new directory with IDE-aware move semantics | Enabled |
| `ide_reformat_code` | Reformat code using project code style | Disabled |
| `ide_optimize_imports` | Remove unused imports and organize remaining imports | Disabled |
| `ide_install_plugin` | Install a locally built plugin `.zip` into this IDE (dev loop) | Disabled |
| `ide_restart` | Restart this IDE (pair with `ide_install_plugin`) | Disabled |

### Extended Tools (Language-Aware)

These tools activate based on available language plugins:

| Tool | Description | Languages |
|------|-------------|-----------|
| `ide_type_hierarchy` | Get type inheritance hierarchy | Java, Kotlin, Python, JS/TS, Go, PHP, Rust |
| `ide_call_hierarchy` | Analyze method call relationships | Java, Kotlin, Python, JS/TS, Go, PHP, Rust |
| `ide_find_implementations` | Find interface implementations | Java, Kotlin, Python, JS/TS, Go, PHP, Rust |
| `ide_find_super_methods` | Find overridden methods | Java, Kotlin, Python, JS/TS, PHP, Go, Rust |
| `ide_file_structure` | Hierarchical file structure *(disabled by default)* | Java, Kotlin, Python, JS/TS, Go, PHP, Rust, Markdown |

### Java-Specific Refactoring Tools

| Tool | Description |
|------|-------------|
| `ide_convert_java_to_kotlin` | Convert Java files to Kotlin using the IDE converter *(disabled by default)* |
| `ide_refactor_safe_delete` | Safely delete with usage check |

---

## Table of Contents

- [Common Parameters](#common-parameters)
- [Universal Tools](#universal-tools)
  - [ide_find_usages](#ide_find_usages)
  - [ide_find_definition](#ide_find_definition)
  - [ide_find_class](#ide_find_class)
  - [ide_find_file](#ide_find_file)
  - [ide_search_text](#ide_search_text)
  - [ide_find_symbol](#ide_find_symbol)
  - [ide_diagnostics](#ide_diagnostics)
  - [ide_index_status](#ide_index_status)
  - [ide_sync_files](#ide_sync_files)
  - [ide_build_project](#ide_build_project)
  - [ide_install_plugin](#ide_install_plugin)
  - [ide_restart](#ide_restart)
  - [ide_read_file](#ide_read_file)
- [Refactoring Tools](#refactoring-tools)
  - [ide_optimize_imports](#ide_optimize_imports)
  - [ide_refactor_rename](#ide_refactor_rename)
  - [ide_move_file](#ide_move_file)
  - [ide_reformat_code](#ide_reformat_code)
- [Extended Tools (Language-Aware)](#extended-tools-language-aware)
  - [ide_type_hierarchy](#ide_type_hierarchy)
  - [ide_call_hierarchy](#ide_call_hierarchy)
  - [ide_find_implementations](#ide_find_implementations)
  - [ide_find_super_methods](#ide_find_super_methods)
  - [ide_file_structure](#ide_file_structure)
- [Java-Specific Refactoring Tools](#java-specific-refactoring-tools)
  - [ide_convert_java_to_kotlin](#ide_convert_java_to_kotlin)
  - [ide_refactor_safe_delete](#ide_refactor_safe_delete)
- [Error Handling](#error-handling)

---

## Common Parameters

All tools accept an optional `project_path` parameter:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_path` | string | No | Absolute path to the project root. Required when multiple projects are open in the IDE. For workspace projects, use the sub-project path. |

### Position Parameters

Most tools operate on a specific location in code and require these parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `file` | string | For project files, path relative to project root (e.g., `src/main/java/MyClass.java`). `ide_read_file` and read-only position-based navigation tools also accept dependency/library paths returned by the plugin as absolute paths or `jar://` URLs. |
| `line` | integer | 1-based line number |
| `column` | integer | 1-based column number. For dotted expressions like `json.dumps()` or `os.path.join()`, point to the member token (`dumps`, `join`) when targeting the member definition. |

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
| `file` | string | Yes | Project-relative file path, or a dependency/library absolute path or `jar://` URL previously returned by the plugin. |
| `line` | integer | Yes | 1-based line number. |
| `column` | integer | Yes | 1-based column number. |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files` |
| `maxResults` | integer | No | Deprecated alias for `pageSize` (default: 100, max: 500) |
| `cursor` | string | No | Pagination cursor from a previous response |
| `pageSize` | integer | No | Number of results per page (default: 100, max: 500) |

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
  "totalCount": 2,
  "truncated": false,
  "nextCursor": null,
  "hasMore": false,
  "totalCollected": 2,
  "offset": 0,
  "pageSize": 100,
  "stale": false
}
```

**Reference Types:**
- `METHOD_CALL` - Method invocation
- `FIELD_ACCESS` - Field read/write
- `REFERENCE` - General reference
- `IMPORT` - Import statement
- `PARAMETER` - Method parameter
- `VARIABLE` - Variable usage

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
  "preview": "14:     \n15:     public User findUser(String id) {\n16:         return userRepository.findById(id);\n17:     }",
  "qualifiedName": "com.example.UserService.findUser",
  "enclosingScope": ["UserService"]
}
```

**Path note:** Project results use relative paths. Dependency/library results may use absolute paths or `jar://` URLs.

---

### ide_find_class

Searches for classes and interfaces by name using the IDE's class index.

**Use when:**
- Finding a class by name when you don't know the file path
- Discovering all classes matching a pattern

**Matching modes:**
- Substring: `"Service"` matches `"UserService"`, `"OrderService"`
- CamelCase: `"USvc"` matches `"UserService"`
- Wildcard: `"User*Impl"` matches `"UserServiceImpl"`
- Exact: case-sensitive exact match

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search pattern |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files` |
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
  "totalCount": 1,
  "query": "UserService"
}
```

**Path note:** Project results use relative paths. Dependency/library results may use absolute paths or `jar://` URLs.

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
| `query` | string | Yes | File name pattern |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files` |
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
  "totalCount": 1,
  "query": "UserService"
}
```

**Path note:** Project results use relative paths. Dependency/library results may use absolute paths or `jar://` URLs.

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
| `context` | string | No | Where to search: `"code"`, `"comments"`, `"strings"`, or `"all"` (default) |
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
  "totalCount": 1,
  "query": "TODO"
}
```

---

### ide_diagnostics

> **Availability**: Universal Tool - works in all JetBrains IDEs

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
- `analysisFresh = true` means the file problems came from a fresh explicit IDE analysis pass instead of cached editor highlights.
- `analysisTimedOut = true` means the file analysis budget was exceeded; build/test sections may still be returned.
- `analysisMessage` explains degraded cases such as timeouts or missing live editor context for intentions.
- `line` and `column` affect intention lookup only; file problems are collected for the whole file, then filtered by `startLine` / `endLine` if provided.

**Severity Values:**
- `ERROR` - Compilation error
- `WARNING` - Potential problem
- `WEAK_WARNING` - Minor issue
- `INFO` - Informational

---

### ide_index_status

> **Availability**: Universal Tool - works in all JetBrains IDEs

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
  "isDumbMode": false,
  "isIndexing": false,
  "indexingProgress": null
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
  "message": "Synced 1 path(s)"
}
```

---

### ide_build_project

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Build the project using the IDE's build system (supports JPS, Gradle, Maven).

**Use when:**
- Checking for compilation errors after code changes
- Verifying that refactoring didn't break anything
- Getting structured error messages with file locations

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `rebuild` | boolean | No | Full rebuild instead of incremental build (default: false) |
| `includeRawOutput` | boolean | No | Include raw build output log (default: false) |
| `timeoutSeconds` | integer | No | Timeout in seconds. No timeout if omitted |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_build_project",
    "arguments": {}
  }
}
```

**Example Response:**

```json
{
  "success": false,
  "aborted": false,
  "errors": 1,
  "warnings": 2,
  "buildMessages": [
    {
      "category": "ERROR",
      "message": "Unresolved reference: fooBar",
      "file": "src/main/kotlin/com/example/App.kt",
      "line": 15,
      "column": 10
    }
  ],
  "truncated": false,
  "durationMs": 3200
}
```

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
| `startLine` | integer | No | Starting line (1-based, inclusive) |
| `endLine` | integer | No | Ending line (1-based, inclusive) |

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

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Searches for code symbols (classes, interfaces, methods, fields, and functions) by name using the IDE's semantic index and IntelliJ's Go to Symbol matching.

**Use when:**
- Finding a class or interface by name (e.g., find "UserService")
- Locating methods across the codebase (e.g., find all "findById" methods)
- Discovering fields or constants by name
- Navigating to code when you know the symbol name but not the file location

**Supports Go to Symbol matching:**
- Substring: "Service" matches "UserService", "OrderService"
- CamelCase: "USvc" matches "UserService", "US" matches "UserService"
- Qualified queries: "BasicSolver.run" matches a method in its containing class or module

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes* | Search pattern. Required for a fresh search; ignored when `cursor` is provided. |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files` |
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

**Example Response:**

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
    },
    {
      "name": "findUser",
      "qualifiedName": "com.example.service.UserService.findUser",
      "kind": "METHOD",
      "file": "src/main/java/com/example/service/UserService.java",
      "line": 18,
      "column": 10
    }
  ],
  "totalCount": 3,
  "query": "UserService"
}
```

**Path note:** Project results use relative paths. Dependency/library results may use absolute paths or `jar://` URLs.

**Kind Values:**
- `CLASS` - Concrete class
- `ABSTRACT_CLASS` - Abstract class
- `INTERFACE` - Interface
- `ENUM` - Enum type
- `ANNOTATION` - Annotation type
- `RECORD` - Record class (Java 16+)
- `METHOD` - Method
- `FIELD` - Field or constant
- `FUNCTION` - Function
- `SYMBOL` - Generic symbol when the IDE contributor does not expose a more specific kind

For Markdown heading outlines, use `ide_file_structure`.

---

### ide_install_plugin

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Install a locally built plugin distribution (`.zip`) into THIS IDE's custom plugins directory, replacing any existing copy of the same plugin. Used as half of the local plugin dev loop: build → `ide_install_plugin` → `ide_restart`.

The new code only takes effect after an IDE restart — call `ide_restart` afterward.

**Use when:**
- Deploying a freshly built plugin zip to the running IDE during development

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | No | Path to the plugin `.zip`. Absolute, or relative to the project root. Default: newest `*.zip` in `<project>/build/distributions/`. |

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

> **Disabled by default.** Enable in Settings > Tools > IdeSense.

---

### ide_restart

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Restart THIS IDE. Use after `ide_install_plugin` to load a freshly installed plugin build.

The restart is scheduled after this tool's response is flushed (default 2 s delay) so the MCP client receives the result before the connection drops. In remote-dev / serverMode the backend relaunches and the thin client reconnects automatically.

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

> **Disabled by default.** Enable in Settings > Tools > IdeSense.

---

## Refactoring Tools

> **Note**: All refactoring tools modify source files. Changes can be undone with Ctrl/Cmd+Z.

### ide_optimize_imports

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Optimize imports in a file: remove unused imports and organize remaining imports according to project code style. Equivalent to the IDE's "Optimize Imports" action (<kbd>Ctrl+Alt+O</kbd> / <kbd>Cmd+Opt+O</kbd>). Does NOT reformat code. Supports undo (Ctrl/Cmd+Z).

**Use when:**
- Removing unused imports after editing or refactoring
- Organizing imports without changing any formatting

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | File path relative to project root |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_optimize_imports",
    "arguments": {
      "file": "src/main/kotlin/com/example/UserService.kt"
    }
  }
}
```

**Returns**: `{ "success": true, "affectedFiles": ["src/…"], "changesCount": 1, "message": "Optimized imports in …" }`

> **Disabled by default.** Enable in Settings > Tools > IdeSense.

---

### ide_refactor_rename (Universal - All Languages)

Renames a symbol and updates all references across the project. This tool uses IntelliJ's `RenameProcessor` which is language-agnostic and works across **all languages** supported by your IDE.

**Supported Languages:** Java, Kotlin, Python, JavaScript, TypeScript, Go, PHP, Rust, Ruby, and any language with IntelliJ plugin support.

**Features:**
- Language-specific name validation (identifier rules, keyword detection)
- **Fully headless/autonomous operation** (no popups or dialogs)
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
| `overrideStrategy` | string | No | How to handle overriding methods: `"rename_base"` (default), `"rename_only_current"`, or `"ask"` |
| `relatedRenamingStrategy` | string | No | How to handle automatic renaming of related symbols: `"all"` (default), `"none"`, `"accessors_and_tests"`, or `"ask"` |

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

Related elements are automatically renamed without any prompts or dialogs:

| Language | What Gets Auto-Renamed |
|----------|------------------------|
| Java/Kotlin | Getters/setters for fields, constructor parameters matching fields, overriding methods in subclasses, test classes |
| All Languages | Method implementations in subclasses, interface method implementations |

All renames happen in a single atomic operation, so one undo (Ctrl/Cmd+Z) reverts everything.

---

### ide_move_file

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

### ide_reformat_code

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Reformat code according to the project's code style settings. Equivalent to the IDE's "Reformat Code" action (<kbd>Ctrl+Alt+L</kbd> / <kbd>Cmd+Opt+L</kbd>).

**Use when:**
- Applying consistent formatting after code changes
- Organizing imports
- Rearranging code members according to project rules

**Respects:** `.editorconfig`, project code style, language-specific formatting rules.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | File path relative to project root |
| `startLine` | integer | No | Start line for partial formatting (1-based). Requires `endLine` |
| `endLine` | integer | No | End line for partial formatting (1-based). Requires `startLine` |
| `optimizeImports` | boolean | No | Optimize imports (default: true) |
| `rearrangeCode` | boolean | No | Rearrange code members (default: true) |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_reformat_code",
    "arguments": {
      "file": "src/main/kotlin/com/example/UserService.kt"
    }
  }
}
```

**Example Response:**

```json
{
  "success": true,
  "affectedFiles": ["src/main/kotlin/com/example/UserService.kt"],
  "changesCount": 1,
  "message": "Reformatted code (optimized imports, rearranged code)"
}
```

---

## Extended Tools (Language-Aware)

These tools activate based on available language plugins:
- **Java/Kotlin** - IntelliJ IDEA, Android Studio
- **Python** - PyCharm (all editions), IntelliJ with Python plugin
- **JavaScript/TypeScript** - WebStorm, IntelliJ Ultimate, PhpStorm
- **Go** - GoLand, IntelliJ Ultimate with Go plugin
- **PHP** - PhpStorm, IntelliJ Ultimate with PHP plugin
- **Rust** - RustRover, IntelliJ Ultimate with Rust plugin, CLion
- **Markdown** - heading outlines in file structure for IDEs with the bundled Markdown plugin

Navigation tools appear according to installed language plugins. Markdown file structure can appear even in IDEs without a code-language handler when the bundled Markdown plugin is enabled.

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
| `className` | string | No* | Fully qualified class name (alternative to position) |
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

**Kind Values:**
- `CLASS` - Concrete class
- `ABSTRACT_CLASS` - Abstract class
- `INTERFACE` - Interface
- `ENUM` - Enum type
- `ANNOTATION` - Annotation type
- `RECORD` - Record class (Java 16+)

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
| `file` | string | Yes | Project-relative file path, or a dependency/library absolute path or `jar://` URL previously returned by the plugin. |
| `line` | integer | Yes | 1-based line number. |
| `column` | integer | Yes | 1-based column number. |
| `direction` | string | Yes | `"callers"` or `"callees"` |
| `maxDepth` | integer | No | How many levels deep to traverse (default: 7, max: 20) |
| `scope` | string | No | Hierarchy scope. One of `all` (default), `production`, `test`, `this_class`, `this_module`. (`production` = production sources only.) |

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
  ]
}
```

---

### ide_find_implementations

Finds implementation, inheritor, and override locations for a class/interface/trait/protocol or method (anchored at a declaration or a resolvable reference). Results are collected up to an internal per-cursor cap.

**Languages:** Java, Kotlin, Python, JS/TS, Go, PHP, Rust.

**Use when:**
- Locating classes that implement an interface
- Finding classes that extend an abstract class
- Finding all overriding methods for polymorphic behavior analysis

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | Project-relative file path, or a dependency/library absolute path or `jar://` URL previously returned by the plugin. |
| `line` | integer | Yes | 1-based line number. |
| `column` | integer | Yes | 1-based column number. |
| `scope` | string | No | Built-in search scope. One of `project_files` (default), `project_and_libraries`, `project_production_files`, `project_test_files` |
| `cursor` | string | No | Pagination cursor from a previous response |
| `pageSize` | integer | No | Number of results per page (default: 100, max: 500) |

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
  "totalCount": 2,
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

**Languages:** Java, Kotlin, Python, JS/TS, PHP, Go (returns interface method(s) a struct method satisfies via `GoSuperMethodSearch`), Rust (returns trait fn/const/type alias the impl satisfies via `RsGotoSuperHandlerKt.gotoSuperTargets`).

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

---

### ide_file_structure

> **Default**: Disabled - enable in Settings > Tools > IdeSense

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
  "structure": "interface UserService :15\n  fun findUser(id: String): User :16\n  fun deleteUser(id: String) :17\n\nclass UserServiceImpl :20\n  val repository: UserRepository :21\n  override fun findUser(id: String): User :23\n  override fun deleteUser(id: String) :30\n  private fun validate(id: String) :37"
}
```

---

## Java-Specific Refactoring Tools

These tools require the Java plugin and are only available in **IntelliJ IDEA** and **Android Studio**.

`ide_convert_java_to_kotlin` also requires the Kotlin plugin and is disabled by default.

### ide_convert_java_to_kotlin

> **Default**: Disabled - enable in Settings > Tools > IdeSense

Convert one or more Java files to Kotlin using IntelliJ's built-in J2K (Java-to-Kotlin) converter.

**Use when:**
- Migrating Java source files to Kotlin
- Converting a batch of related Java files in one request
- Letting the IDE handle syntax conversion, formatting, and import cleanup

**Features:**
- Supports batch conversion via a `files` array
- Uses the IDE's built-in converter instead of text transformation
- Automatically formats converted Kotlin files and optimizes imports
- Deletes original `.java` files after successful conversion
- Returns per-file results plus a summary of converted, skipped, and failed files

**Requirements:**
- Java plugin available
- Kotlin plugin enabled
- Files must belong to a module with Kotlin support enabled

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `files` | array of strings | Yes | Java file paths relative to project root |

**Example Request:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_convert_java_to_kotlin",
    "arguments": {
      "files": [
        "src/main/java/com/example/User.java",
        "src/main/java/com/example/UserService.java"
      ]
    }
  }
}
```

**Example Response:**

```json
{
  "files": [
    {
      "requestedPath": "src/main/java/com/example/User.java",
      "status": "CONVERTED",
      "kotlinFile": "src/main/java/com/example/User.kt",
      "linesConverted": 42,
      "javaFileDeleted": true
    },
    {
      "requestedPath": "src/main/java/com/example/UserService.java",
      "status": "SKIPPED",
      "reason": "Module 'app' does not have Kotlin plugin enabled"
    }
  ],
  "summary": {
    "totalRequested": 2,
    "converted": 1,
    "skipped": 1,
    "failed": 0
  }
}
```

**Status Values:**
- `CONVERTED` - Successfully converted to a new `.kt` file
- `SKIPPED` - File could not be attempted (for example not found, not a Java file, or no Kotlin-enabled module)
- `FAILED` - Conversion was attempted but did not produce a Kotlin file or hit a converter error

**Notes:**
- The tool returns structured per-file results in the same order as the input list
- Duplicate paths are reported separately
- Some advanced Java constructs may still need manual cleanup after conversion

### ide_refactor_safe_delete

Safely deletes a symbol or file, first checking for usages.

**Two modes:**
- **Symbol delete** (`target_type="symbol"`, default): deletes the symbol at the given position. Requires `file`, `line`, and `column`.
- **File delete** (`target_type="file"`): deletes the entire file if no symbols have external usages. Requires `file` only; internal call chains don't block deletion.

If usages exist and `force=false`, returns the blocking usage list instead of deleting.

**Use when:**
- Removing unused code
- Cleaning up dead code
- Safely removing methods, classes, or entire files

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | string | Yes | Path to the file relative to project root |
| `target_type` | string | No | What to delete: `"symbol"` (default, requires `line`+`column`) or `"file"` (deletes entire file if no external usages) |
| `line` | integer | No | 1-based line number. Required when `target_type="symbol"` (the default). |
| `column` | integer | No | 1-based column number. Required when `target_type="symbol"` (the default). |
| `force` | boolean | No | Force deletion even if usages exist (default: false) |

**Example Request (symbol delete):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_refactor_safe_delete",
    "arguments": {
      "file": "src/main/java/com/example/LegacyHelper.java",
      "line": 8,
      "column": 14
    }
  }
}
```

**Example Request (file delete):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "ide_refactor_safe_delete",
    "arguments": {
      "file": "src/main/java/com/example/OldUtil.java",
      "target_type": "file"
    }
  }
}
```

**Example Response (safe to delete):**

```json
{
  "success": true,
  "message": "Successfully deleted 'LegacyHelper'"
}
```

**Example Response (blocked by usages):**

```json
{
  "success": false,
  "message": "Cannot safely delete: 3 usages found",
  "blockingUsages": [
    {
      "file": "src/main/java/com/example/App.java",
      "line": 25,
      "context": "LegacyHelper.convert(data)"
    }
  ]
}
```

---

## Error Handling

### JSON-RPC Standard Errors

| Code | Name | When It Occurs |
|------|------|----------------|
| -32700 | Parse Error | Invalid JSON in request |
| -32600 | Invalid Request | Missing required JSON-RPC fields |
| -32601 | Method Not Found | Unknown tool or method name |
| -32602 | Invalid Params | Missing or invalid parameters |
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
| Specified file doesn't exist | `file_not_found` |
| No symbol at the specified position | `symbol_not_found` |
| Refactoring cannot be completed | `refactoring_conflict` |
| Parameter validation failed (includes a `violations` array) | `invalid_arguments` |
| Generic tool failure | `tool_error` |
| Unexpected server error | `internal_error` |
| Project resolution errors | `no_project_open` / `project_not_found` / `multiple_projects_open` |

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
        "text": "{\"error\":\"index_not_ready\",\"message\":\"IDE is in dumb mode, indexes not available. Please wait for indexing to complete.\"}"
      }
    ],
    "structuredContent": {
      "error": "index_not_ready",
      "message": "IDE is in dumb mode, indexes not available. Please wait for indexing to complete."
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
