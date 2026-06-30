# live-test conventions

Working notes for the snapshot harness. See `README.md` for user-facing docs.

## Snapshot file format

Both `input.jsonl` and `expected.jsonl` are id-keyed JSONL.

- **input row**: `{"id": "<unique-id>", "tool": "ide_X", "params": {...}}` — one per line.
- **expected row**: `{"id": "<input-id>", "result": <normalized-output>}` — one per line.
- **output row** (produced by `run.py`): same shape as expected.

Rows are matched by `id`, not position. Reordering, inserting, or deleting
rows in `input.jsonl` does not shift the rest of the snapshot. The strict
loader in `run.py` (`_load_expected_by_id`) fails on malformed JSON, missing
`id`/`result`, non-string ids, or duplicate ids.

## ID convention

Format: `<tool-prefix>-<entity>[-<context>][-<variant>]`

All lowercase except entity, which preserves source-language casing (PascalCase
classes, camelCase methods, snake_case Python identifiers, UPPER enum constants).

### Tool prefixes

| Prefix | MCP tool | Notes |
|---|---|---|
| `def-` | `ide_find_definition` | |
| `usage-` | `ide_find_usages` | (not `refs-`) |
| `impls-` | `ide_find_implementations` | |
| `super-` | `ide_find_super_methods` | |
| `hier-caller-` | `ide_call_hierarchy` direction=callers | |
| `hier-callee-` | `ide_call_hierarchy` direction=callees | |
| `hier-super-` | `ide_type_hierarchy` direction=supertypes | |
| `hier-sub-` | `ide_type_hierarchy` direction=subtypes | |
| `hier-type-` | `ide_type_hierarchy` (default direction) | |
| `find-class-` | `ide_find_class` | |
| `find-symbol-` | `ide_find_symbol` | |
| `find-file-` | `ide_find_file` | |
| `file-structure-` | `ide_file_structure` | |
| `diagnostics-` | `ide_diagnostics` | |
| `status-` | `ide_index_status` | |

### Entity

The thing being probed. Use the source-language identifier verbatim.

- Class names: PascalCase (`Circle`, `ShapeCollection`, `IntCoercer`).
- Methods/fields: language-native casing (`area`, `totalArea`, `make_default_shapes`).
- Member access: dot (`Circle.area`, `CoerceMode.INT.apply`, `Status.Active`).
- Enum constants: UPPER (Java) or PascalCase (PHP enums) as the source uses.
- Multi-segment Go/Rust paths: dot (`baseShape.Describe`).

### Variants (lowercase suffix)

Append to disambiguate parameter shapes or behaviors of the same probe:

- direction: `-callers`, `-callees`, `-supertypes`, `-subtypes` — embedded in
  the hier-* prefix, never as a suffix.
- depth: `-d1`, `-d2`, `-d3`.
- fuzzySearch: `-fuzzy` (fuzzySearch:true). Exact is the default — omit the suffix, or use `-exact` to be explicit.
- scope: `-libraries-scope`, `-files-scope`.
- pagination: `-paged`, `-page1`, `-page2`.
- query shape: `-qualified` (e.g. `find-symbol-Shape.area-qualified`).
- result shape: `-no-match`, `-empty`, `-direct-overrides-only`.
- diagnostics severity: `-errors`, `-warnings`, `-info`, `-all`.
- context: `-cross-file`, `-decl`, `-call`, `-ctor`, `-promoted`, `-from-<x>`, `-via-<x>`.

Kind descriptors that follow a class but are NOT member access: keep the
hyphen, don't dot. E.g. `usage-Drawable-trait`, `impls-Shape-struct`,
`def-Status-enum-decl`.

### Anti-examples (don't do this)

- ❌ `audit-find-symbol-area-paged` — drop the `audit-` prefix (legacy from layered audits)
- ❌ `refs-Circle-ctor` — use `usage-`
- ❌ `call-hier-area-callers` — direction goes in the prefix: `hier-caller-area`
- ❌ `type-hier-Shape-supertypes` — `hier-super-Shape`
- ❌ `find-class-SC-Fuzzy` — lowercase variant: `find-class-SC-fuzzy`
- ❌ `find-symbol-qualified-Shape-area` — variant at end: `find-symbol-Shape.area-qualified`
- ❌ `def-circle-area-decl` — preserve class casing: `def-Circle.area-decl`
- ❌ `super-Circle-draw` — dot member access: `super-Circle.draw`

## Bless safety

`./run.py --bless` is gated. By default it refuses to:

1. Bless rows whose result is `tool_error_text` / `transport_error` /
   `jsonrpc_error`. Override with `--bless-errors` (rare; usually fix the
   probe first).
2. Drop orphan expected ids (ids in `expected.jsonl` no longer in
   `input.jsonl`). Override with `--prune`.
3. Run with `--tool` filter matching zero rows.

Writes are atomic (temp file + `os.replace`) — SIGINT-safe but not concurrency-
safe. Don't run parallel `--bless` against the same language.

**Never bless without explicit user permission** — re-blessing locks in
whatever the live IDE returns as truth. If the IDE has a regression, that
regression becomes the new baseline.

## Path normalization — project vs library

`normalize()` in `run.py` keeps snapshots stable across machines, IDE installs,
and toolchain versions by classifying every file ref (`_is_library`):

- **Project files** — the plugin returns these relative to the project root
  (`src/normal.py`). Kept as-is, with `line`/`column`: we control these files,
  so their positions only move when we edit a fixture.
- **Library / SDK files** — the plugin returns these as absolute paths
  (`/usr/lib/python3.12/abc.py`). Reduced to **basename + symbol identity**
  (`name`, `qualifiedName`, `kind`); `line`/`column` are dropped. The directory
  is machine-specific and the line/column track the IDE's decompiler — neither
  signals a plugin regression. So a hit at
  `…/mise/installs/go/1.26.1/src/fmt/print.go:64` snapshots as just `print.go`
  with its `fmt.Stringer.String` qualifiedName.

Absoluteness is the signal because the plugin already emits project files
relative and library files absolute. We key off the **project root** (which we
are handed), never off library install locations — so a new host, install
manager, SDK version, or renamed checkout needs **zero** maintenance, and a
toolchain bump no longer drifts the snapshot or forces a re-bless. There is no
`LIBRARY_PATH_SUBS` list to extend. `enclosingScope` is kept — it is usually the
enclosing method/class scope (a relative name chain like `['ShapeCollection',
'Add']`), which is real signal; only its absolute-*directory* form (a FILE
node's folder, `['/','home',…,'src']`) is dropped as machine-specific and
redundant with `file`.

## Fixture-edit safety

- `./run.py --check-fixtures` runs offline validation (no IDE calls):
  - input ids are unique non-empty strings
  - expected.jsonl parses strictly
  - no orphan or missing expected ids
  - each `file+line+column` probe targets an existing file, a line within
    bounds, and a non-whitespace character.
- Run it before any branch with fixture edits — line-shift bugs surface
  here instead of as silent IDE empty responses during a live run.
- When inserting lines into a fixture, every position-based probe with a
  `line` >= insertion point shifts. `--check-fixtures` catches the
  end-of-file case but not the wrong-token case.

## Workflow for adding new probes

1. Pick an `id` following the convention above.
2. Add the row to `<lang>/input.jsonl`.
3. `./run.py --check-fixtures` — verify the new probe is offline-valid.
4. `./run.py --language <lang>` — see the new row reported as MISSING.
5. Inspect the IDE response in `<lang>/output.jsonl` for that id. Confirm
   it looks like the truth you expected.
6. Ask the user to bless.
7. On approval: `./run.py --bless --language <lang>`. The new row's
   expected entry is added; pre-existing expected rows are preserved.

## When fixtures change

- Adding a fixture file (e.g. a new `.java`): no impact on existing probes
  unless the file appears in some find_class / find_symbol / file_structure
  result. Re-bless those.
- Editing a fixture file (insert/delete lines): every position-based probe
  in that file at or after the edit point breaks. Re-run probes; either
  re-bless if the new behavior is correct, or update the probe's `line`/
  `column` to point at the original target.
- Renaming a class: every ID referencing that name in the suite should
  also be renamed. Use the rename script pattern from `/tmp/rename_ids.py`
  (preserves alignment in input.jsonl).

## Captured ground truth (don't re-bless these as "fixes")

Some snapshot rows encode platform quirks intentionally. When you see a
"weird" expected result that looks like a bug, check this list first — the
IDE legitimately returns that output, and changing the probe to "fix" it
will just snapshot a different empty/odd result.

- **`hier-callee-makeDefault` constructor callees split by language.** **Kotlin & PHP**
  return empty callees — constructor invocations inside a method body don't surface as
  call-hierarchy callees there. **Java & TypeScript** are non-empty: Java surfaces the
  `Circle`/`Rectangle`/`Square` constructors as `CONSTRUCTOR` callees, and WebStorm
  surfaces them (in TS) as `CLASS` callees — so both the Java and TS
  `hier-callee-makeDefault` snapshots are non-empty.
- **Java `find-symbol` for overridden methods**: collapses to the topmost
  super; concrete overrides on subclasses are not separately surfaced.
- **PHP `hier-callee-makeDefault`**: empty callees — constructor invocations don't
  surface (same as Kotlin; unlike Java/TS).
- **Python `impls-Drawable.draw`**: returns empty. `Drawable` is a
  `typing.Protocol`, so PyCharm has no nominal implementer set to enumerate
  (`usage-Drawable-protocol` is likewise empty).
- **Python `find-definition` on builtins inside lambda / dict bodies**: some
  positions can return `tool_error_text: No named element at position` — but the
  suite currently has no probe capturing this, so it's an observation, not a blessed row.
- **TypeScript `impls-` via object literal**: classes/objects satisfying an
  interface structurally (no `implements` clause) are not surfaced.
- **JS `hier-type-Probe-sub-*` subtypes omit a cross-file child that `extends` a
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
- **Go `hier-type-*` resolves structural interfaces**: a struct (`Circle`,
  `Rectangle`, `Square`) lists the interfaces it implicitly satisfies as
  `supertypes` (`Drawable`, `Shape`), and an interface (`Drawable`, `Shape`)
  lists its implementers as `subtypes` — even though Go has no explicit
  `implements`. Types with neither (`baseShape`, `ShapeCollection`) return
  empty, as expected.
- **Enum type hierarchy — `direction:both` returns the *supertypes* view, which the IDE's
  combined Type Hierarchy widget hides.** `hier-type-Direction` (TS numeric enum) blesses
  `supertypes: [Number ×3]`; `hier-type-Severity-enum` (PHP string-backed enum) blesses
  `supertypes: [BackedEnum → UnitEnum, Labeled]`. Verified in WebStorm/PhpStorm: the
  **Supertypes** view shows exactly these, but the default combined ("both") widget shows
  *nothing* for the enum — a rendering quirk of that view, not a tool error. Don't re-bless
  these to empty. (Whether `direction:both` should mirror the combined widget vs. the
  supertypes∪subtypes union is a separate open question — see the type_hierarchy follow-up.)
- **Go `qualifiedName` uses `package.Type.Method`** (e.g. `main.Circle.Area`,
  `main.Drawable.Draw`): GoLand registers no `QualifiedNameProvider` for Go, so
  `QualifiedNameUtil.goFallback` builds the FQN by reflection (`package.Function` /
  `package.Receiver.Method` / `package.Interface.method`). Nearly all Go elements
  resolve; a few positions still return `null`.
- **Rust `qualifiedName` partially `null`**: when the Rust provider can't
  compute an FQN. The `name` field is unaffected.
- **Rust `impls-generic-bound-Coercer`** (anchored on `Coercer` in the `<C: Coercer>`
  bound): resolves to the trait's implementations — `impl Coercer for IntCoercer`,
  `impl Coercer for LenCoercer` (`totalCount: 2`).
- **Kotlin `hier-callee-makeDefault`**: empty callees — `Circle(...)`,
  `Rectangle(...)`, `Square(...)` constructor invocations don't appear
  (same as PHP; unlike Java/TS).
- **Kotlin `qualifiedName` uses `#` for methods** (e.g. `demo.Shape#area`):
  correct — matches IntelliJ's "Copy Reference" format and is consistent
  with Java.
- **Library/SDK targets show as a bare basename**: a hit resolving into a
  JDK / stdlib / stub file (`java.lang.Object`, JS `Number.parseInt`, Python
  `int`, …) is reduced to basename + symbol identity, with no directory and no
  line/column — so it reads as `Object.class` / `lib.es5.d.ts` / `builtins.pyi`,
  not a path. By design (see "Path normalization — project vs library"); a
  toolchain or IDE bump no longer drifts these rows, so it is not a re-bless
  trigger.
- **Java `super-LambdaHost-lambda.run-sam`**: returns the lambda's SAM as the
  `method` (`java.lang.Runnable#run`, empty `hierarchy`). Caret is on a lambda's
  `->`; the provider resolves the functional interface's single abstract method
  via `LambdaUtil.getFunctionalInterfaceMethod`, mirroring Ctrl+U. Resolved in
  #22 (was previously a `tool_error`).
- **JS/TS return the full transitive super chain**: e.g.
  `super-LeafMix.greet-3level` (JS) and `super-DeepLeaf.m`/`super-DeepMid2.m` (TS)
  return every transitive super, matching the Java/Kotlin/Python analogs and
  WebStorm's overriding-gutter. The provider recurses on
  `JSInheritanceUtil.findNearestOverriddenMembers` to a fixpoint. Resolved in
  #23 (was previously immediate-parent only).
- **JS `super-WithMixin.shout-mixin`**: empty hierarchy. `WithMixin` extends
  a dynamically-constructed mixin class (`Amplifier(Plain)`); the IDE cannot
  statically resolve the super — confirmed the gutter shows nothing either.
  This is expected ground truth (not a tool gap), unlike the immediate-only
  case above.
- **TS `super-ConstChild.KIND-const`**: a `static readonly` field anchor returns
  its overridden field (`ConstBase.KIND`, `kind: READONLY_FIELD`), mirroring the
  IDE's overriding-gutter / Ctrl+U and matching PHP/Rust/Kotlin const/property
  supers. Resolved in #24 (was previously a `tool_error` from the method-only
  gate). (TS *static methods* also resolve — see `super-Child.factory-static` →
  `StaticBase.factory`.)
- **Go `super-Standalone.Compute-negative`**: a method satisfying no interface
  returns an empty `hierarchy` (method found, no super), matching
  Java/Python/Kotlin. Verified in GoLand: no gutter icon, Ctrl+U no-ops.
  Resolved in #25 (was previously a misleading `tool_error`).
- **Go `file_structure` is package-scoped**: `file-structure-Normal` /
  `file-structure-Quirks` list *every* type in package `main` (each tagged
  with its origin file), not just the queried file's. Adding any `.go` fixture
  to the package changes these snapshots — re-bless them when you add Go
  fixtures (this is why they drift after `multisuper.go` / `*_super.go` land).
- **Go `find_usages` on a type counts the method receiver as a usage**:
  `usage-baseShape-embed` (find_usages of the `baseShape` struct) returns 11
  usages — the three embed sites (`Labeled` embed.go:6, `Circle` normal.go:19,
  `Rectangle` normal.go:30), the receiver declaration
  `func (b baseShape) Describe()` at normal.go:16, **plus 7 more in `normal_test.go`**. The receiver names the type,
  so GoLand counts it as a reference. Verified in GoLand (Find Usages lists the
  receiver). Not a tool artifact.
- **Rust `super-Inherent.foo-inherent`**: empty hierarchy — *correct*. An
  inherent `impl` method (no trait) has no super. Don't be misled by RustRover's
  raw Ctrl+U "Go to Super", which jumps to the enclosing `pub mod` declaration
  (module-super noise); `RustSuperMethodsProvider` filters `gotoSuperTargets` to
  `RsAbstractable` (see its source) and so returns empty, mirroring the gutter
  "I↑" marker (absent on inherent methods), not raw Ctrl+U. Unlike Go's negative
  case (#25), Rust returns the correct empty hierarchy here, not an error.
