# rolldown

- Repository: https://github.com/rolldown/rolldown
- Pin: tag `v1.2.4`, commit `483c64833c0fb0d1b75f1339accf781c0a09b335`, committed 2026-08-12
- License: MIT
- IDE: RustRover (port 29178)
- Rust: `rust-toolchain.toml` names the channel `1.97.1` with the profile `default`. No
  package of the workspace has a `rust-version`. The highest `rust-version` of a locked crate is
  1.95.0 (`oxc` 0.144.0).
- Workspace: 52 packages, 49 in `crates/` and 3 in `tasks/`. `Cargo.lock` has 405 packages: 52
  of the workspace and 353 from crates.io, none from git. Two packages have a build script
  (`rolldown_binding`, `rolldown_testing`); no package of the workspace is a procedural macro.
- JavaScript: a pnpm workspace (`packageManager` `pnpm@11.17.0`, `pnpm-lock.yaml`), with the
  TypeScript sources of the npm package in `packages/rolldown/src`.
- Test data: 12,463 of the 14,003 tracked files are below a `tests` folder (10,380 in
  `crates/rolldown/tests`, 1,597 in `packages/rolldown/tests`). 693 tracked files are below a
  `node_modules` folder in the test data. The two submodules `rollup` and `test262` hold test
  data and stay empty.

## Setup

Run `bootstrap.sh`. It needs `rustup`, `cargo` and `rustc` on the `PATH`.

- The toolchain comes from `rust-toolchain.toml`. The variable `RUSTUP_TOOLCHAIN` overrides that
  file, so the bootstrap clears it for its own calls. `rustup toolchain install` with no name
  installs the toolchain of the file, and `rustup component add rust-src` adds the source of the
  standard library. Neither command changes the default toolchain.
- `Cargo.lock` is committed, and `cargo fetch --locked` refuses each change of it. The crates go
  to the registry of `CARGO_HOME`, outside the checkout.
- The bootstrap installs no JavaScript package.
- RustRover restores a project at its start only when the folder has IDE project files. So the
  bootstrap writes `.idea/modules.xml` and `.idea/workspace.xml` when they are absent, and
  `.idea/rolldown.iml` when its content differs. The workspace file attaches the root
  `Cargo.toml` and names the folder of `cargo` as the toolchain. The product ignores `.idea` and
  `target` in its own `.gitignore`.
- The module file is the file that RustRover writes at a first open of a copy with no `.idea`
  folder: 63 folders, `src` and `examples` as source folders and `tests` and `benches` as test
  folders of each workspace package, and `target` excluded.
- When the environment of RustRover sets `RUSTUP_TOOLCHAIN`, that toolchain wins over
  `rust-toolchain.toml`: rustup gives the variable precedence over the file. On 2026-11-22 the
  fleet RustRover started with `RUSTUP_TOOLCHAIN=1.96.0` in its environment, so the rows ran
  with 1.96.0, not with 1.97.1. Each Cargo sync of that day logs it (`CargoSyncTask` in
  `idea.log`): `RustcVersion(semver=1.96.0, ...)` and the standard library path
  `.../toolchains/1.96.0-x86_64-unknown-linux-gnu/lib/rustlib/src/rust`.
- No row depends on this version. No locked crate needs more than 1.95. Only one row resolves
  into the standard library (`def-Arc-into-stdlib`), and a file outside the checkout keeps only
  its base name and its qualified name (`sync.rs`, `alloc::sync::Arc`), with no line.
- `cmake` is not installed. The build script of `libmimalloc-sys2` fails, and the Cargo sync
  reports 3 errors. No row resolves into this crate or into its generated code.

## Library files in the expected rows

A file outside the checkout keeps only its base name and its qualified name.

| Row | File | Decided by |
|---|---|---|
| `canary-def-ArcStr-into-dependency` | `arc_str.rs` (`arcstr::arc_str::ArcStr`) | `Cargo.lock`: arcstr 1.2.0 |
| `def-Arc-into-stdlib` | `sync.rs` (`alloc::sync::Arc`) | `rust-src` of the toolchain that rustup selects |
| `explain-Plugin-ambiguous` | `lib.es5.d.ts` (`Partial`) | the TypeScript library that RustRover bundles |

## Measured

RustRover 2026.3 (RR-263.7307.313), `-Xmx3072m`, plugin 2.1.1-dev.23, 2026-11-22. The heap
limit is a condition of these values: the fleet RustRover has `-Xmx3072m`, and the other IDEs of
the fleet have `-Xmx2048m`.

| Item | Value |
|---|---|
| Switch at the first open: stop RustRover, mark the projects, start, all projects listed | 26 s |
| Ready after the switch, first open | 0 s, but the Cargo sync starts the indexing 15 s later |
| First indexing: 13,922 files, then 11,124 files of the crates and the standard library | 130 s from the start of the open to the last smart mode |
| Second open | switch 12 s, the last dumb pass ends 35 s after the switch |
| Rust fixture rows while `rolldown` is open | 109 passed (109 before the open) |
| Resident memory of RustRover, `rust` fixture plus `rolldown` | 3,577 MB 3 min after the start, 3,205 MB after a full collection |
| Used heap after a full collection | 421 MB |
| Checkout | 91 MB, and 950 MB of `target/` that the cargo check of the IDE writes |
| Crates of `Cargo.lock` in the registry | 353 crates, 397 MB |

The readiness check passes before the Cargo sync. So open the product with
`--open-product rolldown`, wait 2 minutes at a first open or 45 s at a later open, and then run
`--product rolldown`.

## Import check

Done on 2026-11-22 with plugin 2.1.1-dev.23.

| Call | Result |
|---|---|
| `ide_find_class`, query `LinkStage` | the struct, `crates/rolldown/src/stages/link_stage/mod.rs:89` |
| `ide_find_definition`, `crates/rolldown/src/module_loader/resolve_utils.rs:3:12` | the struct `ArcStr` of arcstr 1.2.0 |
| `ide_find_usages` of `ModuleIdx` | 500 usages collected, more pages |
| `ide_type_hierarchy` of the trait `Plugin` | 57 subtypes |
| `ide_file_structure`, `crates/rolldown_plugin/src/plugin.rs` | 61 lines in 0.8 s |

Comparison with RustRover itself. A second RustRover with a window opened a copy of the pin
with no `.idea` folder:

- Its project model is the model of the bootstrap: the same module file and the root
  `Cargo.toml` attached.
- Go to Declaration at `resolve_utils.rs:3:12` opens `ArcStr` in arcstr. The tool gives the same.
- The Code Vision hint of the trait `Plugin` says 57 implementations. The tool gives 57.
- Type Hierarchy of the TypeScript class `PlainObjectLike`: 5 subclasses. The tool gives the same.
- Choose Implementation of the struct `LinkStage`: 15 `impl` blocks. The tool gives the same.

Project model facts that the probe rows rely on:

- The test data below `crates/*/tests` and `packages/*/tests` is in the project, and the
  `tests` folders of the crates are test folders. The `node_modules` folders of the test data
  are not in the project scope: Go to File finds none of their files.
- The TypeScript sources below `packages/` are in no source folder. So a production or test
  scope finds no TypeScript file: Call Hierarchy of `unwrapBindingResult` with the scope
  Production shows no caller, and the tool gives 0.
- RustRover offers `pnpm install` and does not run it. No row needs a JavaScript package.
