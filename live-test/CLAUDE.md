# live-test conventions

Working notes for the snapshot harness. See `README.md` for user-facing docs.

## Snapshot file format

Snapshots are split per tool and live under `live-test/_snapshots/<lang>/`:

```
live-test/_snapshots/<lang>/
  inputs/<tool>.jsonl      # e.g. inputs/ide_find_usages.jsonl — rows sorted by id
  expected/<tool>.jsonl    # mirrors its input file 1:1, same order (bless-written)
  output.jsonl             # per-language run artifact (gitignored)
live-test/<lang>/          # fixture SOURCES only — the IDE-indexed project
```

- **input row**: `{"id":…,"tool":"ide_X","params":{…}}` — canonical compact
  serialization (params keys recursively sorted, no spaces), e.g.
  `{"id":"find-class-Circle","tool":"ide_find_class","params":{"query":"Circle"}}`
- **expected row**: `{"id": "<input-id>", "result": <normalized-output>}` — one per line.
- **output row** (produced by `run.py`): same shape as expected.

Rules, all enforced by `--check-fixtures`:
- `tool` field must equal the filename stem (`inputs/ide_find_class.jsonl`
  holds only `"tool":"ide_find_class"` rows).
- Ids unique globally per language (across all tool files).
- Rows id-sorted within each file; bless mirrors input-file order, so
  expected files are id-sorted too. New rows insert at their sorted position.
- Every input line must byte-equal its canonical serialization
  (`serialize_input_row` in `run.py`).

Rows are matched by `id`, not position — reordering/inserting/deleting never
shifts the rest of the snapshot. The strict loaders (`_load_inputs`,
`_load_expected`) fail on malformed JSON, missing/duplicate ids, or
tool≠filename.

Snapshots sit **outside** the fixture project roots on purpose: their text
mentions every fixture symbol, and once a symbol's name occurs in >10 files
of the project IntelliJ's unused-symbol inspection silently gives up
(`PsiSearchHelperImpl.isCheapEnoughToSearch` → `TOO_MANY_OCCURRENCES`),
which flips "Class 'X' is never used" warnings out of diagnostics
snapshots. Never move harness artifacts into `live-test/<lang>/`.

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
- scope: `-libraries-scope`, `-files-scope`, `-production-scope`, `-test-scope`,
  `-class-scope` (hierarchy scope:"this_class").
- explicit type-hierarchy direction "both": `-both` (default-direction rows omit it).
- language filter: `-lang-<language>` (e.g. `-lang-java`, `-lang-kotlin-empty`).
- pagination: `-paged`, `-page1`, `-page2`.
- query shape: `-qualified` (e.g. `find-symbol-Shape.area-qualified`).
- result shape: `-no-match`, `-empty`, `-direct-overrides-only`.
- diagnostics severity: `-errors`, `-warnings`, `-info`, `-all`.
- context: `-cross-file`, `-decl`, `-call`, `-ctor`, `-promoted`, `-from-<x>`, `-via-<x>`.

Kind descriptors that follow a class but are NOT member access: keep the
hyphen, don't dot. E.g. `usage-Drawable-trait`, `impls-Shape-struct`,
`def-Status-enum-decl`.

## Fixture taxonomy

What each source file hosts, per language. Files are named after the campaign
that added them — do not rename or move; anchors and expected paths depend on
them. Fixture edits are append-only at EOF or brand-new files (see
Fixture-edit safety), and check the file's `file_structure`/`diagnostics`
pins first — appending to a pinned file drifts its blessed row.

| Language | File | Hosts |
|---|---|---|
| java | Normal.java | Shape/Circle/Rectangle/Square hierarchy, Drawable, ShapeCollection, Normal |
| java | Quirks.java | Quirks (overloads incl. parse ×2, dispatch), Coercer, CoerceMode enum, Coerce interface |
| java | Modern.java | record Point, sealed Animal + Cat/Dog |
| java | MultiSuper.java | diamond/chain interfaces (DiamondTop…), Named/Tagged/Identified + record LabelPoint, sealed shapes, Op enum |
| java | Probes.java | Probe/ProbeAux/ProbeProdChild (scope fixtures) |
| java | GenericSuper.java, LambdaSuper.java, StaticSuper.java, NegativeSuper.java | super-methods campaign fixtures (BaseRepo/Repo, LambdaHost, StaticBase/Derived, Standalone) |
| java | Broken.java | deliberate compile errors (ERROR-diagnostics probe; this pass) |
| java | Extras.java | Plain (toString override → library super; this pass) |
| kotlin | Normal.kt | Shape hierarchy, Drawable, ShapeCollection |
| kotlin | Quirks.kt | Coercer/Coercion/AbsCoerce/IntCoerce, quirk* dispatch fns (incl. quirkDispatchMap) |
| kotlin | Modern.kt | Counter (+ this pass: Printer delegation trio, Channel enum, Plain toString) |
| kotlin | MultiSuper.kt, GenericSuper.kt, CompanionSuper.kt, AsyncSuper.kt, OperatorSuper.kt, SetterSuper.kt, NegativeSuper.kt | super-methods campaign fixtures |
| kotlin | Probes.kt | Probe/ProbeProdChild (scope fixtures) |
| javascript | src/normal.js | Shape hierarchy, Drawable, ShapeCollection, makeDefaultShapes |
| javascript | src/quirks.js | q* dispatch functions (qBind/qCond/qComputed/…) |
| javascript | src/probes.js | Probe, freeProdCaller, ProbeProdChild |
| javascript | test/probe.test.js | ProbeTest, ProbeTestChild (cross-file CommonJS extends) |
| javascript | src/setter_super.js | Base/Derived accessors (+ this pass: writeProbe WRITE-usage site) |
| javascript | src/accessors.js, mixin_super.js, multisuper.js, triple_super.js, async_super.js, static_super…, negative_super.js, consumer.js | super-methods/mixin campaign fixtures |
| typescript | src/normal.ts | Shape hierarchy, Drawable, ShapeCollection |
| typescript | src/multisuper.ts | diamond (DiamondTop/DiamondBottom), AbstractCombo/ConcreteCombo (readonly p), accessor/static supers |
| typescript | src/quirks.ts | q* dispatch, TypedCoercer |
| typescript | src/enums.ts, namespaces.ts, decorators.ts | Color/Direction enums, Geometry namespace, Service + traced decorator |
| typescript | src/decorators_caller.ts | useService — cross-file caller of decorated method (this pass) |
| typescript | src/probes.ts, test/probe.test.ts | scope fixtures |
| typescript | src/setter_super.ts, const_super.ts, generic_super.ts, static_super.ts, async_super.ts, negative_super.ts | super-methods campaign fixtures |
| php | src/Normal.php | Shape hierarchy, ShapeCollection, area/add |
| php | src/Quirks.php | Quirks static dispatch (qMatch/…), IntCoercer/LenCoercer |
| php | src/Modern.php | Color/Status enums |
| php | src/MultiSuper.php, AbstractTraitSuper.php, EnumSuper.php, ConstructorSuper.php, StaticSuper.php, NegativeSuper.php | super-methods campaign fixtures (traits, backed enums, ctor supers) |
| php | src/Probes.php, tests/ProbeTest.php | scope fixtures |
| php | src/Php8.php | Php8/Php8Helper: nullsafe `?->`, first-class callable, const+property (this pass) |
| go | normal.go (+normal_test.go) | Shape/Drawable interfaces, baseShape, Circle/Rectangle/Square, MakeDefaultShapes |
| go | quirks.go | q* dispatch fns, IntCoercer, CoerceLimit iota consts |
| go | embed.go | Labeled embed (cross-file baseShape embed + promoted method) |
| go | multisuper.go, generic_super.go, negative_super.go, wedge_test.go | interface-satisfaction fixtures (IFull/ChainImpl, IBase/IMid/ILeaf embedding chain, Storage[T]/IntStore, Standalone, wedge) |
| rust | src/normal.rs | Shape trait hierarchy, ShapeCollection, area/largest |
| rust | src/quirks.rs | q* dispatch fns, CoerceMode enum, parse_or_zero (fn-pointer) |
| rust | src/macros.rs | square! macro_rules, derive Point |
| rust | src/supertrait_super.rs, generic_super.rs, default_super.rs, multisuper.rs, negative_super.rs, extra.rs | trait-super fixtures (Sub supertrait, Storage generic, Inherent, MyTrait family) |
| rust | src/scopes.rs, tests/scope_probe.rs | Probe/target scope fixtures, TestShape |
| python | src/normal.py | Shape hierarchy, Drawable protocol, ShapeCollection, make_default_shapes |
| python | src/quirks.py | quirk_* dispatch fns (incl. function-local Coercer) |
| python | src/multi_super.py | diamond MRO (DiamondBottom…), ConcreteShape, deep chains |
| python | src/dataclass_super.py | ParentDC/ChildDC `__post_init__` |
| python | src/probes.py, test/probes_test.py | Probe/target scope fixtures |
| python | src/async_super.py, generic_super.py, setter_super.py, negative_super.py | super-methods campaign fixtures |
| python | src/enums.py | Channel(Enum) + member access (this pass) |

### Anti-examples (don't do this)

- ❌ `audit-find-symbol-area-paged` — drop the `audit-` prefix (legacy from layered audits)
- ❌ `refs-Circle-ctor` — use `usage-`
- ❌ `call-hier-area-callers` — direction goes in the prefix: `hier-caller-area`
- ❌ `type-hier-Shape-supertypes` — `hier-super-Shape`
- ❌ `find-class-SC-Fuzzy` — lowercase variant: `find-class-SC-fuzzy`
- ❌ `find-symbol-qualified-Shape-area` — variant at end: `find-symbol-Shape.area-qualified`
- ❌ `def-circle-area-decl` — preserve class casing: `def-Circle.area-decl`
- ❌ `super-Circle-draw` — dot member access: `super-Circle.draw`

## Fixture comment standard (how to read a fixture)

Every fixture source file carries comments that make it readable cold:

- **File header** (1–3 comment lines at top): what the file hosts and why it exists.
- **Per-construct block comments** in multi-family files (`MultiSuper.kt` style:
  "Diamond + abstract base: … -> Bottom").
- **Ground-truth notes** where a construct pins surprising IDE behavior (e.g.
  `writeProbe` in `setter_super.js` pins WebStorm reporting setter write-sites
  as REFERENCE, not WRITE).

The per-probe join lives in `_snapshots/<lang>/ANCHORS.md` (regenerate:
`./run.py --write-anchors`; `--check-fixtures` fails while stale). Comments
never enumerate probe ids — they explain intent; the map owns the inventory.

Hard rules (they keep the pinned snapshots stable):

- **Whole-line comments only** — never trailing/same-line; columns must not move.
- **Plain `//` only** (`#` in Python). Banned: JSDoc `/** */` (feeds WebStorm
  type inference), Python docstrings (become structure nodes), Rust `///`,
  phpdoc, `/* */` blocks.
- **Only name symbols declared in the same file** (10-file word-occurrence
  threshold — see "Snapshot file format"). In Go, prefer lowercase paraphrase
  over capitalized exported names: GoLand counts comment text occurrences as
  usages under the libraries scope.
- **Dictionary words only** in the diagnostics-pinned java files
  (`Broken.java`, `Quirks.java`, `Normal.java`) — a typo can spawn a
  spell-check inspection row.
- New fixture code ships **with** its header + construct comments. Inserting a
  comment into an already-pinned file shifts every anchor below it: re-anchor
  the affected input rows and re-bless (see "When fixtures change").

## Bless safety

`./run.py --bless` is gated. By default it refuses to:

1. Bless rows whose result is `tool_error_text` / `transport_error` /
   `jsonrpc_error`. Override with `--bless-errors` (rare; usually fix the
   probe first).
2. Bless rows whose fresh result is a structured `{"error": ...}` payload
   when the previously blessed result was **not** an error (or the row is
   new) — a degraded IDE must not silently poison snapshots. Rows already
   blessed as errors (intentional negative probes) stay re-blessable.
   Override with `--bless-errors` (e.g. when adding a new negative probe).
3. Drop orphan expected ids (ids in `expected/` no longer in any
   `inputs/<tool>.jsonl`). Override with `--prune`.
4. Run with `--tool` filter matching zero rows.

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
  - input ids are unique non-empty strings, globally per language
  - `tool` == filename stem, rows id-sorted, canonical serialization
  - expected/*.jsonl parse strictly, no cross-file duplicate ids
  - no orphan or missing expected ids
  - each `file+line+column` probe targets an existing file, a line within
    bounds, and a non-whitespace character
  - each committed `ANCHORS.md` byte-matches regeneration from current
    inputs + sources (stale map = failure; run `--write-anchors`).
- Run it before any branch with fixture edits — line-shift bugs surface
  here instead of as silent IDE empty responses during a live run.
- When inserting lines into a fixture, every position-based probe with a
  `line` >= insertion point shifts. `--check-fixtures` catches the
  end-of-file case but not the wrong-token case.

## Workflow for adding new probes

1. Pick an `id` following the convention above.
2. Add the row at its id-sorted position in
   `_snapshots/<lang>/inputs/<tool>.jsonl` (canonical compact serialization).
3. `./run.py --check-fixtures` — verify the new probe is offline-valid.
4. `./run.py --language <lang>` — see the new row reported as MISSING.
5. Inspect the IDE response in `_snapshots/<lang>/output.jsonl` for that id.
   Confirm it looks like the truth you expected.
6. Ask the user to bless.
7. On approval: `./run.py --bless --language <lang>`. The new row's
   expected entry is added; pre-existing expected rows are preserved.
8. New/edited fixture files follow the "Fixture comment standard" above, and
   ANCHORS.md must be regenerated after input changes (`./run.py
   --write-anchors`) — `--check-fixtures` enforces both freshness and anchors.

## When fixtures change

- Adding a fixture file (e.g. a new `.java`): no impact on existing probes
  unless the file appears in some find_class / find_symbol / file_structure
  result. Re-bless those.
- Editing a fixture file (insert/delete lines): every position-based probe
  in that file at or after the edit point breaks. Re-run probes; either
  re-bless if the new behavior is correct, or update the probe's `line`/
  `column` to point at the original target.
- Renaming a class: rename every ID referencing it in `inputs/` **and**
  `expected/` in lockstep (script it; ids are the join key), then run
  `--check-fixtures` and a full language run — results are unchanged so no
  re-bless.

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
- **Python `find-file-star-py` collapses to `src/__init__.py`** — known PyCharm-only
  defect (#87), pinned deliberately. Extension-only queries (`*.py`, `.py`, `py`) return
  a single file while any name part (`*_super.py`) or a trailing space (`*.py `) returns
  the full set; the platform matcher itself accepts all names, so the loss is in the
  contributor item phase (failures are debug-swallowed). When #87 is fixed this row
  diffs — re-bless it then.
- **`find_file` extension queries substring-match longer extensions**: `*.js` matches
  `package.json` (`.js` ⊂ `.json`) and `*.kt` matches `build.gradle.kts` / `settings.gradle.kts`.
  MinusculeMatcher fragments are not end-anchored without a trailing space; matcher-level
  behavior shared with the IDE popup, not a tool bug.
- **Rust `super-Inherent.foo-inherent`**: empty hierarchy — *correct*. An
  inherent `impl` method (no trait) has no super. Don't be misled by RustRover's
  raw Ctrl+U "Go to Super", which jumps to the enclosing `pub mod` declaration
  (module-super noise); `RustSuperMethodsProvider` filters `gotoSuperTargets` to
  `RsAbstractable` (see its source) and so returns empty, mirroring the gutter
  "I↑" marker (absent on inherent methods), not raw Ctrl+U. Unlike Go's negative
  case (#25), Rust returns the correct empty hierarchy here, not an error.
