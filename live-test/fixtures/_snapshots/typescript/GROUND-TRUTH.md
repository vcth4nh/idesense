# Captured ground truth: TypeScript fixture

These results of the TypeScript fixture look wrong, but the IDE returns the same. Do not change
a probe to "fix" one. The notes that cover more than one language are in
[../GROUND-TRUTH.md](../GROUND-TRUTH.md).

- **TypeScript `impls-` via object literal**: classes/objects satisfying an
  interface structurally (no `implements` clause) are not surfaced.
- **TS `super-ConstChild.KIND-const`**: a `static readonly` field anchor returns
  its overridden field (`ConstBase.KIND`, `kind: READONLY_FIELD`), mirroring the
  IDE's overriding-gutter / Ctrl+U and matching PHP/Rust/Kotlin const/property
  supers. Resolved in #24 (was previously a `tool_error` from the method-only
  gate). (TS *static methods* also resolve — see `super-Child.factory-static` →
  `StaticBase.factory`.)
