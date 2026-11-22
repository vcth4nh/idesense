# Captured ground truth: ruff

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **ruff: 31 types `Settings`, where Go to Class shows 32 rows.**
  `find-class-Settings-rust-and-ts` gives 31 types: 30 Rust structs and the TypeScript type alias
  of `playground/ruff/src/Editor/settings.ts`. Go to Class of RustRover with the name `Settings`
  and the scope Project Files shows 32 rows with the exact name. The extra row is in a file of the
  macro expansions: the expansion of `#[salsa::input(debug)]` on the struct of
  `crates/ty_test/src/db.rs:238`. Enter on that row opens `db.rs:238:8`, the same struct as the
  row of `db.rs`. So the popup has 31 targets, as the tool.
- **ruff: the 983 implementations of `ViolationMetadata` point to `#[derive]` lines.**
  `canary-impls-ViolationMetadata-derive-paged` gives 983 implementations, and each item is the
  name in a `#[derive(ViolationMetadata)]` line, not an `impl` block. The derive macro of
  `ruff_macros` writes each `impl`. The popup "Choose Implementation of ViolationMetadata" says
  "983 found" and lists files of the macro expansions. Enter on a row opens the derive line, for
  example `abstract_base_class.rs:56:10`, the position of the tool item. The Code Vision hint on
  the trait says 983 implementations. The source has 984 texts `derive(ViolationMetadata)`: one is
  in a doc comment (`crates/ruff/src/commands/rule.rs:139`). So 983 is complete.
- **ruff: 753 implementations of `Violation`, where 983 rules exist.**
  `impls-Violation-trait-page1` and `-page2` give 753 items: 752 `impl Violation` blocks and the
  blanket `impl<V: AlwaysFixableViolation> Violation for V` as one item. The 231 types that
  implement `AlwaysFixableViolation` do not show one by one. The Code Vision hint on the trait
  says 753 implementations.
- **ruff: 16 symbols `quote_style`, where Go to Symbol shows 35 rows.**
  `find-symbol-quote_style-collision` gives 16 symbols: 12 functions and methods and 4 fields.
  Go to Symbol of RustRover with the scope Project Files shows 35 rows: the first 16 have the
  exact name and are the same 16 declarations, and 19 rows have a longer name. The tool matches
  the exact name by default (`docs/ARCHITECTURE.md`). The other places of the name in the source
  are a parameter (`crates/ty_ide/src/completion.rs:2308`) and field initializers, and Go to
  Symbol lists none of them.
- **ruff: parked rows.** Each of these rows shows an open defect (see "Parked rows" in
  `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `find-class-Rule-macro` | #188 | the enum `Rule`, which the attribute macro `#[ruff_macros::map_codes]` makes, is absent; Go to Class of RustRover lists it and opens `codes.rs:95:3` |
  | `def-Rule-attribute-macro`, `def-Rule.UnusedImport-proc-macro` | #188 | the positions are correct (`codes.rs:95:3`, `codes.rs:175:54`), but the `kind` is `SYMBOL`, and for the enum `Rule` the `name` and the `qualifiedName` are `ruff_macros::map_codes`, the path of the attribute |
  | `explain-Settings-ambiguous`, `usage-Settings-bysymbol` | #269 | the name `Settings`, which 30 Rust structs and one TypeScript type alias share, resolves to the type alias with no `candidates` |
  | `find-file-codes.rs`, `find-file-builtins.pyi-vendored` | #271 | Go to File also gives the files that match through the directory path (`pycodestyle`, `flake8_builtins`): at least 20 rows for `codes.rs` and 9 for `builtins.pyi`, against 7 and 8 |

  `explain-Settings-ambiguous` also shows #274: the first call for the type alias in an IDE
  session gives the `signature` `export type Settings`, and each later call gives
  `type Settings = {`. A row has one park number, so the row has #269.
