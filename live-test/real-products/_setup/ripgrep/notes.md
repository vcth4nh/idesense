# ripgrep

- Repository: https://github.com/BurntSushi/ripgrep
- Pin: tag `15.0.0`, commit `3a612f88b805e14aef45bfa43e25a54abc6297fc`, committed 2025-10-15
- License: Unlicense OR MIT
- IDE: RustRover (port 29178)
- Rust: `rust-version = "1.85"` in `Cargo.toml`. The fleet toolchain is 1.96.0 with the
  component `rust-src`. The product has no `rust-toolchain` file.
- Workspace: 10 packages. The root package `ripgrep` has its targets in `crates/core`
  (`crates/core/main.rs`); the other 9 are `crates/{cli,globset,grep,ignore,matcher,pcre2,
  printer,regex,searcher}`. `Cargo.lock` has 61 packages: 10 of the workspace and 51 from
  crates.io. `fuzz/` is a separate Cargo workspace with its own lockfile and is not attached.

## Setup

Run `bootstrap.sh`. It needs `cargo` and `rustc` 1.85 or later on the `PATH`, and the
component `rust-src` of the toolchain. It runs `cargo fetch --locked`, writes
`.idea/modules.xml` and `.idea/workspace.xml` when they are absent, and writes
`.idea/ripgrep.iml` when its content differs. The product ignores `/.idea` and `target` in its
own `.gitignore`.

- `Cargo.lock` is committed, and `--locked` refuses each change of it. The crates go to the
  registry of `CARGO_HOME`, outside the checkout (51 crates, 76 MB).
- RustRover restores a project at its start only when the folder has IDE project files. A
  restored project does not look for its `Cargo.toml`: `guessAndSetupRustProject` returns when
  the discovery flag of the project is set, and only the open of a new folder and some UI
  actions call it (bytecode of `intellij.rustrover.core.jar`, build RR-262.8665.323). So
  `workspace.xml` attaches the root `Cargo.toml` (component `CargoProjects`) and names the
  folder of `cargo` as the toolchain (component `RustProjectSettings`). rustup then selects its
  default toolchain.
- The module file holds the 16 source and test folders that RustRover itself writes for this
  pin: `src` and `examples` of a package are source folders, `tests` and `benches` are test
  folders. The Cargo sync sets these roots at each open. But at a later open the IDE loads
  its project model from its cache, the Cargo sync commits the roots, and then the IDE applies
  the module file (`JpsProjectModelSynchronizer` in `idea.log`). A module file with no source
  folder then removes all roots. RustRover in `serverMode` does not save the module file.
  Evidence: on 2026-11-12 a RustRover with a window opened a copy of the pin with no `.idea`
  folder, and at its first open it wrote a module file with these 16 folders and `target`
  excluded. The module file of the bootstrap has the same content.
- A new pin with another crate layout needs new folders. Open the new pin one time in a
  RustRover with a window and no `.idea` folder, cancel the question about `fuzz/Cargo.toml`,
  and copy the folders of the module file that RustRover writes into `bootstrap.sh`.
- At each open RustRover runs cargo itself: `cargo metadata --all-features`, `cargo check
  --all-targets --workspace` (build scripts and procedural macros) and `cargo rustc --print
  cfg`. The check writes `target/` in the checkout (84 MB). The module file excludes it.
- A RustRover with a window asks at the first open whether to attach `fuzz/Cargo.toml` (the
  box is not checked). The bootstrap does not attach it.

Times on 2026-11-12: the first `cargo fetch` took 2.5 s with the downloads. With a warm
registry the bootstrap runs in 0.2 s. On 2026-11-13 two more runs took 0.14 s and 0.17 s and
changed no file.

## Library files in the expected rows

A file outside the checkout keeps only its base name and its qualified name.

| Row | File | Decided by |
|---|---|---|
| `canary-def-ByteSlice-into-dependency` | `ext_slice.rs` (`bstr::ext_slice::ByteSlice`) | `Cargo.lock`: bstr 1.12.0 |
| `def-Vec-into-stdlib` | `mod.rs` (`alloc::vec::Vec`) | `rust-src` of the toolchain that rustup selects (1.96.0 on the fleet). RustRover reads a copy of it in its system folder. |
| `hier-sub-Sink` | `boxed.rs` (`alloc::boxed::Box`) | the same toolchain |
| `hier-callee-add_parents-d1`, `hier-callee-search-d1` | 16 files of `core`, `alloc` and `std` | the same toolchain. A module path of `std` can change with the toolchain version (for example `std::sync::poison::rwlock::RwLock::write`); then these two rows need a re-bless. |

## Measured

RustRover 2026.2 (RR-262.8665.323), `-Xmx2048m`, plugin 2.1.1-dev.12, 2026-11-12.

| Item | Value |
|---|---|
| Switch: stop RustRover, mark the projects, start, all projects listed | 11 s |
| Ready after the switch, first open | 15 s |
| First indexing: 1,671 files, then 9,705 files of `target/` after the cargo check | 24 s from the open to the last smart mode |
| Rust fixture rows while `ripgrep` is open | 107 passed (107 before the open) |
| Resident memory of RustRover, `rust` fixture plus `ripgrep` | 3,254 MB 74 s after the start, 2,649 MB after a full collection |
| Used heap after a full collection | 306 MB |

The used heap stays far below 1200 MB (60% of the limit), so RustRover keeps `-Xmx2048m`.

A next open takes 11 s for the switch. The readiness check passes after 0 to 10 s, but the
Cargo sync and the cargo check of the IDE come later: in three later opens the IDE was in
dumb mode again for 2 to 10 s, and smart for good only 18 to 25 s after its start. A row that
runs in that time gives `index_not_ready`. The canary rows hold a run until they match, but a
second dumb pass can come after them. So open the product with `--open-product ripgrep`, wait
30 s, and then run `--product ripgrep`. In the cycle of 2026-11-13 the switch took 16 s, the
last dumb pass ended 16 s after the open, and no row of the run met dumb mode.

## Import check

Done on 2026-11-12 with plugin 2.1.1-dev.12. The product is accepted.

| Call | Result |
|---|---|
| `ide_find_class`, query `LineBuffer` | the struct, `crates/searcher/src/line_buffer.rs:294` |
| `ide_find_definition`, `crates/searcher/src/line_buffer.rs:3:11` | the trait `ByteSlice` of bstr 1.12.0 |
| `ide_find_usages` of `Matcher::find_at` | 26 usages |
| `ide_find_implementations` of the trait `Flag` | 104 `impl` blocks |
| `ide_file_structure`, `crates/core/flags/defs.rs` (235 KB) | 1,094 lines in 0.7 s |

The three files of the agent task are indexed: `file_name` in `crates/ignore/src/pathutil.rs` has
5 usages, `LineBuffer::fill` 1 and `Ignore::add_parents` 4.

Comparison with RustRover itself. A second RustRover with a window opened a copy of the pin
with no `.idea` folder:

- Its project model is the model of the bootstrap: the same module file (16 folders, `target`
  excluded) and the root `Cargo.toml` attached.
- Go to Declaration at `crates/searcher/src/line_buffer.rs:3:11` opens `ByteSlice` in bstr.
- Find Usages: `LineBuffer` 8 results, `Matcher::find_at` 26 results. The tool gives the same.
- Choose Implementation of `Flag`: 104. The tool gives the same.
- Find Usages of `Gitignore::matched_path_or_any_parents`: 5 method calls, and one
  "Unclassified" usage in the group "Dynamic usages in Project Files", the code span at
  `CHANGELOG.md:1241`. The tool gives the 6 usages.

Project model facts that the probe rows rely on:

- `crates/core` holds the targets of the root package, and it is in no source folder. So a
  file of `crates/core` is in no production scope and in no test scope:
  `hier-sub-Flag-production-scope` gives 0, `find-file-mod.rs` gives 5 files and the production
  scope 2. A `#[cfg(test)]` module in a `src` folder is production code for the scopes.
- The usage scopes work: `matched_path_or_any_parents` has 6 usages, 0 in production files and
  5 in test files. The sixth is a reference in `CHANGELOG.md`. The canary scope row needs the
  test folders of the module file.
- The Rust type hierarchy takes the scope (`Matcher`: 5 subtypes, 3 production, 2 test).
- The Rust call hierarchy has no scope: `RsCallHierarchyBrowser.prependActions` removes the
  scope action (bytecode). `hier-caller-search_path-production-scope` lists the caller in
  `crates/core/search.rs`.
- `cfg` is evaluated for the host (unix) and for the features of the sync. The `not(unix)`
  twin of `file_name` has no usage; Find Usages of RustRover says "Nothing found". A call in
  the `cfg(windows)` function goes to the unix `file_name`; Go to Declaration does the same.
  The macro `debug!` of globset resolves to its `cfg(feature = "log")` definition.
- Macros: RustRover injects Rust into the body of each `macro_rules!` (a fragment that it
  wraps in `fn __injected`, `RsMacroDefinitionInjector`) and into each code block of a doc
  comment (a doctest `fn __main`). A function that a macro call makes, for example the 330
  tests of `rgtest!`, lives in an expansion file that no search scope holds. The 104 `impl
  Flag for` blocks are written by hand, not by a macro.
- The Rust outline shows names, visibility, signatures, `impl` headers, the type of an
  associated constant, fields and enum variants. It shows no value, no attribute and no
  comment. So each structure row can be `exact`; `file-structure-defs.rs` is `shape` because of
  its size.

Tools with no row:

- `ide_diagnostics`: a closed file gets the batch inspections of the IDE build only, and the
  result also depends on the state of the cargo check of the IDE. The other products have no
  diagnostics row either.
- `ide_refactor_rename`, `ide_move_file`, `ide_sync_files`, `ide_restart`,
  `ide_install_plugin`: no product row uses a tool that writes.

## Issues

These rows are parked. Each one changes with the fix of its issue only.

| Row | Issue |
|---|---|
| `hier-sub-Flag` | #185: the subtypes of a trait stop at 100 with no signal (104 types implement `Flag`) |
| `usage-messages-macro-body`, `hier-caller-search_slice-d1` | #186: an element in an injected fragment (a `macro_rules!` body, a doctest) gets the path and the line of the fragment; the two usages of `messages()` in macro bodies count as one |
| `def-pathutil-mod-decl` | #187: a module file gets the qualified name `crate::pathutil.rs` and the kind `SYMBOL` |
| `find-symbol-f1_sjis-macro-made` | #188: a function that a macro call makes is absent (the 330 tests of `rgtest!`) |
| `def-messages-from-macro-body` | #189: a position inside an injected fragment is no anchor |
| `search-text-set_errored` | #184: a match in a `macro_rules!` body comes a second time, with the path `/messages.rs` |

#190 (the default Rust outline hides the items that macro calls make) has no row: a row would
also show the line of #188. No structure row of this product has a macro-made item.

`usage-RegexMatcher.find_at-trait-impl` is blessed with its `warnings` entry: its 0 usages equal
the answer No to the question of RustRover ("Nothing found"). #172 tracks the warning.

`hier-caller-search_slice-d2` and `usage-Match-page1` also hold elements of a doctest with the
path of the fragment (#186). They are `shape` rows: their counts equal the counts of RustRover,
and the fix of #186 keeps them.

In dumb mode `ide_file_structure` gives `internal_error` (`IndexNotReadyException` of RustRover)
and not a reduced outline; the comment on #174 has the stack. See "Measured" for the wait after
an open.
