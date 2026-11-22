# ruff

- Repository: https://github.com/astral-sh/ruff
- Pin: tag `0.16.3`, commit `b0e47022cfce4f3594aa26d15ea792681430b6f6`, committed 2026-08-13
- License: MIT
- IDE: RustRover (port 29178)
- Rust: `rust-toolchain.toml` names the channel `1.97.1`. The workspace has `rust-version = "1.95"`.
  The highest `rust-version` of a locked crate is 1.88 (`globset`, `ignore`, `zip`).
- Workspace: 51 packages, all in `crates/`. `Cargo.lock` has 552 packages: 51 of the workspace
  and 501 from crates.io, none from git. Four packages have a build script (`ruff`, `ty`,
  `ty_vendored`, `ty_wasm`). No build script writes Rust source: three read the git state, and
  `ty_vendored` writes a zip file of the typeshed stubs. One package is a procedural macro
  (`ruff_macros`).
- Macros: the derive macro `ViolationMetadata` writes the `impl ViolationMetadata` of each rule
  (983 types). The attribute macro `map_codes` on `code_to_rule` in
  `crates/ruff_linter/src/codes.rs` writes the enum `Rule`.
- Other files: 3,841 Python files (`.py` and `.pyi`). 3,001 of them are test data below
  `resources/` folders, and 752 are the typeshed stubs in `crates/ty_vendored/vendor/typeshed`.
  3,700 snapshot files (`.snap`). 49 TypeScript files below `playground/`. RustRover has no
  Python plugin, so a Python file is plain text. `fuzz/` is a separate Cargo workspace with its
  own lockfile and is not attached.

## Setup

Run `bootstrap.sh`. It needs `rustup`, `cargo` and `rustc` on the `PATH`.

- The toolchain comes from `rust-toolchain.toml`. The variable `RUSTUP_TOOLCHAIN` overrides that
  file, so the bootstrap clears it for its own calls. `rustup toolchain install` with no name
  installs the toolchain of the file, and `rustup component add rust-src` adds the source of the
  standard library. Neither command changes the default toolchain.
- `Cargo.lock` is committed, and `cargo fetch --locked` refuses each change of it. The crates go
  to the registry of `CARGO_HOME`, outside the checkout.
- The bootstrap installs no Python and no JavaScript package.
- RustRover restores a project at its start only when the folder has IDE project files. So the
  bootstrap writes `.idea/modules.xml` and `.idea/workspace.xml` when they are absent, and
  `.idea/ruff.iml` when its content differs. The workspace file attaches the root `Cargo.toml` and
  names the folder of `cargo` as the toolchain. The product ignores `.idea/` and `target/` in its
  own `.gitignore`.
- The module file is the file that RustRover writes at a first open of a copy with no `.idea`
  folder: 68 folders, `src` and `examples` as source folders and `tests` and `benches` as test
  folders of each workspace package, and `target` excluded. A RustRover with a window asks at
  the first open which `Cargo.toml` files to attach (the box of `fuzz/Cargo.toml` is not
  checked). The bootstrap attaches only the root `Cargo.toml`.
- When the environment of RustRover sets `RUSTUP_TOOLCHAIN`, that toolchain wins over
  `rust-toolchain.toml`: rustup gives the variable precedence over the file. So the pin names
  1.97.1, but on 2026-11-22 the fleet RustRover started with `RUSTUP_TOOLCHAIN=1.96.0` in its
  environment, and the rows ran with 1.96.0. Each Cargo sync of that day logs it (`CargoSyncTask`
  in `idea.log`): `RustcVersion(semver=1.96.0, ...)` and the standard library path
  `.../toolchains/1.96.0-x86_64-unknown-linux-gnu/lib/rustlib/src/rust`.
- The sync and the resolve have no error with 1.96.0. The Sync tool window of a RustRover with a
  window says "Cargo: finished", with no error. The `idea.log` of the fleet RustRover has no
  `ERROR` entry from the start to the end of the first indexing. The rows that resolve into a
  registry crate and into the standard library pass (`canary-def-CompactString-into-dependency`,
  `def-Formatter-into-stdlib`), and the derive macro and the attribute macro expand (983
  implementations of `ViolationMetadata`, the enum `Rule` in Go to Class).
- No row depends on the version. The workspace needs Rust 1.95 (`rust-version`), and no locked
  crate needs more than 1.88. The one row into the standard library keeps only the base name and
  the qualified name of the file (`mod.rs`, `core::fmt::Formatter`), with no line.
- At each open RustRover runs `cargo metadata --all-features` and
  `cargo check --all-targets --workspace` for the build scripts and the procedural macro. The
  check writes `target/` in the checkout. The module file excludes it.

Times on 2026-11-22: the first bootstrap took 7 s and added 367 crates (398 MB) to the
registry. A second run took 0.5 s and changed no file.

## Library files in the expected rows

A file outside the checkout keeps only its base name and its qualified name.

| Row | File | Decided by |
|---|---|---|
| `canary-def-CompactString-into-dependency` | `lib.rs` (`compact_str::CompactString`) | `Cargo.lock`: compact_str 0.10.0 |
| `def-Formatter-into-stdlib` | `mod.rs` (`core::fmt::Formatter`) | `rust-src` of the toolchain that rustup selects |

## Measured

RustRover 2026.3, `-Xmx3072m`, plugin 2.1.1-dev.31, 2026-11-22.

| Item | Value |
|---|---|
| Switch at the first open | 16 s |
| Ready after the switch, first open | 0 s, but the Cargo sync starts the indexing later |
| First indexing: 10,981 files (31 s), then 12,039 files of the crates and the standard library (18 s) after the cargo check | 169 s from the start of the open to the last smart mode |
| Cargo check of the IDE at the first open | about 100 s |
| Second open | switch 17 s, the last dumb pass ends 60 s after the start of the open |
| Rust fixture rows while `ruff` is open | 109 passed (109 before the open) |
| Resident memory of RustRover, `rust` fixture plus `ruff` | 3,632 MB 5 min after the start, 3,476 MB after a full collection |
| Used heap after a full collection | 441 MB |
| Checkout | 116 MB, and 1.1 GB of `target/` that the cargo check of the IDE writes |
| Crates of `Cargo.lock` in the registry | 367 crates that the bootstrap added, 398 MB |
| Product run | 16 s for the first run after an open, 6 to 9 s later; 36 s for the first run after the second open |

The readiness check passes before the Cargo sync. So open the product with
`--open-product ruff`, wait 3 minutes at a first open or 1 minute at a later open, and then run
`--product ruff`.

The first call of each row takes at most 7.1 s (`ide_find_symbol` with the query `new`). The
call hierarchy of `Checker::report_diagnostic` (more than 200 callers) and the callees of
`expression` stop at the node budget at depth 1, so their rows are `shape` rows. The callers of
`is_docstring_stmt` at depth 2 take 6.2 s.

## Import check

Done on 2026-11-22 with plugin 2.1.1-dev.31.

| Call | Result |
|---|---|
| `ide_find_class`, query `LinterSettings` | the struct, `crates/ruff_linter/src/settings/mod.rs:213` |
| `ide_find_definition`, `crates/ruff_linter/src/suppression.rs:1:18` | the struct `CompactString` of compact_str 0.10.0 |
| `ide_find_usages` of `SourceCodeSnippet` | 109 usages |
| `ide_type_hierarchy` of the trait `Violation` | 753 subtypes |
| `ide_file_structure`, `crates/ruff_linter/src/codes.rs` | 35 lines in 0.2 s |

Comparison with RustRover itself. A second RustRover with a window opened a copy of the pin:

- Its project model is the model of the bootstrap: the same module file and the root
  `Cargo.toml` attached.
- Go to Declaration at `suppression.rs:1:18` opens `CompactString` in compact_str. The tool gives
  the same.
- Find Usages of `SourceCodeSnippet` gives 109 usages. The tool gives 109.
- The Code Vision hint of the trait `Violation` says 753 implementations: 752 `impl Violation`
  blocks and the blanket `impl<V: AlwaysFixableViolation> Violation for V`. The tool gives 753.
- The Structure tool window of `codes.rs` shows the same items as the tool. It does not show the
  enum `Rule` that the attribute macro `map_codes` makes.

Project model facts that the probe rows rely on:

- The `tests` folders of the crates are test folders. A test scope finds the usages of
  `lines_before` in `crates/ruff_python_trivia_integration_tests/tests` only.
- The derive macro `ViolationMetadata` writes one `impl ViolationMetadata` for each rule. The
  implementations popup lists the 983 impls in macro expansion files, and a row opens the name in
  the `#[derive(ViolationMetadata)]` line of the source. The tool gives that position.
