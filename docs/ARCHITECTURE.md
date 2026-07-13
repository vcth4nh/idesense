# Architecture

## Tool → backing mechanism

Each tool delegates to a platform API. This is **not** uniformly an extension point —
some tools use a platform service, plain PSI/VFS, or a processor that itself iterates EPs.
The "verified against" column cites the exact call site so a future reader can re-check in one grep.

| Tool | Backing mechanism | verified against |
|---|---|---|
| `ide_find_usages` | EP: `FindUsagesHandlerFactory.EP_NAME` (Alt+F7 equivalence class) + `ReferencesSearch` fallback | `FindUsagesHandlerSearch.kt` / `FindUsagesTool.kt` |
| `ide_find_definition` | none — `PsiUtils.resolveTargetElement` → `PsiElement.navigationElement` (Ctrl+B) | `FindDefinitionTool.kt` |
| `ide_find_class` | headless Go-to-Class popup: `PopupFaithfulClassSearch` → `ChooseByNameModel` (Ctrl+N) | `FindClassTool.kt` / `PopupFaithfulClassSearch.kt` |
| `ide_find_file` | EP iteration: `ChooseByNameContributor.FILE_EP_NAME` (Go-to-File, Ctrl+Shift+N) | `FindFileTool.kt` |
| `ide_find_symbol` | headless Go-to-Symbol popup: `PopupFaithfulSymbolSearch` → `GotoSymbolModel2` (Ctrl+Alt+Shift+N) | `FindSymbolTool.kt` / `PopupFaithfulSymbolSearch.kt` |
| `ide_find_implementations` | EP: `DefinitionsScopedSearch.search()` (Ctrl+Alt+B) | `FindImplementationsTool.kt` |
| `ide_find_super_methods` | `LanguageServices.findSuperMethods()` — dispatches to `SuperMethodsProvider` EP per language (Ctrl+U) | `FindSuperMethodsTool.kt` / `handlers/LanguageServices.kt` |
| `ide_search_text` | service: `PsiSearchHelper.getInstance(project).processElementsWithWord` (word index) | `SearchTextTool.kt` |
| `ide_type_hierarchy` | EP: `LanguageTypeHierarchy` via `HierarchyTreeWalker`; Rust fallback: `RustTypeHierarchyFallback` (Strategy II) | `TypeHierarchyTool.kt` / `HierarchyTreeWalker.kt` |
| `ide_call_hierarchy` | EP: `LanguageCallHierarchy` via `HierarchyTreeWalker` | `CallHierarchyTool.kt` / `HierarchyTreeWalker.kt` |
| `ide_file_structure` | EP: `LanguageStructureViewBuilder` → `TreeModelWrapper` + `SmartTreeStructure` (Structure view) | `FileStructureTool.kt` |
| `ide_read_file` | none — `PsiUtils.resolveVirtualFileAnywhere` / `PsiManager.findFile` (VFS + PSI) | `ReadFileTool.kt` |
| `ide_diagnostics` | multiple: `DaemonCodeAnalyzerEx` (open files) + `CodeSmellDetector` (closed files) + `BuildDiagnosticsCacheService` + `TestResultsCollector` | `GetDiagnosticsTool.kt` / `DiagnosticsAnalysisService.kt` |
| `ide_index_status` | service: `DumbService.getInstance(project).isDumb` | `GetIndexStatusTool.kt` |
| `ide_sync_files` | none — `VfsUtil.markDirtyAndRefresh` + `LocalFileSystem` + `PsiDocumentManager.commitAllDocuments` | `SyncFilesTool.kt` |
| `ide_install_plugin` | none — `PathManager.getPluginsDir()` + JDK `ZipInputStream` (zip-slip guarded) | `InstallPluginTool.kt` |
| `ide_restart` | none — `ApplicationManagerEx.getApplicationEx().restart(true)` (scheduled via `AppExecutorUtil`) | `RestartIdeTool.kt` |
| `ide_refactor_rename` | `RenameProcessor` + `RenamePsiElementProcessor` EP + `AutomaticRenamerFactory` EP iteration | `RenameSymbolTool.kt` |
| `ide_move_file` | `MoveFilesOrDirectoriesProcessor` (delegates to `MoveFileHandler` EP per language; PHP class files route through PhpStorm's class-move processor) | `MoveFileTool.kt` |

## Core Design Principle: Mimic the IDE

Every tool should return what the IDE's own action or tool window would show for the
same input. Delegate to the platform's extension points and presentation APIs rather
than re-deriving behavior per language:

- Hierarchies → `LanguageCallHierarchy` / `LanguageTypeHierarchy` (drive the IDE's own
  `HierarchyProvider` browser headlessly), not hand-rolled per-language traversal
- Qualified names → `QualifiedNameProvider` extension point (same API as "Copy Reference")
- Display names → the element's own `ItemPresentation` / `ClassPresentationUtil`
- Find Usages → `FindUsagesHandlerFactory` (the Alt+F7 equivalence class)
- Search scope → map to the scope string the IDE selects by default for that action

Per-language reflection is a **last resort**, used only where the platform exposes no
universal API (most notably element `kind` — there is no `PsiElement.getKind()`, so
class/interface/struct/trait classification is unavoidably language-specific). When the
IDE's behavior changes between versions, faithfully mirroring it is correct — re-bless
snapshots rather than re-deriving.

**Escalate, don't decide silently.** Two situations require asking the user rather than
choosing unilaterally:

1. **Verification needs the IDE.** If correctness can't be judged from code alone —
   i.e. you can only tell whether output is right by comparing against what the IDE
   actually shows — surface it and ask the user to confirm against the running IDE.
   Don't bless a snapshot you can't independently justify.
2. **Mimic-vs-useful tension.** When faithfully mirroring the IDE (and staying
   language-agnostic) would withhold information that is genuinely more useful to the
   calling agent, do not quietly pick one. Present the tradeoff and let the user
   decide. "Mimic the IDE" is the default, not an absolute — usefulness can override
   it, but only with explicit sign-off.

## Key Documentation

### IntelliJ Platform SDK
- **Main Documentation**: https://plugins.jetbrains.com/docs/intellij/welcome.html
- **PSI (Program Structure Interface)**: https://plugins.jetbrains.com/docs/intellij/psi.html
- **Indexing and PSI Stubs**: https://plugins.jetbrains.com/docs/intellij/indexing-and-psi-stubs.html
- **Rename Refactoring**: https://plugins.jetbrains.com/docs/intellij/rename-refactoring.html
- **Modifying the PSI**: https://plugins.jetbrains.com/docs/intellij/modifying-psi.html
- **Plugin Configuration**: https://plugins.jetbrains.com/docs/intellij/plugin-configuration-file.html
- **Explore API**: https://plugins.jetbrains.com/docs/intellij/explore-api.html

### Model Context Protocol (MCP)
- **Tools API (2025-11-25 — structuredContent)**: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- **Specification (2025-03-26, also supported)**: https://spec.modelcontextprotocol.io/specification/2025-03-26/
- **Tools API (2025-03-26, also supported)**: https://modelcontextprotocol.io/specification/2025-03-26/server/tools
- **Resources API (2025-03-26)**: https://modelcontextprotocol.io/specification/2025-03-26/server/resources
- **Legacy SSE Transport**: https://spec.modelcontextprotocol.io/specification/2024-11-05/basic/transports/
- **GitHub**: https://github.com/modelcontextprotocol/modelcontextprotocol

## Project Structure

Package map under `src/main/kotlin/com/github/vcth4nh/idesense/`
(file list is `ls`-derivable — this documents *purpose*, which is not):

- `server/` — MCP infra: `McpServerService` (app-level lifecycle), `JsonRpcHandler`,
  `ProjectResolver` (multi-project/workspace), `transport/` (Ktor CIO + SSE), `models/`
- `tools/` — one class per MCP tool. `AbstractMcpTool` (auto VFS/PSI sync + threading;
  extend this and implement `doExecute()`), `ToolRegistry` (data-driven registration),
  `schema/SchemaBuilder` (all tool input schemas). Subpackages: `navigation/`,
  `intelligence/`, `project/` (incl. `InstallPluginTool`/`RestartIdeTool` dev-loop),
  `refactoring/`
- `tools/navigation/hierarchy/` — **IDE extension-point delegation** for
  `ide_call_hierarchy`/`ide_type_hierarchy`. `HierarchyTreeWalker` drives the IDE's own
  `HierarchyProvider` browser/tree-structure headlessly; `ClassLikePsi` is the cross-IDE
  PSI reflection layer (kind/qualifiedName/name without compile-time language deps);
  `HierarchyScope`; `RustTypeHierarchyFallback`/`Impl` (Strategy II — RustRover
  ships no type-hierarchy provider). See "Hierarchy Tools" below.
- `handlers/` — `LanguageServices` (object with `getKind`/`findSuperMethods` dispatch)
  backed by `LanguageKindResolver` and `SuperMethodsProvider` IntelliJ `LanguageExtension`
  EPs (registered in `plugin.xml`). Also: `PopupFaithfulSymbolSearch`/`ClassSearch`
  (headless Go-to-Symbol popup model), `SymbolDataConverter`, `LanguageDisplayName`,
  `BuiltInSearchScope*`, `FindUsagesHandlerSearch`, `HandlerDataClasses` (wire-format
  data classes).
- `util/` — `QualifiedNameUtil` (QualifiedNameProvider EP delegation + Go/Rust
  fallbacks), `ClassResolver`, `ProjectUtils`, `PsiUtils`, `PluginDetectors`,
  `ThreadingUtils`
- `settings/`, `startup/`, `ui/` — config + configurable, startup activities, tool-window UI
- `resources/META-INF/` — `plugin.xml` + optional `*-features.xml` language extensions

Tests: `src/test/kotlin` (`*UnitTest` = `TestCase`, no platform; `*Test` =
`BasePlatformTestCase`), fixtures in `src/test/testData/`, live harness in `live-test/`.

## Architecture Concepts

### IntelliJ Platform Key Components

1. **PSI (Program Structure Interface)**
   - Core abstraction for parsing and representing code structure
   - `PsiFile`, `PsiElement`, `PsiClass`, `PsiMethod`, etc.
   - `PsiNamedElement` for elements that can be renamed/referenced

2. **Indexes**
   - `DumbService` - query if IDE is in dumb mode (indexing) vs smart mode
   - File-based indexes for fast lookups
   - PSI stubs for lightweight syntax trees

3. **Refactoring APIs**
   - `RenameHandler` - custom rename UI/workflow
   - `PsiNamedElement.setName()` - rename element
   - `PsiReference.handleElementRename()` - update references

4. **Services**
   - Application-level services (singleton across IDE)
   - Project-level services (one per open project)

### Workspace / Multi-Module Project Support

The plugin supports workspace projects where a single IDE window contains multiple sub-projects
represented as modules with separate content roots:

- **Project resolution** (`ProjectResolver.resolve`): Checks exact basePath → module content roots → subdirectory match
- **File resolution** (`AbstractMcpTool.resolveFile`): Tries basePath, then module content roots
- **Relative path computation** (`ProjectUtils.getRelativePath`): Strips the matching content root prefix
- **VFS/PSI sync** (`AbstractMcpTool.ensurePsiUpToDate`): Refreshes all content roots, not just basePath
- **Error responses**: `available_projects` detail is configurable. Expanded mode includes workspace sub-projects with their `workspace` parent name; compact mode returns only top-level project roots.

Key utility: `ProjectUtils.getModuleContentRoots(project)` returns all module content root paths.

### MCP Server Architecture

MCP servers expose:
- **Tools** - Operations that can be invoked (e.g., `rename_symbol`, `find_usages`)
- **Prompts** - Pre-defined interaction templates (optional)

**Server Infrastructure:**
- Custom embedded **Ktor CIO** HTTP server (not IntelliJ's built-in server)
- Configurable port with IDE-specific defaults (e.g., IntelliJ: 29170, PyCharm: 29172) via Settings → Tools → IdeSense → Server Port
- Binds to `127.0.0.1` (localhost) by default; configurable via **Server Host** setting
- **Non-loopback bind is opt-in.** There is no auth token on any transport, so a non-loopback host (`0.0.0.0`, a LAN address, …) hands every enabled tool to anything that can reach the port. `ServerHostPolicy` is the single choke point on every bind path: a non-loopback host is honored only when the user has ticked **Allow non-loopback bind**; otherwise the server falls back to loopback, stays running (local agents keep working), and warns via notification. Every URL the plugin reports — status panel, generated client configs — is built from the host actually bound, never the configured one
- Single server instance across all open projects
- Auto-restart on port change

**Key Server Classes:**
- `McpServerService` - Application-level service managing server lifecycle
- `KtorMcpServer` - Embedded Ktor CIO server with CORS support
- `KtorSseSessionManager` - SSE session management using Kotlin channels
- `JsonRpcHandler` - JSON-RPC 2.0 request processing

**Transport**: This plugin supports two transports with JSON-RPC 2.0. All tool results include native `structuredContent` (MCP 2025-11-25). The text content block mirrors the structured content for backward compatibility: in **JSON** mode (default) it contains the serialized JSON; in **TOON** mode it contains the TOON representation instead. The format is controlled by the **Response Format** setting.

*Streamable HTTP (Primary, MCP 2025-11-25):*
- `POST /mcp/streamable-http` → Stateless JSON-RPC requests/responses
- `GET /mcp/streamable-http` → 405 Method Not Allowed
- `DELETE /mcp/streamable-http` → 405 Method Not Allowed
- Protocol version is negotiated on `initialize` (supported: 2025-11-25, 2025-03-26, 2024-11-05); streamable-HTTP defaults to 2025-11-25

*Legacy SSE (MCP 2024-11-05):*
- `GET /mcp/sse` → Opens SSE stream, sends `endpoint` event with POST URL
- `POST /mcp` → JSON-RPC requests/responses


**Port Configuration**: Settings → Tools → IdeSense → Server Port (IDE-specific defaults, range: 1024-65535)

**IDE-Specific Defaults**:
| IDE | Server Name | Default Port |
|-----|-------------|--------------|
| IntelliJ IDEA | `intellij-idesense` | 29170 |
| Android Studio | `android-studio-idesense` | 29171 |
| PyCharm | `pycharm-idesense` | 29172 |
| WebStorm | `webstorm-idesense` | 29173 |
| GoLand | `goland-idesense` | 29174 |
| PhpStorm | `phpstorm-idesense` | 29175 |
| RubyMine | `rubymine-idesense` | 29176 |
| CLion | `clion-idesense` | 29177 |
| RustRover | `rustrover-idesense` | 29178 |
| DataGrip | `datagrip-idesense` | 29179 |
| Aqua | `aqua-idesense` | 29180 |
| DataSpell | `dataspell-idesense` | 29181 |
| Rider | `rider-idesense` | 29182 |

> **Note**: Rider has a port entry but is currently marked incompatible in `plugin.xml` and is not supported.

## Multi-Language Architecture

Two distinct mechanisms — pick by whether the platform exposes a usable extension point
(see "Core Design Principle: Mimic the IDE"):

**1. IDE extension-point delegation (preferred).** `ide_call_hierarchy` /
`ide_type_hierarchy` drive the IDE's own machinery — no per-language handlers. See
"Hierarchy Tools" below. Qualified names everywhere go through `QualifiedNameUtil` →
`QualifiedNameProvider` EP.

**2. `LanguageServices` dispatch object (where no universal EP fits).** Used for kind
resolution and `ide_find_super_methods`.

- `LanguageServices` (`handlers/LanguageServices.kt`) — object with `getKind(element)`
  (dispatches to `LanguageKindResolver` EP → `LanguageFindUsages.getType()` fallback →
  className fallback) and `findSuperMethods(element, project)` (dispatches to
  `SuperMethodsProvider` EP). Both EPs are registered in `plugin.xml` per language.
- `LanguageKindResolver` / `SuperMethodsProvider` — IntelliJ `LanguageExtension` EPs;
  implementations are registered for each supported language and use reflection where
  needed to avoid compile-time deps on language plugins (prevents `NoClassDefFoundError`
  in IDEs lacking them).

**3. `DefinitionsScopedSearch` EP delegation.** `ide_find_implementations` calls the
platform's `DefinitionsScopedSearch.search()` directly — the same API behind Ctrl+Alt+B.
Works for all languages (each plugin registers its own `QueryExecutor`).

**Registration flow** (`ToolRegistry`, during `McpServerService` init):
1. `registerUniversalTools()` — tools that work in every IDE (incl. `ide_refactor_rename`,
   `ide_sync_files`, the hierarchy tools, `ide_find_implementations`,
   `ide_install_plugin`/`ide_restart`)
2. `registerLanguageNavigationTools()` — `ide_find_super_methods` (gated by
   `LanguageServices.hasAnySuperMethodsProvider()`), hierarchy tools

## Hierarchy Tools (IDE Extension-Point Delegation)

`ide_call_hierarchy` / `ide_type_hierarchy` do **not** re-implement traversal. They drive
the IDE's own `HierarchyProvider` headlessly so output matches the IDE's Hierarchy tool
window. Code in `tools/navigation/hierarchy/`:

- **`HierarchyTreeWalker`** — the engine. Resolves `LanguageCallHierarchy` /
  `LanguageTypeHierarchy` for the element's language, calls `provider.getTarget()` /
  builds the provider's browser, reflectively invokes the protected
  `createHierarchyTreeStructure(typeName, element)`, and walks the resulting
  `HierarchyNodeDescriptor` tree depth-bounded with cycle dedupe. **Strategy I.**
- **`BrowserBackedResolver`** (in the walker) — resolves each descriptor's logical
  element, preferring `descriptor.getEnclosingElement()` (the IDE's own "logical owner"
  notion) over the browser's `getElementFromDescriptor`. Normalizes Rust callers (whose
  browser returns the call site) to the enclosing method like every other language.
- **`ClassLikePsi`** — cross-IDE PSI reflection: `kind` (delegates to
  `LanguageServices.getKind()`), qualified/display name, walk-up to
  class-/method-like. Uses `Class.forName` + `isInstance` so a single binary runs in
  PyCharm/GoLand/RustRover/etc. without compile-time language-plugin refs. Element
  `kind` is the one thing with no universal
  API — classification here is unavoidably per-language.
- **`HierarchyScope`** — enum mapping wire values (`all`, `production`, `test`,
  `this_class`, `this_module`) to the IDE's hierarchy scope-type strings. `all` maps
  to `SCOPE_ALL` deliberately (matches the IDE's default-selected tab; `SCOPE_PROJECT`
  = "Production" yields an empty scope in projects with no production source roots,
  e.g. JS/TS — which silently emptied callers).
- **`RustTypeHierarchyFallback` / `RustTypeHierarchyImpl`** — **Strategy II.** RustRover
  registers a call-hierarchy provider but **no** type-hierarchy provider, so Rust type
  hierarchy uses a relocated hand-rolled algorithm that synthesizes descriptors. This is
  the only language without full EP delegation.

## Symbol Search

Symbol search across all languages drives IntelliJ's headless "Go to Symbol" popup stack via `PopupFaithfulSymbolSearch` (in `handlers/PopupFaithfulSymbolSearch.kt`):
- Wraps `GotoSymbolModel2` + `ChooseByNameModelEx` — the same APIs as IntelliJ's own Ctrl+Alt+Shift+N popup
- Inherits the IDE's parallel execution, dumb-mode safety, cancellation, proximity-aware sorting, and qualified-query support (e.g. `BasicSolver.run`)
- `FindSymbolTool` owns the over-fetch loop and converts NavigationItems to wire-format `SymbolData` via `SymbolDataConverter`
- `SymbolDataConverter` delegates `kind` classification to `LanguageServices.getKind()` and qualified names to `QualifiedNameUtil`
- Supports language filtering (e.g., `languageFilter = setOf("Java", "Kotlin")`)

## Pagination

The plugin supports cursor-based pagination for search tools that return flat result lists:
`ide_find_usages`, `ide_search_text`, `ide_find_class`, `ide_find_file`, `ide_find_symbol`, `ide_find_implementations`.

**Key components:**
- `PaginationService` (`server/PaginationService.kt`): Application-level light service managing cursor cache
- Cursor tokens are opaque, immutable, base64url-encoded strings containing `{entryId}:{offset}:{pageSize}`
- Same cursor token always returns the same page (idempotent, safe for retries)
- Each response includes `nextCursor` for the next page

**Cache lifecycle:**
- Over-collection: tools collect 500 results internally, serve in configurable page sizes (default varies per tool)
- Inactivity-based TTL: 10 minutes of idle time before cursor expires
- LRU eviction: max 20 active cursors
- Max 5,000 cached results per cursor; beyond this, `hasMore` returns false
- Staleness detection via `PsiModificationTracker` — `stale: true` in response if PSI changed

**Tool integration pattern:**
1. Check for `cursor` parameter → serve from cache via `getPageFromCache()`
2. Fresh search → collect results, create cursor via `PaginationService.createCursor()`, serve first page
3. `searchExtender` lambda enables lazy cache extension when pages are exhausted
4. Each tool has a `buildPaginatedResult()` helper mapping `GetPageResult` to its own result model

**Schema:** All parameters are optional in the schema (no `required` array) because the Anthropic API does not support `anyOf`/`oneOf` at the top level. Validation is done at runtime — if `cursor` is absent, the tool checks for its required search params and returns an error if missing.

**Backward compatibility:** Old `limit`/`maxResults` parameters work as aliases for `pageSize`. Legacy cursors (without embedded pageSize) are still decodable but require an explicit `pageSize` parameter.

## Argument Validation & Structured Errors

Two pieces ship the structured-validated-error-path work (Layers B + C of
`docs/superpowers/specs/2026-05-29-structured-validated-error-path-design.md`):

**`ArgumentValidator`** (`tools/schema/ArgumentValidator.kt`) — the enforcement counterpart to
`SchemaBuilder`. Pure and unit-tested. `JsonRpcHandler.processToolCall` calls
`validate(arguments, tool.inputSchema)` **after** project resolution and **before** `tool.execute`;
non-empty violations short-circuit to an `invalid_arguments` tool error (not recorded in command
history, not logged at ERROR). It is **strict** — checks required, primitive type, enum, **and
unknown keys** (the core fix for silently-ignored typos, #12). Type checking mirrors the runtime
accessors (`jsonPrimitive.int`/`.boolean`/`.content`): it rejects only the kinds those would throw on
and stays lenient on numeric-string→int (`line: "123"` passes, `line: "abc"` does not). The
undocumented pagination aliases `limit`/`maxResults` are allowlisted; `project_path` is in-schema on
every tool. **Consequence:** because validation now enforces the schema, every parameter (and enum
value) a tool actually accepts MUST be declared in its `SchemaBuilder` schema — an accepted-but-
undeclared param is a bug (this surfaced `ide_find_class` `matchMode: camelCase`, which was missing
from the enum). Conversely a param the tool ignores should not be sent; the validator (correctly)
rejects it.

**`McpErrors`** (`server/McpErrors.kt`) — builds canonical error bodies as `JsonObject`s (pure;
callers render them to a `ToolCallResult` via `StructuredToolResult.fromElement`). Canonical shape:
`{ "error": "<snake_case_code>", "message": "<human>", …context }`. Validation errors aggregate:
`{ "error": "invalid_arguments", "message": …, "violations": [ {"parameter", "problem", …} ] }` where
`problem` ∈ `{missing_required, unknown_parameter, invalid_type, invalid_enum}` (unknown carries
`allowedParameters`; type carries `expected`/`provided`; enum carries `provided`/`supportedValues`).

**Error channel & catch-all split.** Once a tool resolves, all errors are **tool results**
(`isError: true` + text mirror + native `structuredContent`), never JSON-RPC `error` objects — those
stay reserved for pre-dispatch protocol failures (parse, bad jsonrpc, missing params, unknown
tool/method). `AbstractMcpTool.createErrorResult(message)` now wraps to
`{"error":"tool_error","message":message}` centrally (all ~100 call sites, zero edits), and is
recursion-safe (`createStructuredErrorResult`'s formatting-failure fallback builds plain text inline).
`processToolCall`'s catch is split: `catch (McpException)` → `McpErrors.fromException(e)` using
`e.errorType`, **not** logged at ERROR (client-caused, e.g. dumb mode); `catch (Exception)` →
`internal_error`, logged at ERROR.

**`error` code vocabulary:** `invalid_arguments` (validator) · `tool_error` (generic
`createErrorResult`) · `internal_error` (generic catch / `InternalErrorException`) · the
`McpException.errorType` codes `index_not_ready` / `file_not_found` / `symbol_not_found` /
`refactoring_conflict` / `invalid_params` · and `ProjectResolver`'s `no_project_open` /
`project_not_found` / `multiple_projects_open`.

## Search Collection Pattern (Processor)

All search operations use the `Processor` pattern for efficient streaming and early termination:

```kotlin
// ✗ Inefficient: loads all results into memory
val results = SomeSearch.search(element).findAll().take(100)

// ✓ Efficient: streams results with early termination
val results = mutableListOf<Result>()
SomeSearch.search(element).forEach(Processor { item ->
    results.add(convertToResult(item))
    results.size < 100  // Return false to stop iteration
})
```

## Useful IntelliJ Platform Classes

```kotlin
// PSI Navigation
PsiTreeUtil           // Tree traversal utilities
PsiUtilCore          // Core PSI utilities
ReferencesSearch     // Find references to element

// Refactoring
RefactoringFactory   // Create refactoring instances
RenameProcessor      // Rename refactoring
RefactoringBundle    // Refactoring messages

// Indexes
DumbService          // Check index status
FileBasedIndex       // Access file indexes
StubIndex            // Access stub indexes

// Project Structure
ProjectRootManager   // Project roots
ModuleManager        // Module access
VirtualFileManager   // Virtual file system
```
