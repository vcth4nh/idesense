# Architecture

This file describes how the code works: the mechanism behind each tool, the code map and the
platform contracts. The goal, the scope and the design principles are in
[PRINCIPLES.md](PRINCIPLES.md). The process is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Tool → backing mechanism

Each tool delegates to a platform API. This is **not** uniformly an extension point —
some tools use a platform service, plain PSI/VFS, or a processor that itself iterates EPs.
The "verified against" column cites the exact call site so a future reader can re-check in one grep.

| Tool | Backing mechanism | verified against |
|---|---|---|
| `ide_find_usages` | `SuperMethodsProvider.findDirectReferences` first (Java, Kotlin, PHP), else EP `FindUsagesHandlerFactory.EP_NAME` (Alt+F7 equivalence class), else `ReferencesSearch`; symbol anchor: `SymbolAnchorResolver` | `FindUsagesHandlerSearch.kt` / `FindUsagesTool.kt` / `SuperMethodsProvider.kt` |
| `ide_find_definition` | none — `PsiUtils.resolveTargetElement` → `PsiElement.navigationElement` (Ctrl+B) | `FindDefinitionTool.kt` |
| `ide_find_class` | headless Go-to-Class popup: `PopupFaithfulClassSearch` → `GotoClassModel2` (Ctrl+N) | `FindClassTool.kt` / `PopupFaithfulClassSearch.kt` |
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
| `ide_explain_symbol` | composes: anchor via `SymbolAnchorResolver`; quick doc via `DocumentationManager`, else `PsiDocumentationTargetProvider.EP_NAME`; facets via `SuperMethodsProvider` EP + `DefinitionsScopedSearch` + `FindUsagesHandlerSearch` + optional `DiagnosticsAnalysisService` | `ExplainSymbolTool.kt` / `SymbolAnchorResolver.kt` |
| `ide_index_status` | service: `DumbService.getInstance(project).isDumb` | `GetIndexStatusTool.kt` |
| `ide_sync_files` | none — `VfsUtil.markDirtyAndRefresh` + `LocalFileSystem` + `PsiDocumentManager.commitAllDocuments` | `SyncFilesTool.kt` / `AbstractMcpTool.kt` (`commitDocuments`) |
| `ide_install_plugin` | none — `PathManager.getPluginsDir()` + JDK `ZipInputStream` (zip-slip guarded) | `InstallPluginTool.kt` |
| `ide_restart` | none — `ApplicationManagerEx.getApplicationEx().restart(true)` (scheduled via `AppExecutorUtil`) | `RestartIdeTool.kt` |
| `ide_refactor_rename` | `RenameProcessor` + `RenamePsiElementProcessor` EP + `AutomaticRenamerFactory` EP iteration | `RenameSymbolTool.kt` |
| `ide_move_file` | `MoveFilesOrDirectoriesProcessor` (delegates to `MoveFileHandler` EP per language; PHP class files route through PhpStorm's class-move processor) | `MoveFileTool.kt` |

## Where a tool differs from the IDE on purpose

Each entry gives the difference, its reason and the code. "Mimic the IDE" is the default (see
[PRINCIPLES.md](PRINCIPLES.md)). A new deviation needs the sign-off of the owner of the
repository, and an entry here.

- **Find usages: base declarations and marks.** The tool searches the base declarations and the
  overriding declarations too, and it marks each usage that is not a sure match (`BASE`,
  `OVERRIDE`, `DYNAMIC`). The rule is "Marked false positives" in [PRINCIPLES.md](PRINCIPLES.md).
  The detail is in [Find Usages](#find-usages) (`FindUsagesHandlerSearch`, `UsageMatch`).
- **Find usages: Go literal keys of a same-named field.** The search leaves them out and counts
  them in a note. See the item "Left-out usages" of [Find Usages](#find-usages)
  (`GoFindUsages.isFieldKeyOfType`).
- **Find usages: no search of the Python class `object`.** Each class is a subclass of `object`, so
  these usages give almost no information. The PyCharm factory asks no question when the nearest
  super method is in `object`. A note names each skipped method
  (`PythonSuperMethodsProvider.skippedBaseDeclarations`, `SkippedBasesNote`).
- **Usage types.** `usageType` is a vocabulary of the plugin (`UsageTypes`), not the usage types of
  the IDE. A usage inside a comment is always `COMMENT`, in each language: this is the rule of the
  platform group "Usage in comments" (`UsageTypeGroupingRule`). The other types come from
  substrings of PSI class names (`FindUsagesTool.classifyUsage`; see #27).
- **A scope with no source roots is an error.** For `project_production_files` or
  `project_test_files` in a project with no such source root, `ide_find_usages`, `ide_find_class`,
  `ide_find_file`, `ide_find_symbol` and `ide_find_implementations` return `scope_matches_no_files`.
  The IDE scope is empty there too, but an empty list reads as "no matches"
  (`BuiltInSearchScopeResolver.missingRootsReason`). The hierarchy tools give an empty tree, as the IDE does.
- **`ide_type_hierarchy` with `direction: both`.** The result is the union of the supertypes walk
  and the subtypes walk, as two lists, not the combined tree of the IDE. See
  [Why `direction: both` is a union](#why-direction-both-is-a-union) (`TypeHierarchyTool`).
- **The order of same-name symbols.** `ide_find_symbol` and the name anchors put declarations before
  values (field, variable, property, constant, parameter), then a symbol in a file of its own name,
  then sort by file, line and column (`SameNameSymbolOrder`). The popup sorts by proximity to the file
  in the editor (`DefaultChooseByNameItemProvider.processByNames`, idea/262.8665.337); a headless call
  has no editor, so that order changes between IDE sessions. The order has no path rules: the IDE has none.
- **`ide_call_hierarchy` limits.** The default depth is 3 (maximum 20). The tree holds at most 200
  nodes, filled depth first, because a callers tree can hold thousands of nodes. A cut sets
  `truncated`, and the nodes after the cut show no children (`CallHierarchyTool`). `ide_type_hierarchy`
  has a depth (default 5, maximum 20) and no node budget.
- **One row for a Go method that a type gets through an embedded pointer** (`ide_find_implementations`
  and `ide_explain_symbol`). GoLand gives the declared method and a light element for the promoted
  method. Both hits get the same position (`PsiUtils.positionElement`), and
  `ImplementationLocations.Collector` keeps one row for each position and name. The GoLand popup shows
  two equal rows only for a small result: a list that loads in the background keeps its rows in a
  `TreeSet` that compares the row texts (`BackgroundUpdaterTaskBase`,
  `GotoTargetHandler.createComparator`; GoLand 262.8665, `lib/intellij.platform.lang.impl.jar`).
- **`ide_find_super_methods` at a method that a Go interface declares.** The tool returns that method
  with an empty hierarchy: a method of an interface has no super method. Go to Super of GoLand works
  on the interface type at this position. The tool gives the type result for a position on the type
  name or on an embedded interface (`GoSuperMethodsProvider.tryInterfaceMethodAnchor`).
- **The Rust type hierarchy is code of the plugin.** RustRover registers no type hierarchy provider,
  so no IDE view exists to mirror (`RustTypeHierarchyFallback`, `RustTypeHierarchyImpl`; see #185).
- **`ide_search_text`: one match for each line, and a label filter.** The word index search calls the
  processor for each PSI ancestor of an occurrence, innermost first; the tool takes only the first
  call, and it keeps one match for each line. The `context` filter compares the label of the tool (`CODE`, `COMMENT`, `STRING_LITERAL`), and
  the index search runs with `UsageSearchContext.ANY`: the index puts plain text, HTML text and JSON
  strings in other contexts, so a context mask loses matches (#133) (`SearchTextTool`).
- **The qualified name of a Go field or method.** The tool puts the package and the type before the
  name: `package.Struct.field`, `package.Struct.Mutex` for an embedded `sync.Mutex`,
  `package.Receiver.Method` and `package.Interface.method`. A field and an interface method get the
  name of the nearest enclosing type declaration, also inside an anonymous struct. A field with no
  enclosing type declaration (an anonymous struct of a `var`, a parameter or a literal) gets
  `package.field`. The Go plugin registers no `qualifiedNameProvider`. Its own name,
  `GoNamedElementImpl.getQualifiedName`, is different: a field gets `package.field`
  (`GoPsiImplUtil.getFqn`), a method gets `Receiver.Method`, and an interface method gets the
  presentation text of the enclosing `GoSpecType` and the name, with no package
  (`plugins/go-plugin/lib/modules/intellij.go.impl.jar`, GO-263.7307.211). With these names, the
  fields of one name in two structs of one package get one name, and so do the methods of two types
  of one name in two packages (#136) (`QualifiedNameUtil.goFallback`).
- **`ide_file_structure`: the name `{}`.** The JavaScript structure view gives no text to an object
  literal that is not the right side of an assignment, for example an object in an array
  (`JSStructureItemPresentation.buildPresentationForElement`,
  `plugins/javascript-plugin/lib/modules/intellij.javascript.structureView.jar`, WS-263.7307.202).
  The File Structure popup shows such a node with an icon and no text. A text tree has no icon, so
  the tool gives the node the name `{}` and keeps its children (#198) (`FileStructureTool.nodeName`).
- **`ide_file_structure`: a name of one line, cut at 80 characters when it had a line break and
  is longer.** For an element with no name, the JavaScript structure view gives the source text of
  the element, also over several lines. The popup shows the node in one row and cuts the text at the
  width of the popup. The tool puts one space in place of each run of white space in a name of each
  language. It cuts only a name that had a line break and is longer than 80 characters, after 79
  characters, and adds `…`. A name with no line break stays complete, so a long function signature
  stays whole (#199) (`FileStructureTool.nodeName`).

## Project Structure

Package map under `src/main/kotlin/com/github/vcth4nh/idesense/`
(file list is `ls`-derivable — this documents *purpose*, which is not):

- `server/` — MCP infra: `McpServerService` (app-level lifecycle), `JsonRpcHandler`,
  `ProjectResolver` (multi-project/workspace), `transport/` (Ktor CIO + SSE), `models/`
- `tools/` — one class per MCP tool. `AbstractMcpTool` (VFS refresh and document commit before
  `doExecute()` only when `syncExternalChanges` is on, off by default; threading helpers),
  `ToolRegistry` (data-driven registration),
  `schema/SchemaBuilder` (all tool input schemas), `SymbolAnchor`/`SymbolAnchorResolver` (see
  "Symbol Anchors"). Subpackages: `navigation/` (incl. the note builders `BaseDeclarationsNote`,
  `OverridingDeclarationsNote`, `SkippedBasesNote`, `DroppedUsagesNote`, and `structure/`, the
  modifier text of `ide_file_structure`), `intelligence/`,
  `project/` (incl. `InstallPluginTool`/`RestartIdeTool` dev-loop), `refactoring/`, `models/`
  (the result data classes)
- `tools/navigation/hierarchy/` — **IDE extension-point delegation** for
  `ide_call_hierarchy`/`ide_type_hierarchy`. `HierarchyTreeWalker` drives the IDE's own
  `HierarchyProvider` browser/tree-structure headlessly; `ClassLikePsi` is the cross-IDE
  PSI reflection layer (kind/qualifiedName/name without compile-time language deps);
  `HierarchyScope`; `RustTypeHierarchyFallback`/`Impl` (Strategy II — RustRover
  ships no type-hierarchy provider). See "Hierarchy Tools" below.
- `handlers/` — `LanguageServices` (object with `getKind`/`findSuperMethods` dispatch)
  backed by `LanguageKindResolver` and `SuperMethodsProvider` IntelliJ `LanguageExtension`
  EPs (declared in `plugin.xml`). Also: `PopupFaithfulSymbolSearch`/`ClassSearch`
  (headless Go-to-Symbol popup model), `SameNameSymbolOrder`, `SymbolDataConverter`,
  `LanguageDisplayName`, `BuiltInSearchScope*`, `FindUsagesHandlerSearch` (with the language parts
  `go/GoFindUsages`, `javascript/JavaScriptFindUsages`, `markdown/MarkdownFindUsages`),
  `HandlerDataClasses` (wire-format data classes). `handlers` does not import `tools`. The
  `LanguageKindResolver` and `SuperMethodsProvider` implementations of a language are in
  `handlers/<lang>/`.
- `constants/` — `ToolNames`, `ParamNames`, `UsageTypes`, `UsageMatch` (the marks of a usage),
  `UsageDrop` (the kinds of a left-out usage)
- `util/` — `QualifiedNameUtil` (QualifiedNameProvider EP delegation + Go/Rust
  fallbacks), `ClassResolver`, `ProjectUtils`, `PsiUtils`, `PluginDetectors`,
  `ThreadingUtils`, `LinePreview`
- `settings/`, `startup/`, `ui/` — config + configurable, startup activities, tool-window UI.
  The tool window takes its actions from `actions/`, its icons from `icons/` and its command list
  from `history/` (`CommandHistoryService`).
- `exceptions/`: `McpException` and its subclasses.

Resources: `src/main/resources/META-INF/` (`plugin.xml` and the optional `*-features.xml`
language extensions).

Tests: `src/test/kotlin` (the test kinds are in [CONTRIBUTING.md](CONTRIBUTING.md#test-kinds),
"Test kinds"), live harness in `live-test/`.

## Architecture Concepts

### Workspace / Multi-Module Project Support

The plugin supports workspace projects where a single IDE window contains multiple sub-projects
represented as modules with separate content roots:

- **Project resolution** (`ProjectResolver.resolve`): Checks exact basePath → module content roots → subdirectory match
- **File resolution** (`AbstractMcpTool.resolveFile`): Tries basePath, then module content roots
- **Relative path computation** (`ProjectUtils.getRelativePath`): Strips the matching content root prefix
- **VFS/PSI sync** (`AbstractMcpTool.ensurePsiUpToDate`): Refreshes all content roots, not just basePath. It runs only when `syncExternalChanges` is on.
- **Error responses**: `ProjectResolver` builds `available_projects`. The setting `availableProjectsMode` selects the expanded or the compact list (see "Settings" in [README.md](../README.md#settings)).
- **All open projects at once**: with no `project_path`, a tool that implements `AllProjectsTool` (today `ide_index_status`) answers for each open project instead of `multiple_projects_open`. It is a separate interface, not a default method of `McpTool`, because `McpTool` is the interface of the public extension point `mcpTool`.

Key utility: `ProjectUtils.getModuleContentRoots(project)` returns all module content root paths.

### MCP Server Architecture

The server exposes tools only (for example `ide_refactor_rename`, `ide_find_usages`), no prompts and
no resources. `JsonRpcHandler` answers the JSON-RPC methods `initialize`,
`notifications/initialized`, `ping`, `tools/list` and `tools/call` (`JsonRpcMethods`).

**Server Infrastructure:**
- Custom embedded **Ktor CIO** HTTP server (not IntelliJ's built-in server)
- The port, the host and the other server settings are in "Settings" of [README.md](../README.md#settings)
- **Non-loopback bind is opt-in.** There is no auth token on any transport, so a non-loopback host (`0.0.0.0`, a LAN address, …) hands every enabled tool to anything that can reach the port. `ServerHostPolicy` is the single choke point on every bind path: a non-loopback host is honored only when the user has ticked **Allow non-loopback bind**; otherwise the server falls back to loopback, stays running (local agents keep working), and warns via notification. Every URL the plugin reports — status panel, generated client configs — is built from the host actually bound, never the configured one
- Single server instance across all open projects

**Key Server Classes:**
- `McpServerService` - Application-level service managing server lifecycle
- `KtorMcpServer` - Embedded Ktor CIO server with CORS support
- `KtorSseSessionManager` - SSE session management using Kotlin channels
- `JsonRpcHandler` - JSON-RPC 2.0 request processing

**Transport**: This plugin supports three transport modes with JSON-RPC 2.0. A tool result that `StructuredToolResult` builds includes native `structuredContent` (MCP 2025-11-25). Only `AbstractMcpTool.createSuccessResult` (today the empty-file answer of `ide_file_structure`) and the fallback for a formatting failure give a result with text only. The text content block mirrors the structured content for backward compatibility: in **JSON** mode (default) it contains the serialized JSON; in **TOON** mode it contains the TOON representation instead. The format is controlled by the **Response Format** setting.

*Streamable HTTP (Primary, MCP 2025-11-25):*
- `POST /mcp/streamable-http` → Stateless JSON-RPC requests/responses
- `GET /mcp/streamable-http` → 405 Method Not Allowed
- `DELETE /mcp/streamable-http` → 405 Method Not Allowed
- Protocol version is negotiated on `initialize` (the versions in `McpConstants.SUPPORTED_PROTOCOL_VERSIONS`); streamable-HTTP defaults to 2025-11-25

*Legacy SSE (MCP 2024-11-05):*
- `GET /mcp/sse` → Opens SSE stream, sends `endpoint` event with POST URL
- `POST /mcp?sessionId=<id>` → 202, the answer is an SSE `message` event (`POST /mcp/sse` goes to the same handler)

*Stateless (legacy):*
- `POST /mcp` with no `sessionId` → immediate JSON, default protocol `McpConstants.LEGACY_MCP_PROTOCOL_VERSION`

### IDE-Specific Defaults

Server names and default ports come from `IdeProductInfo.IdeProduct` (`util/IdeProductInfo.kt`).
The table for a user is in [README.md](../README.md#ide-specific-defaults), "IDE-Specific
Defaults". `IdeProductInfo` has a Rider entry, but `plugin.xml` marks the plugin incompatible
with Rider (`incompatible-with`).

## Multi-Language Architecture

Three mechanisms — pick by whether the platform exposes a usable extension point
(see "Delegate to the platform" in [PRINCIPLES.md](PRINCIPLES.md)):

**1. IDE extension-point delegation (preferred).** `ide_call_hierarchy` /
`ide_type_hierarchy` drive the IDE's own machinery — no per-language handlers. See
"Hierarchy Tools" below. Qualified names everywhere go through `QualifiedNameUtil` →
`QualifiedNameProvider` EP.

**2. `LanguageServices` dispatch object (where no universal EP fits).** Used for kind
resolution and `ide_find_super_methods`.

- `LanguageServices` (`handlers/LanguageServices.kt`) — object with `getKind(element)`
  (dispatches to `LanguageKindResolver` EP → `LanguageFindUsages.getType()` fallback →
  className fallback) and `findSuperMethods(element, project)` (dispatches to
  `SuperMethodsProvider` EP). `plugin.xml` declares both EPs.
- `LanguageKindResolver` / `SuperMethodsProvider` — IntelliJ `LanguageExtension` EPs.
  Each language registers its implementations in its `<lang>-features.xml`. The
  implementations use reflection where needed to avoid compile-time deps on language plugins
  (prevents `NoClassDefFoundError` in IDEs lacking them). JavaScript and TypeScript register
  only a `SuperMethodsProvider`, so their kind comes from the two fallbacks of `getKind`.

**3. `DefinitionsScopedSearch` EP delegation.** `ide_find_implementations` calls the
platform's `DefinitionsScopedSearch.search()` directly — the same API behind Ctrl+Alt+B.
Works for all languages (each plugin registers its own `QueryExecutor`).

**Registration flow** (`ToolRegistry`, during `McpServerService` init):
1. `registerUniversalTools()` — tools that work in every IDE (incl. `ide_refactor_rename`,
   `ide_sync_files`, `ide_find_implementations`, `ide_install_plugin`/`ide_restart`)
2. `registerLanguageNavigationTools()` — the hierarchy tools, and `ide_find_super_methods`
   (gated by `LanguageServices.hasAnySuperMethodsProvider()`)

## Hierarchy Tools (IDE Extension-Point Delegation)

`ide_call_hierarchy` / `ide_type_hierarchy` do **not** re-implement traversal. They drive
the IDE's own `HierarchyProvider` headlessly so output matches the IDE's Hierarchy tool
window. Code in `tools/navigation/hierarchy/`:

- **`HierarchyTreeWalker`** — the engine. Resolves `LanguageCallHierarchy` /
  `LanguageTypeHierarchy` for the element's language, calls `provider.getTarget()` /
  builds the provider's browser, reflectively invokes the protected
  `createHierarchyTreeStructure(typeName, element)`, and walks the resulting
  `HierarchyNodeDescriptor` tree depth-bounded with cycle dedupe and an optional node budget
  (`maxNodes`). **Strategy I.**
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

### Why `direction: both` is a union

`TypeHierarchyBrowserBase` (`lib/intellij.platform.lang.impl.jar`) has three hierarchy types:
`getSupertypesHierarchyType()`, `getSubtypesHierarchyType()` and the combined
`getTypeHierarchyType()` ("Class {0}"). `HierarchyTreeWalker` never asks for the combined type, and
`TypeHierarchyTool` runs one walk for each direction. The call hierarchy maps one to one
(`CallHierarchyBrowserBase.getCallerType()`, `getCalleeType()`). The combined branch of
`createHierarchyTreeStructure` in each language (bytecode of the language plugins):

| Language | Browser → tree structure of the combined view | Headless |
|---|---|---|
| Java | `TypeHierarchyBrowser` → `TypeHierarchyTreeStructure` | yes |
| Kotlin (K2) | `KotlinTypeHierarchyBrowser` → `KotlinTypeHierarchyTreeStructure`; its `createSuperClasses` asserts the EDT and runs a modal task (`analyzeInModalWindow`) | no |
| Python | `PyTypeHierarchyBrowser` → `PyTypeHierarchyTreeStructure` | yes |
| JavaScript, TypeScript | `JSTypeHierarchyBrowser` → `JSTypeHierarchyTreeStructure`; TypeScript has no provider of its own and gets the JavaScript one through its base language | yes |
| PHP | `PhpTypeHierarchyBrowser` → `PhpTypeHierarchyTreeStructure` | yes |
| Go | `GoTypeHierarchyBrowser` returns null for the combined type | no view |
| Rust | no type hierarchy provider (only `RsCallHierarchyProvider`) | no view |

Only the two separate walks work headless in all eight languages.

### Scope

`HierarchyTreeWalker.applyBrowserScope` writes the scope string of `HierarchyScope` into the
per-call browser by reflection: into the `myScope` of the sheet, as the current sheet, and into the
own `myScope` of a browser that overrides `getCurrentScopeType()` (GoLand's
`GoCallHierarchyBrowser`). The base `HierarchyTreeStructure.getSearchScope` maps "Production" to the
production files (in source content, not in test sources), "Test" to the test files, "This Class"
to a `LocalSearchScope` of the element, "This Module" to `Module.getModuleScope(true)`, and each
other value to the all scope. `ide_type_hierarchy` accepts only `all`, `production` and `test`
(`HierarchyScope.TYPE_HIERARCHY_SCOPES`). The language plugin decides whether a value has an effect:

| Language | Call hierarchy | Type hierarchy |
|---|---|---|
| Java, Kotlin | the base mapping | the inheritor search takes the scope |
| Python | the base mapping | no effect: `PyClassInheritorsSearch.search(PyClass, boolean)` has no scope parameter |
| PHP | the base mapping | no effect: `PhpSubtypesHierarchyTreeStructure` takes no scope |
| JavaScript, TypeScript | the base mapping | no effect: `JSSubtypesHierarchyTreeStructure` takes no scope |
| Go | the browser reads its own `myScope`; the GoLand window has its own scope list (`GoChangeScopeAction`) with no Production, This Class or This Module entry | the scope applies |
| Rust | no effect: `RsCallHierarchyBrowser.prependActions` removes the scope action, and `RsCallerTreeStructure` searches the references with a null scope | the scope applies through the plugin code (`HierarchyScope.resolveGlobalScope` in `RustTypeHierarchyImpl`) |

The project model decides the rest: `production` and `test` are empty without such source roots,
and `this_module` covers the whole project when it has one module. RustRover takes its test source
roots from the Cargo layout, the `tests/` and `benches/` folders of a crate
(`CargoProjectServiceKt.setup`); `RsTestSourcesFilter.isTestSource` accepts only doctest injections
(`intellij-rust.jar`).

### The per-call browser and the client session

- **Construction.** Each walk creates a browser through `createHierarchyBrowser`, on the calling
  thread, inside the read action: the platform rejects `invokeAndWait` there, and the constructors
  only allocate Swing components that nothing shows (`HierarchyTreeWalker.createBrowserHeadless`).
- **Disposal.** The constructor of `HierarchyBrowserBaseEx` registers a `SingleAlarm` under the
  browser, so a browser that nobody disposes leaks a panel and a timer for each call.
  `HierarchyWalkResult` owns the browser and is `AutoCloseable`; the tools close it after the
  conversion, and `releaseOnFailure` disposes the browser of a failed build. `dispose()` has no EDT
  assertion and changes no Swing state, so `disposeBrowser` runs inside the read action.
- **Client session.** The browser constructor creates the project service `HierarchyBrowserManager`
  (`client="all"`: one instance for each client session), which registers the "Hierarchy" tool
  window. The MCP thread has no `ClientId`, so in remote development a second instance would
  conflict with the instance of the GUI session. Thus `HierarchyTreeWalker.walk` runs under
  `ClientId.withExplicitClientId(guiClientId(project))`. `ClientId` and `ClientSessionsManager` are
  `@ApiStatus.Internal` on the class (`lib/intellij.platform.core.jar`, 2026.2), with no public
  replacement. Thus `build.gradle.kts` pins `pluginVerification.failureLevel` to
  `COMPATIBILITY_PROBLEMS`, which keeps the use of internal API a warning (#74).

### A class as the anchor of a call hierarchy

The call hierarchy providers of Java, Kotlin, Python and Rust accept a class: the anchor is its
constructor. The providers of JavaScript, TypeScript, Go and PHP fail on a class (GoLand:
`GoTypeSpecImpl` cannot be cast to `GoNamedSignatureOwner`). For a `symbol` that resolves to a
class-like element (`ClassLikePsi.isClassLike`), `CallHierarchyTool` replaces the failure of the
walker with an error that names the class and asks for a method. The check looks at the input, not
at the cause of the failure. The message of the walker goes to the log at INFO.

Related issues: #218, #223 and #225 (Go call hierarchy), #224 (Python property), #185 (Rust subtypes).

## Symbol Search

Symbol search across all languages drives IntelliJ's headless "Go to Symbol" popup stack via `PopupFaithfulSymbolSearch` (in `handlers/PopupFaithfulSymbolSearch.kt`):
- Wraps `GotoSymbolModel2` + `ChooseByNameModelEx` — the same APIs as IntelliJ's own Ctrl+Alt+Shift+N popup
- Inherits the IDE's parallel execution, dumb-mode safety, cancellation, the name order of the popup (`SameNameSymbolOrder` orders the symbols of one name), and qualified-query support (e.g. `BasicSolver.run`)
- `FindSymbolTool` owns the over-fetch loop and converts NavigationItems to wire-format `SymbolData` via `SymbolDataConverter`
- An exact-name search (`searchExactName`) serves the exact mode of `ide_find_symbol` and the name anchors of `SymbolAnchorResolver`. The popup ranks its items by a fuzzy match, so an item with the exact name can come after any number of other items (GoLand indexes a symbol as `package.name`, and the text `PKI` matches each symbol of the package `caddypki`). The exact-name search gives the popup stack only the index names that end with the name, and it keeps only the items with the exact name (#131)
- `SymbolDataConverter` delegates `kind` classification to `LanguageServices.getKind()` and qualified names to `QualifiedNameUtil`
- Supports language filtering (e.g., `languageFilter = setOf("Java", "Kotlin")`)

## Symbol Anchors

`ide_explain_symbol`, `ide_call_hierarchy` and `ide_find_usages` take a `symbol` (a name or a
qualified name) or `file` + `line` + `column`. `SymbolAnchor.parse` rejects both forms together, a
blank name and an incomplete position (`invalid_arguments`). The `className` of
`ide_type_hierarchy` resolves in the same way. `SymbolAnchorResolver.resolve` (in a read action):

1. **Qualified name.** `ClassResolver.findClassByName` asks each `QualifiedNameProvider` (the
   reverse of Copy Reference), then the PHP index for an interface or a trait. A file or a directory
   (`PsiFileSystemItem`) is no symbol and goes to step 2: the last fallback of the Java provider
   resolves a file path. A method given without a parameter list that has same-name overloads gives
   the overloads as candidates, because the provider selects one of them silently.
2. **Go to Symbol popup.** `PopupFaithfulSymbolSearch.searchExactName` in the project files, the case
   of the query first (`exactCaseFirst`), at most 200 exact matches.
3. **Result.** No match gives `NotFound`, one match `Resolved`, more matches `Ambiguous` with up to 10
   candidates in the order of `SameNameSymbolOrder` (`SymbolCandidatesResult`).

The resolver is in `tools`, because it returns `tools.models.SymbolMatch`. A Go or a Rust name never
resolves in step 1, so the popup decides it: `RsQualifiedNameProvider.qualifiedNameToElement` returns
null (`plugins/intellij-rust/lib/modules/intellij.rustrover.core.jar`, RR-262.8665.323), and the Go
plugin registers no `qualifiedNameProvider` (GO-262.8665.336). Observed in the running IDEs (2026.2):

- IntelliJ IDEA: the popup hides overriding methods, so a plain method name with no overloads
  resolves to the declaration in the base type. The Java provider wants `#` for a member
  (`demo.Quirks#parse`); a dotted member name goes to the popup.
- GoLand: the popup matches the qualifier by camel humps, so `Shape.Describe` also matches
  `baseShape.Describe` and gives candidates.
- RustRover: the popup returns nothing for a qualified pattern (`Shape::area`, a full crate path),
  also in `ide_find_symbol`. A plain name works.

## Find Usages

`ide_find_usages` and the usages of `ide_explain_symbol` call `FindUsagesHandlerSearch.processReferences`.
Its KDoc has the detail and the bytecode citations. The summary:

- **Passes.** The direct pass searches the symbol. The base pass searches each base declaration
  (`findBaseDeclarations`: all levels, the nearest first, only for a member that itself has a base),
  and after each one the other declarations that override it (`basePassTargets`), with the mark
  `BASE`. The override pass searches each overriding declaration (`findOverridingDeclarations`) with
  the mark `OVERRIDE`; the Go path has none. The result is the union. The collectors keep the first
  hit at a position, so a usage of the direct pass keeps no mark.
- **One target.** The search first asks the provider of the language of the target for
  `findDirectReferences`. A result that is not null replaces the handler. Else the first
  `FindUsagesHandlerFactory` that can find the usages gives a handler: for the direct pass in
  `USAGES_WITH_DEFAULT_OPTIONS` (the Find Usages action with no dialog), or in `HIGHLIGHT_USAGES`,
  which asks no question, when the symbol has a base declaration. With no handler, the search is a
  plain `ReferencesSearch`. A Go handler (`GoFindUsages.isGoHandler`) runs `processElementUsages`:
  only that path of GoLand gives the usages through interface methods and in comments. Each other
  handler runs `findReferencesToHighlight`, because `processElementUsages` can assert the EDT there.
  The option clones search no text occurrences.
- **Marks** (`UsageMatch`). `DYNAMIC` comes first, from the rule of the IDE group "Dynamic usages".
  The platform sets the flag in `UsageInfo(PsiReference)` when `multiResolve(false)` is empty or
  `resolve()` is null (`com.intellij.usageView.UsageInfo`, `lib/intellij.platform.core.jar`, build
  262.8665), and the listeners of `com.intellij.usageViewElementsListener` can set it. In the six IDEs
  of build 262, only `JSUsageViewElementsListener` (`JavaScriptFindUsages`) and the Markdown
  `BacktickUsageViewElementsListener` (`MarkdownFindUsages`) exist. For a new IDE version, examine the
  plugin descriptors for this extension point again and mirror each new listener. Then the provider
  can change the mark (`usageMark`).
- **PHP.** For a PHP method, PhpStorm asks "find usages of base method?" and then searches the
  selected methods and the methods that override them, with no mark. The tool asks no question
  (`PhpSuperMethodsProvider.findDirectReferences`, #182). It searches the method, its base methods
  with the other methods that override them (`FindUsagesHandlerSearch.basePassTargets`), and its
  overriding methods (#183). So the result holds each usage of both answers. The tool decides the
  mark of each usage from the declarations that its reference resolves to
  (`PhpSuperMethodsProvider.usageMark`).
- **Left-out usages** (`UsageDrop`). The general rule is "No silent drop" in
  [PRINCIPLES.md](PRINCIPLES.md). The language provider gives the kind of a usage to leave out
  (`SuperMethodsProvider.droppedUsageKind`, a `UsageDrop` value). `FindUsagesHandlerSearch` does
  not give that row to the caller, and it counts each position one time. `ide_explain_symbol`
  counts the left-out usages in the same way. Two kinds exist:
  - `GO_FIELD_KEY`: a key of a Go composite literal that names a struct field with the same name
    as the type of the query (`certmagic.ACMEIssuer{CA: iss.CA}` for the type `CA`). Find Usages
    of GoLand lists the key as a usage of the type, but the key refers to the field. This is an
    approved deviation from GoLand. A key of an embedded field names the type and stays.
  - `PHP_SELF_REFERENCE`: a reference to a PHP class through `$this`, `self` or `static` inside
    that class (#179). Find Usages of PhpStorm hides these rows by default
    (`PhpThisOrSelfFilteringRule`, `plugins/php-impl/lib/php.jar`), so the drop mirrors the IDE.
- **Notes and warnings.** The first page of `ide_find_usages` has `notes` from
  `BaseDeclarationsNote`, `OverridingDeclarationsNote` (both name at most 3 declarations and count
  the marked usages), `SkippedBasesNote` and `DroppedUsagesNote` ("or more" when the search stopped
  at its limit). When the factory or a handler stage throws, the search continues with less (the
  anchor only, no secondary targets, or one target less), and `warnings` says so. A cursor page has
  no `notes` and no `warnings`. `ide_explain_symbol` has only the skipped-base and dropped notes,
  counts up to 200 usages, and lists sure code usages first in `topUsages`, then `BASE`, `OVERRIDE`,
  other marks and `COMMENT` (`ExplainSymbolTool.preferSureUsages`).
- **The anchor of a position.** `ide_find_usages` takes the reference target with the flags of the
  Find Usages action (`PsiUtils.resolveReferenceTarget`). It does not use `resolveTargetElement`,
  whose `GotoDeclarationHandler` step moves a `new Foo()` caret to the constructor and loses usages.
  The map of a Kotlin constructor to its class thus stays in `FindDefinitionTool.effectiveDeclarationTarget`.

Provider hooks (`SuperMethodsProvider`; a hook that throws changes nothing, a cancellation or a `LinkageError` leaves the search):

| Hook | Effect | Languages |
|---|---|---|
| `findBaseDeclarations` | the targets of the base pass | Go, Java, JavaScript/TypeScript, Kotlin, PHP, Python, Rust |
| `findDirectReferences` | the references of one target, with no handler | Java (each method and constructor), Kotlin (a declaration with a super declaration), PHP (each method) |
| `findOverridingDeclarations` | the override pass, and more targets of the base pass | PHP |
| `skippedBaseDeclarations` | the base declarations that the search leaves out, for a note | Python (the methods of `object`) |
| `usageMark` | the mark of a usage that is not dynamic | PHP (from the declarations that the reference resolves to) |
| `droppedUsageKind` | a usage to leave out (`UsageDrop`) | Go (`GO_FIELD_KEY`), PHP (`PHP_SELF_REFERENCE`) |

Related issues: #214 (a PHP field with an accessor), #216 (the reason text of the base note), #220
(PyCharm: a receiver type that does not declare the method), #221 (Go: a file that the build
constraints exclude).

## Pagination

The plugin supports cursor-based pagination for search tools that return flat result lists:
`ide_find_usages`, `ide_search_text`, `ide_find_class`, `ide_find_file`, `ide_find_symbol`, `ide_find_implementations`.

**Key components:**
- `PaginationService` (`server/PaginationService.kt`): Application-level light service managing cursor cache
- Cursor tokens are opaque, immutable, base64url-encoded strings containing `{entryId}:{offset}:{pageSize}`
- Same cursor token always returns the same page (idempotent, safe for retries)
- Each response includes `nextCursor` for the next page

**Cache lifecycle** (the constants are in `PaginationService`):
- Over-collection: tools collect `DEFAULT_OVERCOLLECT` results internally, serve in configurable page sizes (default varies per tool)
- Inactivity-based TTL: `TTL_MINUTES` of idle time before cursor expires
- LRU eviction: max `MAX_CURSORS` active cursors
- Max `MAX_CACHED_RESULTS_PER_CURSOR` cached results per cursor; the `searchExtender` runs only while the cache holds fewer results
- Staleness detection via `PsiModificationTracker` — `stale: true` in response if PSI changed

The effect of these limits for a user is in [USAGE.md](USAGE.md#pagination-and-result-size),
"Pagination and Result Size".

**Tool integration pattern:**
1. Check for `cursor` parameter → serve from cache via `getPageFromCache()`
2. Fresh search → collect results, create cursor via `PaginationService.createCursor()`, serve first page
3. `searchExtender` lambda enables lazy cache extension when pages are exhausted
4. Each tool calls `AbstractMcpTool.buildPaginatedResult` with a lambda that maps the page to its own result model

**Schema:** All parameters of the paginated tools are optional in the schema (no `required` array) because the Anthropic API does not support `anyOf`/`oneOf` at the top level. Validation is done at runtime — if `cursor` is absent, the tool checks for its required search params and returns an error if missing.

**Backward compatibility:** Old `limit`/`maxResults` parameters work as aliases for `pageSize`. Legacy cursors (without embedded pageSize) are still decodable but require an explicit `pageSize` parameter.

## Argument Validation & Structured Errors

Two classes give the structured error path: `ArgumentValidator` checks the arguments against the
schema, and `McpErrors` builds the error bodies.

**`ArgumentValidator`** (`tools/schema/ArgumentValidator.kt`) — the enforcement counterpart to
`SchemaBuilder`. Pure and unit-tested. `JsonRpcHandler.processToolCall` calls
`validate(arguments, tool.inputSchema)` **after** project resolution and **before** `tool.execute`;
non-empty violations short-circuit to an `invalid_arguments` tool error (not recorded in command
history, not logged at ERROR). It is **strict** — checks required, primitive type, enum, **and
unknown keys** (so a typo in a parameter name is an error, not an ignored key). Type checking
mirrors the runtime accessors (`jsonPrimitive.int`/`.boolean`/`.content`): it rejects only the kinds
those would throw on and stays lenient on numeric-string→int (`line: "123"` passes, `line: "abc"`
does not). The undocumented pagination aliases `limit`/`maxResults` are allowlisted; `project_path`
is in-schema on every tool. **Consequence:** because validation enforces the schema, every
parameter (and enum value) a tool actually accepts MUST be declared in its `SchemaBuilder` schema —
an accepted-but-undeclared param is a bug. Conversely a param the tool ignores should not be sent; the
validator (correctly) rejects it.

**`McpErrors`** (`server/McpErrors.kt`) — builds canonical error bodies as `JsonObject`s (pure;
callers render them to a `ToolCallResult` via `StructuredToolResult.fromElement`). Canonical shape:
`{ "error": "<snake_case_code>", "message": "<human>", …context }`. Validation errors aggregate:
`{ "error": "invalid_arguments", "message": …, "violations": [ {"parameter", "problem", …} ] }` where
`problem` ∈ `{missing_required, unknown_parameter, invalid_type, invalid_enum}` (unknown carries
`allowedParameters`; type carries `expected`/`provided`; enum carries `provided`/`supportedValues`).

**Error channel & catch-all split.** Once a tool resolves, all errors are **tool results**
(`isError: true` + text mirror + native `structuredContent`), never JSON-RPC `error` objects — those
stay reserved for pre-dispatch protocol failures (parse, bad jsonrpc, missing params, unknown
tool/method, disabled tool). `AbstractMcpTool.createErrorResult(message)` wraps to
`{"error":"tool_error","message":message}` centrally, and is recursion-safe
(`createStructuredErrorResult`'s formatting-failure fallback builds plain text inline).
`processToolCall`'s catch is split: `catch (McpException)` → `McpErrors.fromException(e)` using
`e.errorType`, logged at INFO (client-caused, e.g. dumb mode); `catch (Exception)` →
`index_out_of_sync` at WARN when `McpErrors.isIndexMismatch(e)`, else `internal_error` at ERROR.
A cancellation (a `CancellationException` or a `ControlFlowException`) has two cases in the catch
blocks of `JsonRpcHandler` (`cancellationInActiveCall`, #127). When the coroutine of the call is
cancelled, the cancellation leaves the block with no log entry, no history update and no answer.
This occurs, for example, when the server stops. When the coroutine is still active, the client
still waits. Then the block gives its usual answer and history update, and it logs one line with
no throwable. Two examples extend `ProcessCanceledException`: `ServiceNotReadyException`, which
`FileBasedIndexImpl.ensureUpToDate` throws while the index is not ready (`lib/app-client.jar`),
and `AlreadyDisposedException` (`lib/util-8.jar`). `handleRequest` answers each cancellation in an
active call, so the request handlers of `KtorMcpServer` rethrow each cancellation
(`rethrowIfCancellation`). Their other source of a cancellation is the write of the answer. Then
the output channel of the call is cancelled (`CloseToken.wrapCause`, ktor-io 3.4.3), so no answer
can reach the client. The log gets no throwable, because the platform logger replaces a
`ControlFlowException` with the text "Control-flow exceptions ... should never be logged". It
also replaces a `CancellationException` while `idea.log.rethrow.ce` is `true`, the default
(`Logger.ensureNotControlFlow`, `lib/util-8.jar`). A `ProcessCanceledException` is a
`CancellationException`. The jars are those of ideaIC-2025.1.3.

**`error` code vocabulary** (the class that makes each code; the list for a user is in
"Error Handling" of [USAGE.md](USAGE.md#error-handling)): `invalid_arguments`
(`ArgumentValidator` and `AbstractMcpTool.createMissingRequiredParamError`, with `violations`;
the check of `SymbolAnchor.parse` in `ide_find_usages`, `ide_call_hierarchy` and
`ide_explain_symbol`, with no `violations`) · `tool_error` (generic `createErrorResult`) ·
`internal_error` (the generic catch of `processToolCall`) · `index_not_ready`
(`IndexNotReadyException` from `AbstractMcpTool.requireSmartMode`, the only `McpException` that a
tool throws) · `invalid_scope` (`McpErrors.invalidScope`, an unsupported `scope` value) ·
`scope_matches_no_files` (`McpErrors.scopeMatchesNoFiles`, see "Where a tool differs from the IDE
on purpose") · `index_out_of_sync` (`McpErrors.indexOutOfSync`, for the platform failure "PSI and
index do not match"; the platform calls `rebuildStub()` on the file before it throws (`FileTrees`,
idea/262.8665.337), so a later call can succeed) · and `ProjectResolver`'s `no_project_open` /
`project_not_found` / `multiple_projects_open`.

## Platform Contracts and Traps

Each entry gives the contract, the consequence for the code, and the class that follows it.

- **A read action starts again only when the cancellation leaves the block.** The coroutine
  `readAction { }` (`AbstractMcpTool.suspendingReadAction`) runs the block again for a pending write
  action only when `ReadAction.CannotReadException` (a `ProcessCanceledException`) leaves the block
  (`InternalReadAction.tryReadCancellable`, `app-client.jar`, ideaIC-2025.1.3). A broad `runCatching`
  or `catch (Exception)` stops the restart and turns a race into an empty or a failed result, and
  `Method.invoke` wraps the exception in `InvocationTargetException`. Rule: never swallow a
  cancellation. `rethrowIfCancellation` (in `HierarchyTreeWalker.kt`) unwraps and rethrows a
  `CancellationException` or a `ControlFlowException` for `HierarchyTreeWalker`,
  `ImplementationLocations.Collector` and the reflective searches and getters of the
  `SuperMethodsProvider` implementations (#210), and for the reflective getters of
  `UniversalModifiers`. The block can run more than one time, so the
  state that it fills starts empty in each run (`FindUsagesTool` clears its warnings and notes).
  Broad catches remain in `BrowserBackedResolver.resolve`, `HierarchyTreeWalker.resolveTarget`,
  `RustTypeHierarchyImpl`, `ClassResolver` and `QualifiedNameUtil`.
- **Dumb mode can start after a dumb mode check.** A check of `DumbService.isDumb` holds only for
  that moment. A search in a later plain read action can run in dumb mode: the platform
  `IndexNotReadyException` then gives an empty result (platform code catches it, for example
  `ExecutorsQuery`), a find-usages warning, or `internal_error` (#195, #267). The start of dumb mode
  is a write action (`DumbServiceImpl.incrementDumbCounter`, `app-client.jar`, ideaIC-2025.1.3).
  A write action cancels a coroutine `readAction` and runs its whole block again
  (`InternalReadAction.tryReadCancellable` turns `ReadAction.CannotReadException` into
  `ReadResult.WritePending`, and `readLoop` runs the block again; `app-client.jar` of
  ideaIC-2025.1.3, `intellij.platform.ide.impl.jar` of IU-263.7307.200). So after
  `requireSmartMode`, `suspendingReadAction` of the same call tests `DumbService.isDumb` at the
  start of its block, inside the read lock. In dumb mode it leaves the read action, waits 50 ms and
  tries again, also for the search extender of a cursor (`getPageFromCache`). The waits of one call
  stop at `INDEX_WAIT_LIMIT_MS` (10 s) with `index_not_ready`. The call does not wait for a scan of
  the files with no dumb mode; `smartReadAction` does, because its constraint tests
  `SmartModeScheduler.getCurrentMode`, which includes the scanner. During such a scan a platform
  search with the `inSmartMode` constraint throws "Constraint inSmartMode cannot be satisfied" inside
  a read action (`NonBlockingReadActionImpl$Submission.attemptComputation`, both builds), and
  `ExecutorsQuery` logs the error and goes on: `JavaFunctionalExpressionSearcher` then gives no
  lambdas and method references.
- **No exception may leave a search callback inside a stub index processor.** GoLand runs the
  callback of `DefinitionsScopedSearch` inside `StubIndexEx.processElements`, which takes an
  `IndexOutOfBoundsException` for index damage (`FileBasedIndexEx.extractCauseToRebuildIndex`) and
  rebuilds the stub index; all open projects are in dumb mode during the rebuild. A light element has
  the text offset -1 (`LightElement.getTextOffset()`, `intellij.platform.core.impl.jar`), and
  `Document.getLineNumber(-1)` throws that exception. A Go method that a type gets through an embedded
  pointer is such an element (`GoLightMethodDeclaration`, `intellij.go.impl.jar`).
  `PsiUtils.positionElement` then takes the position of the navigation element.
  `ImplementationLocations.Collector.addInCallback` keeps each failure except a cancellation and stops
  the search; `throwFailure` throws it after the search.
- **The name enumeration of the file name index ignores the scope.** With the registry key
  `indexing.filename.over.vfs` on (the default), `processNames` of the file contributor goes to
  `FSRecords.processAllNames` (`FileBasedIndexScanUtil.processAllKeys`, pycharm/2026.1.3 and
  pycharm/2026.2.0.1). The scope and the `IdFilter` have no effect, and the names come from the VFS
  name table of the machine, in the order of their first registration. A cap on the names thus keeps
  the names that the VFS saw first and loses files that were indexed later, depending on the index
  state. `FindFileTool.processContributor` never cuts the name enumeration: it ranks the names by
  `matchingDegree`, and the item phase, which filters by the scope, stops at the limit.
- **Find-usages factories can ask a question.** For a member with a base member, the factory or the
  handler of several languages opens a dialog or asserts the EDT (the PHP factory asks about the base
  method; `JavaFindUsagesHandler.getPrimaryElements` calls `SuperMethodWarningUtil`). Thus the direct
  pass of a member with base declarations takes `HIGHLIGHT_USAGES`, and the providers of Java, Kotlin
  and PHP give the references through `findDirectReferences`. The detail is in the KDoc of
  `FindUsagesHandlerSearch.processReferences` and of `findDirectReferences` in
  `JavaSuperMethodsProvider`, `KotlinSuperMethodsProvider` and `PhpSuperMethodsProvider`.
- **Never change the options object of a handler.** `GoFindUsagesHandler` returns one options object
  for each project, which its Find Usages dialog also reads. The search sets the scope and the text
  occurrences only on a `clone()` (`FindUsagesHandlerSearch.searchGo`,
  `KotlinSuperMethodsProvider.findDirectReferences`).
- **Kotlin K2 has no classic quick documentation.** Under K2, `DocumentationProvider.generateDoc` and
  `getQuickNavigateInfo` return null. `ExplainSymbolTool` then asks `PsiDocumentationTargetProvider.EP_NAME`
  for a documentation target: `computeDocumentationHint()` gives the signature, and
  `computeDocumentation()` cast to `DocumentationData` gives the HTML. It skips an asynchronous
  result, and the facet stays null.
- **Kinds from class names need an order.** The third tier of `LanguageServices.getKind`
  (`fallbackKindFromClassName`) tests substrings of the PSI class name in a fixed order. "constructor"
  contains "struct", so the constructor test comes before the struct tests (else
  `KtPrimaryConstructor` is `STRUCT`). A new substring rule goes above each rule whose text it
  contains. The second tier can throw for an element that the provider does not know
  (`XmlFindUsagesProvider.getType` throws `IllegalArgumentException` for an HTML file), so
  `kindFromIdeTypeOrClassName` catches it and goes to the third tier.
- **The JSON of a result encodes defaults.** The serializers of the tool results
  (`AbstractMcpTool.json`, `StructuredToolResult`) have `encodeDefaults = true`, so a new nullable
  field shows as `"field": null` in each response. A field that is absent in the normal case takes
  `@EncodeDefault(EncodeDefault.Mode.NEVER)` (`UsageLocation.match`, `FindUsagesResult.notes`,
  `ExplainSymbolResult.notes`), and its class takes `@OptIn(ExperimentalSerializationApi::class)`.
  Then the JSON omits the field while it is `null`. `FindUsagesResult.warnings` has no such
  annotation, so each `ide_find_usages` response has `"warnings": null`.
