<!-- Keep a Changelog guide -> https://keepachangelog.com -->

# IdeSense Changelog

The changelog of the older project, from before the rebrand to IdeSense, is in
[docs/CHANGELOG-before-rebrand.md](docs/CHANGELOG-before-rebrand.md).

## [Unreleased]

### Added
- `ide_call_hierarchy` and `ide_find_usages` accept a `symbol` (name or qualified name) instead of
  `file`/`line`/`column`, resolved like the `ide_explain_symbol` anchor: exact qualified name first,
  then the Go to Symbol popup with the exact-name filter. An ambiguous name returns a `candidates`
  list instead of a guess. A class name given to `ide_call_hierarchy` anchors on its constructor
  where the IDE's provider supports that (Java, Kotlin, Python, Rust); elsewhere the error names the
  class. Calling either tool without `symbol` and without a full position now returns a structured
  `invalid_arguments` error (was a `tool_error` text) (#40).

### Changed
- The name anchors of `ide_explain_symbol`, `ide_type_hierarchy` (`className`), `ide_call_hierarchy`
  and `ide_find_usages` (`symbol`) no longer resolve a qualified method name given without its
  parameter list (`demo.Quirks#parse`) to the provider's first overload: the overloads come back as
  `candidates`, and `demo.Quirks#parse(java.lang.String)` selects one exactly. A file path is no
  longer accepted as a symbol (IntelliJ IDEA's qualified-name provider resolved paths as a last
  fallback); it returns "Symbol not found" (#40).
- The name anchors (`symbol`, `className`) prefer a declaration with the case of the name:
  `Handler` no longer matches a field `handler`. A name with no declaration in that case is still
  found without case. The exact mode of `ide_find_symbol` still ignores case (#131).
- `ide_find_usages` and `ide_explain_symbol` give the `usageType` `COMMENT` to a usage inside a
  comment or a doc comment, in every language. This is the rule of the "Usage in comments" group
  of the IDE's Find Usages window. Such a usage had another type before, in most cases
  `REFERENCE`: for example `Shape` in the PHP doc comment `/** @var Shape[] */`. A caller that
  filters on `REFERENCE` no longer gets these usages (#132).
- `ide_find_usages` and `ide_explain_symbol` include the usages of the base declarations of a Go,
  Java, JavaScript, Kotlin, PHP, Python, Rust or TypeScript member. The result is the union of the
  usages of the member and the usages of each declaration that it overrides or implements. A usage
  of a base declaration has `match: BASE`: the call can run this member or another implementation.
  A usage whose reference matches only by the name has `match: DYNAMIC`. A usage with no `match`
  refers to the member itself. The `notes` entry of `ide_find_usages` names the base declarations
  and gives the count of the `BASE` usages. The `topUsages` of `ide_explain_symbol` lists the code
  usages with no `match` first (#171, #172, #175, #182, #196, #208).
- `ide_find_usages` and `ide_explain_symbol` leave out a key of a Go composite literal that names a
  struct field with the same name as the type of the query (`certmagic.ACMEIssuer{CA: iss.CA}` for
  the type `CA`). Find Usages of GoLand lists such a key as a usage of the type, but the key refers
  to the field. A key of an embedded field names the type and stays in the list.
- The first page of `ide_find_usages` has a `notes` entry for each kind of usage that the result
  leaves out, with the count (`<n> or more` when the search stopped at its limit), and an entry for
  each base method that the search does not search (a method of the Python class `object`).
  `ide_explain_symbol` has the new optional field `notes` with the same entries; its `usageCount`
  and `topUsages` do not hold a usage that is left out.

### Removed
- The default server name and port for JetBrains Aqua (`aqua-idesense`, port 29180). JetBrains
  discontinued Aqua. An IDE with the product code `QA` now gets the defaults of an IDE with no
  entry: `jetbrains-idesense` and port 29199. The ports of the other IDEs do not change (#241).

### Fixed
- The notification that "Copy Configuration" shows for Claude Code, and the README, gave the
  scopes of `claude mcp add` wrong. They now say that `--scope project` writes the shared file
  `.mcp.json`, and that `--scope local`, the default, is the scope for one person in the current
  project.
- `ide_type_hierarchy` and `ide_call_hierarchy` dispose the per-call hierarchy browser once the
  tree is converted. Every call constructed a `HierarchyBrowserBaseEx` (a Swing panel whose
  constructor registers a `SingleAlarm` under it in the Disposer tree) and never released it, so
  an agent that issued hierarchy calls in a loop grew the IDE's Disposer tree and heap for the
  life of the process (#26).
- `ide_type_hierarchy` `className` works on Go and Rust, and resolves plain class names on every
  language. It only used the `QualifiedNameProvider` extension point: in the 2026.2 IDEs RustRover's
  `RsQualifiedNameProvider.qualifiedNameToElement` returns null and GoLand registers no provider, so
  every Go/Rust name reported "Class not found". The lookup now falls back to the Go to Symbol popup;
  a name that is not a class-like declaration returns a clear error (#59).
- `ide_find_implementations` and `ide_explain_symbol` no longer make GoLand rebuild its stub index.
  For a Go method that a type gets through an embedded pointer, GoLand's search returns a light
  element (`GoLightMethodDeclaration`) whose text offset is -1. The tool used that offset inside the
  search callback; the platform took the `IndexOutOfBoundsException` for index damage, rebuilt the
  stub index and put every open project into dumb mode. The tool now takes the position from the
  navigation element, lets no exception except a cancellation leave the search callback, and
  returns the promoted method one time, at its declaration (#129).
- `ide_find_implementations` returns only results whose file is in the `scope`: in GoLand the
  default `project_files` scope returned library types. A result above the collection limit of 500
  no longer ends with `hasMore: false`: a cursor call continues the search, up to the cursor limit
  of 5,000 results. An implementation that a Rust macro writes is listed at the macro call (#134).
- `ide_find_implementations` no longer hides a cancellation of its search for Java lambdas and
  method references. The call then returned a partial list as a success.
- The name anchors of `ide_explain_symbol`, `ide_type_hierarchy`, `ide_call_hierarchy` and
  `ide_find_usages` find a name on a large project. They took the first 40 items of the Go to Symbol
  search and filtered by exact name after that. A name that the popup ranks after many other items
  gave "Symbol not found", a silent choice between two types of the same name, or a cut
  `candidates` list. They now take each item with the exact name, and the message of an ambiguous
  name gives the number of all matches. The exact mode of `ide_find_symbol` had the same cause: it
  lost an exact name that came after its collection cap (#131).
- `ide_search_text` with `context` `code`, `comments` or `strings` returns each match whose
  `contextType` has the related label. The filter was the occurrence mask of the word index, which
  is a different classification: matches in plain text, in HTML and in JSON strings were absent from
  the filtered results. One case is lost: `strings` no longer finds a word that follows an escape
  sequence with no space (`World` in `"Hello\nWorld"`). `all` did not find it before (#133).
- `ide_find_super_methods` at a method that a Go interface declares returns that method with an
  empty hierarchy. The `method` field named the interface, and the hierarchy listed the super
  interfaces of the interface: the result of Go to Super in GoLand for the type. A position on the
  type name still returns them (#135).
- A `FindUsagesProvider` that throws from `getType` no longer fails the whole call with
  `internal_error`. `XmlFindUsagesProvider` throws for an `HtmlFile`, which failed
  `ide_call_hierarchy` when a tree node was an HTML file. The kind then comes from the class name of
  the element (#126).
- `ide_find_usages` on a Go method that implements an interface method also returns the usages of
  the interface method, as Find Usages of GoLand does. The first page names the interface methods
  in a new `notes` field (absent when there are none). The tool asked GoLand's handler factory for
  the handler in a mode that opens the dialog "Find Usages of the Interface Methods?". Off the EDT
  the dialog threw, and the tool returned only the references to the concrete method, with no
  warning. The tool now asks for the handler in the mode of the Find Usages action without its
  dialog. GoLand then shows its notification "Looking for usages of the interface methods" until
  the user selects "Don't show again". A handler factory that throws now gives a `warnings` entry:
  PhpStorm gives it for a method with a base method. The `usageCount` and `topUsages` of
  `ide_explain_symbol` include the same usages (#130).
- `ide_find_usages` and `ide_explain_symbol` in GoLand return the usages in comments, the "Usage in
  comments" group of Find Usages. The tool searched on the path of highlight usages, where the Go
  handler removes the comment references. For Go, the tool now takes the search of the Find Usages
  action. A usage in a comment points at the word, not at the start of the comment.
  `ide_explain_symbol` counts these usages in `usageCount`, and its `topUsages` lists the code
  usages first (#132).
- `ide_find_usages` and `ide_explain_symbol` on a JavaScript or TypeScript member that overrides a
  base member return the usages through the base member. For a member with a base member in
  another class, WebStorm's handler factory asked "Do you want to find usages of the base
  method?". Off the EDT the question threw: the tool searched only the references to the member,
  and each call logged a stack trace. The tool now asks for the handler in the mode of highlight
  usages, which asks no question. It searches each base member in a second pass (#171).
- `ide_find_usages` and `ide_explain_symbol` on an item of a Rust trait impl return the usages
  through the trait item. RustRover's handler factory asked "Do you want to find usages of the base
  declaration?". Off the EDT the question threw: the tool searched only the references to the impl
  item, and each call logged a stack trace. The tool now asks for the handler in the mode of
  highlight usages and searches the trait item in a second pass (#172).
- `ide_find_usages` and `ide_explain_symbol` on a Python method that overrides a method of a base
  class return the usages through the base method. PyCharm's handler factory asked "Do you want to
  find usages of the base method?". Off the EDT the question threw: the tool searched only the
  references to the method, and each call logged a stack trace. The tool now asks for the handler in
  the mode of highlight usages and searches each base method in a second pass. The tool does not
  search a method of the class `object` (#208).
- `ide_find_usages` and `ide_explain_symbol` on a Java method or constructor no longer give the
  `warnings` entry "handler JavaFindUsagesHandler threw on primaryElements" and no longer write two
  stack traces to the IDE log for each call. The handler asserted the EDT for each method and
  constructor. For a method that overrides a super method, the tool returned the usages of the
  deepest super methods with no mark. It now returns the usages of the method itself with no mark
  and the usages of each super method with `match: BASE`. A Kotlin function or property that
  overrides a declaration had the same defect (the `warnings` entry "handler Function threw on
  primaryElements") and now gets the same result (#175).
- `ide_find_usages` and `ide_explain_symbol` mark a dynamic usage with `match: DYNAMIC`. A dynamic
  usage came back with no mark, as a sure usage: for example a call `x.send()` on a value with no
  known type. The mark follows the rule of the "Dynamic usages" group of the IDE's Find Usages
  window, and in JavaScript and TypeScript also the rule of WebStorm. A symbol name in a code span
  of a Markdown file has the mark too, as in the IDE. WebStorm hides these usages by default (#196).
- `ide_find_usages` and `ide_explain_symbol` on a PHP method with a base method no longer give the
  `warnings` entry "Find-usages handler factory PhpFindUsagesHandlerFactory threw while creating
  the handler" and no longer write a stack trace to the IDE log for each call. PhpStorm's handler
  factory asked "Do you want to find usages of base method?", and off the EDT the question threw.
  The tool now asks the factory for no PHP method: it searches the references to the method itself,
  and the usages of each base method and of the other methods that override that base method with
  `match: BASE`. The result holds each usage of the answer "Base Method" (#182).
- `ide_find_usages` and `ide_explain_symbol` on a PHP method also return the usages of each method
  that overrides or implements it, as Find Usages of PhpStorm does. Such a usage has the new mark
  `match: OVERRIDE`: it is a call on a value whose type has the overriding method. At an interface
  method these calls were absent, with no note. The `notes` entry of `ide_find_usages` names the
  overriding methods and gives the count of the `OVERRIDE` usages. The declarations of the
  overriding methods are not usages (#183).
- `ide_find_usages` and `ide_explain_symbol` on a PHP class, interface, trait or enum leave out the
  references through `$this`, `self` or `static` inside the class, as Find Usages of PhpStorm does by
  default. The tool listed them as plain usages. The first page has a `notes` entry with their
  count (#179).
- `ide_find_usages` no longer shows a `warnings` or a `notes` entry two times when the IDE started
  the search again after a write action.
- `ide_find_usages` and `ide_explain_symbol` name the class in the `warnings` entry of a
  find-usages handler or handler factory that throws, also when the class is anonymous. The entry
  had two spaces and no name, for example
  `Find-usages handler  threw on findReferencesToHighlight` for the handler of PyCharm for a class.
  The name of an anonymous class is now the class name without the package, for example
  `PyFindUsagesHandlerFactory$1`. The entry for a named class does not change (#206).
- `ide_explain_symbol` gives `usageCount: 200` and `usagesTruncated: true` for a symbol with more
  than 200 usages. For a Go symbol, the count was 200, 201 or 202, and equal calls gave different
  values. The search of the IDE gives usages from more than one thread, and some usages arrive
  after the tool stops the search. The tool counted these usages too (#215).
- The companion skill (`SKILL.md`, `tools-reference.md`) had wrong or absent facts about the
  tools. It now says that the `subtypes` of `ide_type_hierarchy` is a flat list, that a fresh
  `ide_find_usages` search takes the `symbol` anchor or a position, and that `ide_find_file` and
  `ide_search_text` return the pagination fields. It also gives the limit of 100 `problems` of
  `ide_diagnostics` (with no truncation flag), the stop of a cursor at 5,000 results, one
  `ide_search_text` match for each line, and the project-only file paths of `ide_type_hierarchy`
  (file mode) and `ide_file_structure`.
- The change notes of the plugin take no text of the older project. `CHANGELOG.md` also held the
  changelog of the older project, and IdeSense uses its version numbers again. The build took the
  change notes of the 2.0.0 plugin from the section `[2.0.0]` of the older project, and it merged
  the two sections `[1.0.0]`. The changelog of the older project is now in
  `docs/CHANGELOG-before-rebrand.md`.
- The description of the server no longer names "safe delete" as a capability. No tool does safe
  delete (#169).
- The descriptions of `ide_file_structure` and `ide_find_symbol` no longer say "disabled by
  default". Both tools are on by default (#168).
- `ide_file_structure` no longer puts parts of an annotation or a decorator into the modifiers of a
  declaration. When the arguments had white space, parts of them stayed at the start of the line.
  For example, `@Deprecated(since = "3.9")` gave
  `= "3.9") static public loadDataAndPrepareJob(...)`. The line now starts with the keywords only:
  `static public loadDataAndPrepareJob(...)`. Java and Kotlin annotations and JavaScript and
  TypeScript decorators had this defect (#173).
- A cancelled tool call no longer writes error entries to the IDE log. The server logged the
  cancellation with its exception, and the platform logger wrote "Control-flow exceptions ...
  should never be logged" in place of the exception. When the IDE stopped the MCP server during a
  call, the server also updated the command history of the disposed project. That update gave a
  second entry. Now a cancellation of the call itself ends the call with no log entry, no history
  update and no answer. This occurs, for example, when the server stops. A change of the host or
  the port in the settings starts the server again. The restart cancels a call that runs for more
  than one second, except a call over SSE. The entry of that call in the command history now keeps
  the status PENDING, where it got ERROR before. The IDE can also cancel an operation while the
  call is still active, for example when the index is not ready after an IDE start. Then the
  client gets the same answer as before, and the log gets one warning line with no exception
  (#127).
- `ide_sync_files` no longer logs two SEVERE entries ("Cannot run synchronous
  submitTransactionAndWait" and "Write-unsafe context!") that name IdeSense as the plugin to blame.
  Each request ran with the modality `ModalityState.any()`, and the platform permits no document
  commit in that modality. Each request now runs with `ModalityState.nonModal()`. The same commit
  also runs after a rename of `ide_refactor_rename`, and before a tool call when the setting "Sync
  external file changes before operations" is on. While a modal dialog is open in the IDE, a tool
  step that writes (for example this commit) waits until the dialog closes. The searches and
  `ide_diagnostics` do not wait, unless the setting "Sync external file changes before operations"
  is on: then each of these tools commits the documents first, and that step waits (#145).
- `ide_restart` no longer logs SEVERE entries "Write-unsafe context!" when the IDE saves the
  documents and the projects before the restart. The restart request ran with
  `ModalityState.any()`, and it now runs with `ModalityState.nonModal()`. While a modal dialog is
  open, the restart waits until the dialog closes (#147).
- `ide_find_super_methods` no longer returns an empty `hierarchy` when a write action interrupts
  the search of the super methods. The provider of the language took the cancellation for a
  failure, so the IDE did not run the search again. `ide_find_usages` and `ide_explain_symbol` take
  their base declarations from the same search. The search now starts again, in Go, JavaScript,
  Kotlin, PHP, Python, Rust and TypeScript (#210).
- The toolbar actions Clear History, Export History and Refresh of the IdeSense tool window update
  on a background thread. They updated on the EDT, so each update of the toolbar waited for the
  EDT. The IDE logged `to grab EDT for` lines for them (#128).
- A Rust module file as a result gets the module path of RustRover as its `qualifiedName`, and the
  `kind` `MODULE`. For example, `ide_find_definition` at `mod pathutil;` gave `crate::pathutil.rs`
  and `SYMBOL`. It now gives `globset::pathutil` and `MODULE`, the name that Copy Reference gives.
  When RustRover gives no module path, `qualifiedName` is `null`. A file as a result now also goes
  to the qualified-name providers of the other languages. In IntelliJ IDEA, a Gradle build script
  can now get the Gradle path of its project (#187).
- A PHP class constant gets the `kind` `CONSTANT`, as a PHP constant outside a class. It had the
  `kind` `CLASS`, because the type name "Class constant" of PhpStorm contains "class" (#180).
- The `qualifiedName` of a Go struct field holds the name of its struct: `package.Struct.field`.
  It was `package.field`, so the fields of one name in two structs of one package had one name.
  For example, `ide_find_symbol` with the query `handler` on caddy gave `reverseproxy.handler` for
  two fields. They are now `reverseproxy.metricsUpstreamsHealthyUpdater.handler` and
  `reverseproxy.handleResponseContext.handler`. An embedded field gets the same form. A field of an
  anonymous struct gets the name of the nearest enclosing type declaration, and `package.field`
  when it has none. GoLand gives `package.field`: this name differs from GoLand on purpose (#136).
  The new name is no `symbol` anchor, as the name of a Go method (#139): use a position for a field.

## [2.1.0] - 2026-11-09

### Added
- New `ide_explain_symbol` tool (#41): fused one-round-trip symbol overview — declaration +
  signature + quick documentation (plain text) + supers + implementations + usage summary,
  with optional declaration diagnostics via `includeDiagnostics`. Anchors on a symbol name /
  qualified name (an ambiguous name returns a candidates list instead of guessing) or an
  exact file position, so agents can skip the find-coordinates-first step.

### Changed
- `ide_call_hierarchy`: the default `maxDepth` is 3 (was 7), and the tree holds at most 200 nodes,
  filled depth-first. A new `truncated` field is `true` when the walk stopped at this limit.
  Callers trees of frequently called functions were 60K–250K characters before and failed in
  clients (#116).
- `project_production_files` / `project_test_files` in a project without production (or test)
  source roots now return a `scope_matches_no_files` error instead of an empty list, in
  `ide_find_usages`, `ide_find_symbol`, `ide_find_file`, `ide_find_class` and
  `ide_find_implementations`. The scope itself keeps the IDE's semantics (the IDE's
  "Project Production Files" scope is also empty there); the error only makes the empty scope
  visible, because `[]` read as "no usages" (#116).
- `ide_find_symbol` and `ide_explain_symbol` order same-name symbols: declarations (class,
  function, …) before values (field, variable, …), then a symbol declared in a file of its own
  name. The Go to Symbol popup sorts same-name items by proximity to the file open in the
  editor; a headless call has no editor, so the old order was arbitrary and could put attribute
  assignments above the declaration. Remaining ties sort by file, line and column, so the order
  is the same in every IDE session. Names keep the popup's match order (#116).
- `ide_index_status` without `project_path` while several projects are open returns the status
  of every open project (`projects: [{name, path, isDumbMode}]`) instead of
  `multiple_projects_open` (#116).
- `ide_diagnostics`: `problems` and `problemCount` are `null` when the file analysis timed out,
  instead of an empty list that read as a clean file (#116).
- Paginated tools echo the page size of the call in `pageSize`; it was `0` on an empty page and
  the item count on a short page (#116).

### Fixed
- Source-line text is bounded: `preview` (`ide_find_usages`, `ide_find_definition`,
  `ide_explain_symbol`) and `ide_search_text` match `context` hold at most 200 characters of
  the line, cut to a window around the match with `…` at each cut end. One match on a minified
  line was 1.66M characters before, and a smaller `pageSize` could not help (#116).
- `ide_search_text` reports `line` and `column` of the occurrence itself. A word inside a
  multi-line comment or string was reported on the comment's first line, or not at all. The
  search also no longer copies the whole line for every PSI ancestor of an occurrence (#116).
- Caret errors of `ide_find_usages`, `ide_call_hierarchy` and `ide_find_implementations` name up
  to 3 named elements of the requested line with their columns, or say that the line is blank
  (#116).
- A platform "PSI and index do not match" failure returns a retryable `index_out_of_sync` error
  instead of `internal_error` with the raw platform text, and is logged at WARN, not ERROR (#116).
- `ide_sync_files` names requested paths that are excluded from the project (and are not part
  of a library): the IDE refreshes them but does not index them (#116).
- `ide_find_file` no longer drops in-scope files on extension-only queries (`*.py`, `.py`, `py`).
  The default contributor enumerates the machine-global VFS name table in append order
  (scope and `IdFilter` are ignored on that path), so the old `limit*3` candidate-name cap
  filled up with library names matching the un-anchored pattern (typeshed stubs, SDK
  sources) and starved recently indexed project files. The name enumeration is no longer
  truncated; names are ranked by matching degree and the scope-filtered item phase stops at
  the collection limit instead. Was most visible on PyCharm, where `*.py` could collapse to
  a single file (#87).
- `ide_find_file` no longer swallows file-contributor failures at debug level: a contributor
  that throws mid-search is logged at WARN and reported through a `warnings` list on the first
  page (same contract as `ide_find_usages`), and cancellation exceptions are rethrown instead
  of being eaten, preserving the read-action retry contract (#87).
- `ide_find_usages` no longer degrades silently when a language's find-usages handler throws
  during target expansion: the response now carries a `warnings` list naming each failed
  stage (`primaryElements` / `secondaryElements` / `findReferencesToHighlight`), so agents
  can tell a partial result from a complete one. `ide_explain_symbol`'s usage facet reports
  the same degradation through its existing `warnings` field. `warnings` is `null` on
  complete searches (#81).
- `ide_find_definition` on a Kotlin constructor call now reports the class being constructed
  — kind `CLASS`/`DATA_CLASS` and class qualified name, matching the declaration-site result
  and Java's `new Foo()` behavior — instead of `STRUCT` with a member-style qualified name (#17).
- `ide_find_file` no longer doubles a leading `*` wildcard when building its match pattern,
  so queries like `*.java` and `*Test.kt` match exactly as written (#16).

## [2.0.0] - 2026-07-18

### Removed
- **Seven tools removed** in refocusing IdeSense on code analysis without human-in-the-IDE
  interaction: `ide_open_file` and `ide_get_active_file` (editor interaction),
  `ide_refactor_safe_delete`, `ide_optimize_imports`, `ide_convert_java_to_kotlin`, and
  `ide_reformat_code` (code mutation), `ide_build_project` (dev-loop driver). **Breaking** for
  MCP clients that call these tools. `ide_refactor_rename` and `ide_move_file` remain as the
  minimal retained refactorings.
- **`totalCount` removed from every paginated search result** (`ide_find_usages`, `ide_find_class`,
  `ide_find_symbol`, `ide_find_file`, `ide_find_implementations`, `ide_search_text`). It duplicated
  `totalCollected`, but the name implied a whole-project total, so an agent could stop paginating
  early and miss results. Completeness is signalled by `hasMore`/`nextCursor`; `totalCollected` (the
  collected count) remains. **Breaking** for clients that read `totalCount` (#30).
- **`isIndexing` and `indexingProgress` removed from `ide_index_status`.** `isIndexing` always
  mirrored `isDumbMode` and `indexingProgress` was always `null`; the result is now just
  `{ isDumbMode }`. **Breaking** for clients that read those fields (#31).

### Changed
- Mission statements (README/Marketplace description, CLAUDE.md, agent skill) rewritten to the
  analysis-first philosophy. `ide_diagnostics` still reports last-build errors via the passive
  build listener — only the ability to *trigger* builds is gone.
- **Error taxonomy unified** so agents parse one shape. `invalid_scope` is now built from the central
  `McpErrors` vocabulary — it gains a human-readable `message`; `error`/`parameter`/`provided`/
  `supportedValues` are unchanged — across all seven scope-taking tools (the five search tools plus
  `ide_type_hierarchy`/`ide_call_hierarchy`). A missing `query` on the search tools now returns the
  structured `invalid_arguments` shape (a `missing_required` violation) instead of a generic
  `tool_error` string. **Breaking** for clients that matched the old missing-`query` message (#39).
- **Analysis-only default tool set.** Fresh installs now enable every read-only analysis tool:
  `ide_find_symbol` and `ide_file_structure` leave the default-disabled set (#72). The retained
  refactorings `ide_refactor_rename` and `ide_move_file` become opt-in instead, joining
  `ide_install_plugin`, `ide_restart`, and `ide_read_file` (enable any tool under Settings →
  Tools → IdeSense). Installs that ever saved the tool toggles are unaffected — persisted
  settings replace the defaults entirely. **Breaking** for MCP clients on fresh installs that
  call the refactoring tools without opting in.

### Added
- **Security — non-loopback bind is now opt-in.** There is no authentication on any transport, so
  binding a non-loopback host (`0.0.0.0`, a LAN address, …) hands every enabled tool to any machine
  that can reach the port. A new **Allow non-loopback bind** setting (off by default) must be
  ticked for such a host to be honored; without it the server falls back to `127.0.0.1`, keeps
  running (local agents are unaffected), and warns via notification. URLs reported in the status
  panel and generated client configs now reflect the host actually bound, not the configured one
  (#25).

### Fixed
- **Security:** disabled tools are now refused at the `tools/call` dispatch site instead of only
  being hidden from `tools/list`; a client that already knows a disabled tool's name gets a
  clear "disabled by user settings" error (#23).
- **Security:** `ide_install_plugin` requires the source `.zip` to resolve (canonically, symlinks
  followed) inside the open project's roots, mirroring the containment other file-taking tools
  apply; out-of-root paths are rejected. For cross-project dev loops, copy the zip into the
  target project first (#24).

## [1.0.0] - 2026-06-25

### Changed
- **Renamed to IdeSense** and established as an independent project, forked from
  [`jetbrains-index-mcp-plugin`](https://github.com/hechtcarmel/jetbrains-index-mcp-plugin) by
  Carmel Hecht (MIT). New plugin id `com.github.vcth4nh.idesense`; MCP server ids renamed
  `<ide>-index` → `<ide>-idesense`. **Existing users must update their MCP client config to the new
  server name.**
