# Captured ground truth: JavaScript fixture

- **JS `hier-sub-Probe-*` subtypes omit a cross-file child that `extends` a
  `require()`-imported base.** `ProbeTestChild` (in `test/probe.test.js`,
  `class ProbeTestChild extends Probe` with `Probe` `require()`-imported from
  `src/probes.js`) does NOT appear under Subtypes of `Probe`; only the same-file
  `ProbeProdChild` does — so JS blesses 1 subtype vs 2 for Python/PHP/TS. The `extends`
  edge itself *resolves* (Supertypes of `ProbeTestChild` correctly shows `Probe`), but
  WebStorm's stub-based **inheritors index** (the Subtypes direction) never captures the
  CommonJS cross-file edge — confirmed even with Node.js coding-assistance enabled (so
  `require` resolves) and after a forced reindex/re-stub. Verified against WebStorm's own
  Type Hierarchy widget. The type-hier scope no-op still holds (all/production/test
  identical at 1).
- **JS `super-WithMixin.shout-mixin`**: empty hierarchy. `WithMixin` extends
  a dynamically-constructed mixin class (`Amplifier(Plain)`); the IDE cannot
  statically resolve the super — confirmed the gutter shows nothing either.
  This is expected ground truth (not a tool gap), unlike the immediate-only
  case above.
