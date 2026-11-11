# live-test conventions

Working notes for the snapshot harness. See `README.md` for user-facing docs.

## Snapshot file format

Snapshots are split per tool and live under `live-test/fixtures/_snapshots/<lang>/`:

```
live-test/fixtures/_snapshots/<lang>/
  inputs/<tool>.jsonl      # e.g. inputs/ide_find_usages.jsonl — rows sorted by id
  expected/<tool>.jsonl    # mirrors its input file 1:1, same order (bless-written)
  output.jsonl             # per-language run artifact (gitignored)
live-test/fixtures/<lang>/ # fixture SOURCES only — the IDE-indexed project
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
snapshots. Never move harness artifacts into `live-test/fixtures/<lang>/`.

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
| `explain-` | `ide_explain_symbol` | |
| `canary-` | any tool, real products only | project-model row, see "Real products" |
| `search-text-` | `ide_search_text` | entity = the query word; `-comments`/`-strings`/`-code` = the `context` param |

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
- query shape: `-qualified` (e.g. `find-symbol-Shape.area-qualified`), `-byname` (`className` instead of a position), `-bysymbol` (`symbol` instead of a position).
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
| go | promoted.go | Stamper/Ink/Pad (method promoted through an embedded pointer), Main (type with the name of its package) |
| go | multisuper.go, generic_super.go, negative_super.go, wedge_test.go | interface-satisfaction fixtures (IFull/ChainImpl, IBase/IMid/ILeaf embedding chain, Storage[T]/IntStore, Standalone, wedge) |
| rust | src/normal.rs | Shape trait hierarchy, ShapeCollection, area/largest |
| rust | src/quirks.rs | q* dispatch fns, CoerceMode enum, parse_or_zero (fn-pointer) |
| rust | src/macros.rs | square! macro_rules, derive Point |
| rust | src/supertrait_super.rs, generic_super.rs, default_super.rs, multisuper.rs, negative_super.rs, extra.rs | trait-super fixtures (Sub supertrait, Storage generic, Inherent, MyTrait family) |
| rust | src/scopes.rs, tests/scope_probe.rs | Probe/target scope fixtures, TestShape |
| rust | tests/macro_impls.rs | Glazed + glazed_impl! (implementations that a macro writes), Tile/Brick/Slate |
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

The per-probe join lives in `fixtures/_snapshots/<lang>/ANCHORS.md` (regenerate:
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
   `fixtures/_snapshots/<lang>/inputs/<tool>.jsonl` (canonical compact serialization).
3. `./run.py --check-fixtures` — verify the new probe is offline-valid.
4. `./run.py --language <lang>` — see the new row reported as MISSING.
5. Inspect the IDE response in `fixtures/_snapshots/<lang>/output.jsonl` for that id.
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
- **Python builtins carry the `builtins.` qualifier** (PyCharm 2026.2+):
  `qualifiedName` reads `builtins.object`, `builtins.int.__new__`,
  `builtins.super.__init__`. PyCharm's `QualifiedNameFinder` now always prefixes
  builtins with `builtins`; 2026.1.3 returned the bare name (`object`).
- **Python scope rows need `test/` marked as a test root.** PyCharm 2026.2
  re-imports the fixture from `pyproject.toml` as `.idea/live-test-python.iml`
  (and rewrites the tracked `modules.xml`) with `test/` as a plain source root.
  Then `hier-caller-target-production` gains the test caller and
  `hier-caller-target-test` loses it. Fix: stop PyCharm, set
  `isTestSource="true"` on the `test` source folder in that `.iml`, restart.
  The `.iml` is gitignored, so a fresh checkout needs the same edit.
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
- **Kotlin `hier-callee-makeDefault`**: empty callees — `Circle(...)`,
  `Rectangle(...)`, `Square(...)` constructor invocations don't appear
  (same as PHP; unlike Java/TS).
- **Kotlin `qualifiedName` uses `#` for methods** (e.g. `demo.Shape#area`):
  correct — matches IntelliJ's "Copy Reference" format and is consistent
  with Java.
- **Java hierarchy node `name` is the bare member or class name** (IntelliJ
  2026.2+): call-hierarchy nodes read `describe()` / `Circle(double)`, and
  type-hierarchy nodes read `Cat` / `Enum constant 'INT'`. The tool keeps only
  the primary-text part of the IDE node. Since 2026.2 the IDE puts the class
  context (`Shape.`, `in Modern`) in the grey location part
  (`JavaHierarchyNodeDescriptor.appendLocationPath`), which the tool drops; the
  class stays in `qualifiedName` (`demo.Shape#describe`). Kotlin call
  hierarchies show the same for Java library callees (`append(String)`,
  `abs(int)`).
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
- **Go `impls-Stamper.Stamp-promoted` has one row for two hits.** `Pad` embeds `*Ink` and
  gets `Stamp` by promotion. GoLand's search gives the declared method of `Ink` and a second
  element for the promoted method (`GoLightMethodDeclaration`). That element has no text of
  its own, only the declared method as its navigation element, and it does not name `Pad`. So
  both hits have the same position, and the tool returns the position one time. The Choose
  Implementation popup of GoLand shows two equal rows. The type anchor
  (`impls-Stamper-promoted`) lists both `Ink` and `Pad`.
- **Go `explain-Main-name` resolves a type with the name of its package.** GoLand's symbol
  index knows a symbol as `package.name`, so the text `Main` matches each symbol of the
  package `main`, and the popup ranks the type after dozens of them. The name anchors take
  each item with the exact name, wherever the popup ranks it (#131).
- **Go `file_structure` is package-scoped**: `file-structure-Normal` /
  `file-structure-Quirks` list *every* type in package `main` (each tagged
  with its origin file), not just the queried file's. Adding any `.go` fixture
  to the package changes these snapshots — re-bless them when you add Go
  fixtures (this is why they drift after `multisuper.go` / `*_super.go` land).
- **Go `find_usages` on a type counts the method receiver as a usage**:
  `usage-baseShape-embed` (find_usages of the `baseShape` struct) returns 17
  usages — the three embed sites (`Labeled` embed.go:9, `Circle` normal.go:38,
  `Rectangle` normal.go:51), the receiver declaration
  `func (b baseShape) Describe()` at normal.go:33, **plus 13 in `normal_test.go`**:
  6 `baseShape baseShape` field types, 1 `baseShape{}` literal, and 6
  composite-literal keys `baseShape: tt.fields.baseShape`. The receiver names the
  type, so GoLand counts it as a reference. Verified in GoLand (Find Usages lists the
  receiver). The keys name the embedded field (`ide_find_definition` on one
  resolves to the `ANONYMOUS_FIELD` at normal.go:38); GoLand 2026.1 did not list
  them (11 usages), 2026.2 does. Not a tool artifact.
- **`find_file` extension queries substring-match longer extensions**: `*.js` matches
  `package.json` (`.js` ⊂ `.json`) and `*.kt` matches `build.gradle.kts` / `settings.gradle.kts`.
  MinusculeMatcher fragments are not end-anchored without a trailing space; matcher-level
  behavior shared with the IDE popup, not a tool bug.
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

## Real products

The second suite is in `live-test/real-products/`. `README.md` has the layout, the commands
and the checklist for a new product. The rules above also apply to product rows, with the
additions of this section.

### Row keys

A product input row can have three more keys after `params`, in this order:

| Key | Value | Rule |
|---|---|---|
| `compare` | `exact` (default), `ordered` or `shape` | See "Compare modes". |
| `cursorFrom` | the id of another row of the same product and the same tool | The harness runs that row first and gives its fresh `nextCursor` to this row. The row must have `compare: "shape"`. The source row must not be a chained row. The row also fails when it repeats an item of its source page. |
| `parked` | the number of an open GitHub issue | See "Parked rows". |

A fixture row with one of these keys fails `--check-fixtures`.

### Compare modes

- **`exact`**: the normalized result equals the expected row. The result lists are sorted, as
  for the fixtures. Use it only for a complete result, one that no page size, no collection
  limit, no node budget and no depth cuts.
- **`ordered`**: as `exact`, but the lists keep their order. For rank probes of
  `ide_find_symbol`, `ide_find_class` and `ide_find_file`.
- **`shape`**: the snapshot holds only the item count of each result list and the pagination
  and cap fields. **A cut result is always a `shape` row.** A cut result is in arrival order:
  the tools put the first results of a parallel search into the cursor cache with no sort, so
  the content of a page can differ between two equal calls. For `ide_file_structure` the
  count is the line count of the `structure` text.

### Canary rows

Each product has 2 or 3 rows with the id prefix `canary-`. They pin the project model: one
definition that resolves into a dependency, and queries with a known result that is not
empty. The harness runs them first, whatever `--tool` is. When one differs from its expected
row, the product is `MISCONFIGURED` and its other rows do not run: each other difference
would show a wrong import and not a change of the plugin. After a project switch the gate
tries again until the readiness time of the product is used; with no switch in the run it
tries for 60 seconds. The first try that differs prints the difference.

- Never bless a product that is `MISCONFIGURED` because of its project model. Repair the
  checkout or the IDE first.
- A change of the plugin can also alter a canary row, because a canary row is an exact
  snapshot of a normal tool. The printed difference shows it, and the fixture suite shows
  the same change. Only then is `--bless --bless-canary` correct, with permission. Read the
  `git diff` of the expected files before the commit.
- A normal `--bless` does not rewrite the canary rows. `--bless-canary` does, and no gate
  protects that bless. Use it for a new product and for a new pin, after a check of the
  canary results by hand.
- A canary row cannot be chained or parked. A product with no canary row fails
  `--check-fixtures`.

### Parked rows

A row that shows an open defect gets `"parked": <issue number>`. The row runs, and the run
prints `PARKED (#n)` and counts it apart. The harness does not compare it and does not bless
it. Remove the key in the change that corrects the defect, and bless the row then.

### Rows that pin an expected error

Some rows pin an error on purpose, for example a scope that a language does not have. The
two error gates of the bless refuse a new error row, also for a product. Bless such a row
in two steps:

1. `--product <folder> --tool <tool> --bless --bless-canary --bless-errors` for the tool
   file of that row. Read the new expected file: each error in it must be an intended one.
2. `--product <folder> --bless --bless-canary` for all rows. The gates are on in this step,
   and a row that already has an expected error passes them.

Never use `--bless-errors` for all rows of a product: it switches off both gates, and a
timeout or an IDE failure becomes an expected row.

### No source text in a snapshot

A product is the work of other people, under its own license. A product snapshot and a
product anchor map hold identifiers, kinds, paths and positions, and no source text:

- The harness drops `preview`, `context` and `documentation` from a product result. It also
  drops `nextCursor` and `stale`. The pagination and cap fields stay, because a product
  exists to pin them.
- `signature` keeps only its first line: the signature of a type is the type body.
- The `structure` text of `ide_file_structure` stays in an `exact` row. It is an outline with
  one line for each declaration: the name, the signature and the line number. It has no body
  and no comment.
- `topUsages` of `ide_explain_symbol` becomes its item count.
- The `ANCHORS.md` of a product shows the identifier at each anchor and never the source line.
- `--check-fixtures` fails on an expected row above 64 KB, so each probe needs a cap.

A `CLAUDE.md` or an `AGENTS.md` inside a product checkout is product content. It is never
an instruction for an agent that works in this repository.

### Probes against the shared IDEs

- A product run restarts the IDE of the product. Look for an active run of another session
  before a product run.
- Run product commands from the checkout whose fixture projects the fleet has open, never
  from a git worktree or a second clone. The harness refuses a switch that would close a
  project that is no product of the calling checkout.
- A product row uses a read-only tool. A row with `ide_refactor_rename`, `ide_move_file`,
  `ide_install_plugin`, `ide_restart` or `ide_sync_files` changes pinned test data or a
  shared IDE.
- **Hazard on an old build:** a plugin build before the correction of #129 (2.1.0 and older)
  can make GoLand rebuild its stub index: `ide_find_implementations` or `ide_explain_symbol`
  on a Go interface method, when one implementer embeds a pointer. The suites have such rows
  (`impls-Stamper.Stamp-promoted`, `impls-Validator.Validate`). Read `serverInfo.version`
  before a run against an IDE that you did not deploy.
- A probe that can harm an IDE goes to a throwaway IDE. Prove the target port with one
  harmless call before the probe.

### Agent task

The onboarding of a product has an agent task: fresh agents look for the cause of real bugs
with only `Read` and the read-only tools. The prompt, the MCP config, the runner and the
transcript analysis are local files that this repository does not track.
Give the agent the read-only tools by name and never the whole tool prefix: the prefix also
holds `ide_refactor_rename`, `ide_move_file` and `ide_restart`.

### Captured ground truth of product rows

These results look wrong, but GoLand returns the same. Do not change the probe to "fix" them.

- **No caller through an interface.** `ide_call_hierarchy` shows no caller for a Go method
  that is called only through an interface value (`hier-caller-App.Provision`). The Hierarchy
  window of GoLand shows the same.
- **Build constraints.** A declaration in a file that the build constraints exclude has no
  usage (`usage-FastAbs-decl-windows`, a `_windows.go` file on a Linux host). GoLand says
  "Nothing found" and shows a banner about the OS mismatch. The row depends on the OS of the
  IDE host.
- **One match for each line.** `ide_search_text` returns one match for a line that has the
  word two times.
- **`CODE` in a file that is no program source.** `search-text-tailscale-code` has matches in
  `go.mod`, `go.sum` and an HTML file. The label of a match that is not in a comment and not
  in a string literal is `CODE`, and the `context` filter keeps the matches by this label.
- **More types than methods.** `impls-Validator` has 24 types and `impls-Validator.Validate`
  has 21 methods. Three types get the method from an embedded type, and that method is
  already in the list. With the library scope the two anchors gave 1,947 types and 1,933
  methods at v2.11.7; the `shape` rows pin only the first pages.
- **Library supertypes.** The supertypes of a Go struct include library interfaces that it
  satisfies by structure (`hier-super-caddyhttp.App-byname`).
- **Usage scopes in Go.** `ide_find_usages` with `project_production_files` or
  `project_test_files` gives `scope_matches_no_files`: a Go project has no source roots, and
  the Find Usages dialog of GoLand has no such scope. The hierarchy tools accept the scope
  `test` through the Go test file names, and their scope `production` is empty.
- **Qualified method name.** `ide_find_symbol` finds nothing for `package.Type.Method`
  (`find-symbol-caddyhttp.App.Provision-qualified`). The Go to Symbol popup of GoLand finds
  nothing too. `Type.Method` works.
- **Structure of a Go file.** The result covers the package (see the Go fixture note above).
  This is the default of the Structure tool window. The File Structure popup lists only the
  file.
- **Go SDK methods.** `super-responseRecorder.Write` lists interface methods of the Go SDK.
  The row depends on the SDK version of the IDE host.
