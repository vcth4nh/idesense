# Captured ground truth: ripgrep

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **ripgrep: the module file.** The scope rows need the 16 source and test folders of the module
  file that the bootstrap writes (see "Setup" in [notes.md](../../_setup/ripgrep/notes.md)).
  When the module file has no folder, the scope rows give `scope_matches_no_files` or no subtypes.
- **ripgrep: `crates/core` is in no source folder.** It holds the targets of the root package.
  So `hier-sub-Flag-production-scope` gives 0 subtypes, and `find-file-mod.rs` gives 5 files and
  its production scope 2.
- **ripgrep: a trait impl method gets the usages of the trait item (#172).**
  `usage-RegexMatcher.find_at-trait-impl` gives 26 usages, all with `match` `BASE`, and the
  `notes` entry names `grep_matcher::Matcher::find_at` (`crates/matcher/src/lib.rs:571:8`). The
  row has no `warnings` entry. RustRover, answer Yes: "Usages in Project Files 26 results" (4 in
  `crates/matcher/src`, 22 in `crates/searcher/src`). Answer No: "Nothing found".
- **ripgrep: the Rust type hierarchy is code of the plugin.** RustRover has no Type Hierarchy
  for Rust, so no IDE action decides these rows. A blanket `impl` for a reference (`&'a mut S`)
  is no subtype node: `hier-sub-Sink` gives 8 types, and `impls-Sink-trait` gives 9 `impl`
  blocks.
- **ripgrep: the Rust call hierarchy has no scope.** `hier-caller-search_path-production-scope`
  equals `hier-caller-search_path-d1`: it lists the caller in `crates/core/search.rs`, a file
  in no source folder. RustRover removes the scope action from its Call Hierarchy window
  (`RsCallHierarchyBrowser.prependActions`, bytecode).
- **ripgrep: a call in a `macro_rules!` body is no caller.** `hier-caller-set_errored-macro-body`
  gives no caller: the only call is in the body of `err_message!`. The Hierarchy window of
  RustRover shows none.
- **ripgrep: a usage in a Markdown code span.** `usage-matched_path_or_any_parents` gives 6
  usages: 5 calls in a test file and the code span at `CHANGELOG.md:1241`. Find Usages of
  RustRover shows "Usages in Project Files" (5 results) and a separate group "Dynamic usages in
  Project Files" with one "Unclassified" usage at that line. The tool gives the sum, 6, and the
  code span usage has the `usageType` `REFERENCE` and `match` `DYNAMIC`. The Markdown plugin
  makes this reference: `BacktickReferenceSearcher` searches the name in Markdown files, and
  `BacktickReference.isReferenceTo` accepts the same name when it has 10 or more characters or
  more than one word (bytecode, build 262.8665). The source of the IDE rule:
  `BacktickUsageViewElementsListener` (`plugins/markdown/lib/intellij.markdown.jar`, build
  262.8665) calls `setDynamicUsage(true)` for a usage in a `MarkdownCodeSpan` that has a
  `BacktickReference`.
- **ripgrep: dependency rows.** `canary-def-ByteSlice-into-dependency` resolves into bstr, and
  `Cargo.lock` decides its version. `def-Vec-into-stdlib`, `hier-sub-Sink`,
  `hier-callee-add_parents-d1` and `hier-callee-search-d1` name files of the standard library of
  the toolchain that rustup selects (`rust-src`). A module path of `std` can change with the
  toolchain version (for example `std::sync::poison::rwlock::RwLock::write` in
  `hier-callee-add_parents-d1`); then these rows need a re-bless.
- **ripgrep: `ide_file_structure` in dumb mode.** Since the fix of #174, `ide_file_structure`
  answers `index_not_ready` in dumb mode (`docs/USAGE.md`, `ide_file_structure`). Before it,
  the tool gave `internal_error` (`IndexNotReadyException` of RustRover) and not a reduced
  outline; the comment on #174 has the stack. For the wait after an open, see "Measured" in
  `live-test/real-products/_setup/ripgrep/notes.md`.
- **ripgrep: two `shape` rows hold elements of a doctest (#186).**
  `hier-caller-search_slice-d2` and `usage-Match-page1` hold elements of a doctest with the
  path of the fragment. They are `shape` rows: their counts equal the counts of RustRover, and
  the fix of #186 keeps them. So they are not parked.
- **ripgrep: parked rows.** Each of these rows shows an open defect (see "Parked rows" in
  `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `usage-messages-macro-body`, `hier-caller-search_slice-d1` | #186 | an element in an injected fragment (a `macro_rules!` body, a doctest) gets the path and the line of the fragment; the two usages of `messages()` in macro bodies count as one |
  | `find-symbol-f1_sjis-macro-made` | #188 | a function that a macro call makes is absent (the 330 tests of `rgtest!`) |
  | `def-messages-from-macro-body` | #189 | a position inside an injected fragment is no anchor |

  #190 (the default Rust outline hides the items that macro calls make) has no row: a row
  would also show the line of #188. No structure row of this product has a macro-made item.
