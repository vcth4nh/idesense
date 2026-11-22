# Captured ground truth: rolldown

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **rolldown: 57 implementations of the trait `Plugin`, where a popup says 53.**
  `impls-Plugin-trait` gives 57 `impl` blocks. The Code Vision hint of RustRover on the trait
  says "57 implementations". The popup "Choose Implementation of Plugin" says "53 found": it
  shows one row for each text of the form "name (in file name[line])". The 57 blocks have 53
  different texts. Three texts come from more than one block, each in test files named `mod.rs`
  at the same line: `TestPlugin` (2 blocks, line 10), `Test` (2 blocks, line 11) and
  `EmitChunkPlugin` (3 blocks, line 17). The popup shows one row
  `EmitChunkPlugin (in mod.rs[16])` for the 3 blocks.
- **rolldown: parked rows.** Each of these rows shows an open defect (see "Parked rows" in
  `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `explain-Plugin-ambiguous`, `usage-Chunk-bysymbol` | #269 | a name that a Rust item and a TypeScript declaration share resolves to the TypeScript declaration with no `candidates` (`Plugin`: an interface and a trait; `Chunk`: a type alias and 3 structs) |
  | `explain-Plugin-rust-qualified-name` | #273 | the printed `qualifiedName` of the trait, `rolldown_plugin::plugin::Plugin`, gives "Ambiguous symbol" with 2 candidates |
  | `find-class-ModuleIdx-macro` | #188 | the struct `ModuleIdx` of `oxc_index::define_index_type!` is absent; Go to Class of RustRover lists it and opens `module_idx.rs:3:16` |
  | `def-ModuleIdx-via-reexport-macro`, `def-HookUsage-generated`, `def-HookUsage.Transform-bitflags` | #188 | the position is correct, but an item that a macro call makes gets the `kind` `SYMBOL`; the Structure tool window shows `HookUsage` as a struct |
  | `file-structure-hook_usage.rs-generated` | #190 | the default outline says "File is empty or has no parseable structure."; the Structure tool window and the File Structure popup show `HookUsage` and `null: ()` |

  `explain-Plugin-ambiguous` also shows #274: the first call in an IDE session gives the
  `signature` `export interface Plugin<A> extends OutputPlugin, Partial`, and each later call
  gives `interface Plugin<A = any>`. A row has one park number, so the row has #269.
