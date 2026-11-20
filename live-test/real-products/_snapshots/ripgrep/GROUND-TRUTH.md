# Captured ground truth: ripgrep

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **ripgrep: the module file.** The bootstrap writes `.idea/ripgrep.iml` with the 16 source and
  test folders that RustRover itself writes at a first open, and `target` excluded. At a later
  open RustRover loads the project model from its cache, the Cargo sync sets the roots, and then
  the IDE applies the module file. A module file with no folder removes all roots, and the scope
  rows then give `scope_matches_no_files` or no subtypes.
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
  equals `hier-caller-search_path-d1`. RustRover removes the scope action from its Call
  Hierarchy window (`RsCallHierarchyBrowser.prependActions`, bytecode).
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
  toolchain version; then these rows need a re-bless.
- **ripgrep: parked rows.** `hier-sub-Flag` is parked with #185 (the subtypes stop at 100 of
  104), `usage-messages-macro-body` and `hier-caller-search_slice-d1` with #186 (an element in
  an injected fragment gets the path and the line of the fragment), `def-pathutil-mod-decl` with
  #187 (a module file gets `crate::pathutil.rs` and the kind `SYMBOL`),
  `find-symbol-f1_sjis-macro-made` with #188 (a function that a macro call makes is absent),
  `def-messages-from-macro-body` with #189 (a position in a fragment is no anchor) and
  `search-text-set_errored` with #184. #190 (the default outline hides the items that macro
  calls make) has no row.
