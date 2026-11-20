# Captured ground truth: TypeScript fixture

- **TypeScript `impls-` via object literal**: classes/objects satisfying an
  interface structurally (no `implements` clause) are not surfaced.
- **TS `super-ConstChild.KIND-const`**: a `static readonly` field anchor returns
  its overridden field (`ConstBase.KIND`, `kind: READONLY_FIELD`), mirroring the
  IDE's overriding-gutter / Ctrl+U and matching PHP/Rust/Kotlin const/property
  supers. Resolved in #24 (was previously a `tool_error` from the method-only
  gate). (TS *static methods* also resolve — see `super-Child.factory-static` →
  `StaticBase.factory`.)
