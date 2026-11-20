# Captured ground truth: Rust fixture

These results of the Rust fixture look wrong, but the IDE returns the same. Do not change
a probe to "fix" one. The notes that cover more than one language are in
[../GROUND-TRUTH.md](../GROUND-TRUTH.md).

- **Rust `qualifiedName` comes from RustRover's `RsQualifiedNameProvider`**
  (2026.2+): crate-qualified module paths (`live_test_rust::normal::Circle`),
  trait-impl members as `<live_test_rust::normal::Circle as
  live_test_rust::normal::Shape>::area`, std items as `core::…` / `alloc::…`.
  On 2026.1 the provider returned nothing for these elements, so
  `QualifiedNameUtil.rustFallback` emitted `crate::<name>` (the pre-#95
  snapshots). It is still `null` where neither computes an FQN (13 values in 5
  rows, e.g. `impls-Shape-trait`). The `name` field is unaffected.
- **Rust `impls-generic-bound-Coercer`** (anchored on `Coercer` in the `<C: Coercer>`
  bound): resolves to the trait's implementations — `impl Coercer for IntCoercer`,
  `impl Coercer for LenCoercer` (`totalCount: 2`).
- **Rust `find_usages` searches the base declaration too (#172).** The window
  observations of RustRover 2026.2.0.1 on 2026-11-17, anchor `Circle::area`
  (`src/normal.rs:27:8`): the IDE asks "Do you want to find usages of the base
  declaration?". Yes searches 5 functions: the anchor, the `area` of the other impls
  of `Shape` in `normal.rs` and in `tests/scope_probe.rs`, and the trait item. Yes
  lists 8 usages: `normal.rs` lines 16, 32, 53, 77, 97 and 102 (two usages), and
  `tests/scope_probe.rs:21`. No lists 1 usage (line 32). Rows `usage-Circle.area-impl`
  and `usage-area-libraries-scope` give the same 8 usages: 32:45 has no `match`, and
  the other 7 have `BASE`. The `notes` entry names `Shape::area`
  (`src/normal.rs:13:8`). The tool searches the anchor and the trait item. The search
  of the trait item also returns the calls on the other impls (53:48, 77:20,
  `scope_probe.rs:21:26`), so these usages have `BASE` too.
- **Rust `impls-Glazed-via-macro` lists a macro implementation at its macro call.** RustRover
  keeps the expansion of `glazed_impl!(Tile)` in a file of its own, which no search scope
  holds. The navigation element of the implementation in that file is the macro call
  (`RsNavigationElementProviderServiceImpl`, read from the bytecode). So the rows of `Tile`
  and `Brick` are at lines 24 and 25, column 1, and their names come from the expansion
  (`impl Glazed for Tile`). The row of `Slate` is at its hand-written `impl`.
- **Rust `super-Inherent.foo-inherent`**: empty hierarchy — *correct*. An
  inherent `impl` method (no trait) has no super. Don't be misled by RustRover's
  raw Ctrl+U "Go to Super", which jumps to the enclosing `pub mod` declaration
  (module-super noise); `RustSuperMethodsProvider` filters `gotoSuperTargets` to
  `RsAbstractable` (see its source) and so returns empty, mirroring the gutter
  "I↑" marker (absent on inherent methods), not raw Ctrl+U. Unlike Go's negative
  case (#25), Rust returns the correct empty hierarchy here, not an error.
