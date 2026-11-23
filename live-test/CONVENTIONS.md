# live-test conventions

The conventions for the rows, the snapshots and the fixture files of the harness.
[README.md](README.md) has the commands. [AGENTS.md](AGENTS.md) has the rules for an agent,
with the bless rule. The ground-truth notes are in the `GROUND-TRUTH.md` files (see
"Ground-truth notes").

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
  (`serialize_input_row` in `suite/cli.py`).

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
them. Prefer an append at EOF or a new file. An insert shifts the anchors below it
(see "When fixtures change"). Check the file's `file_structure`/`diagnostics`
pins first — appending to a pinned file drifts its blessed row.

| Language | File | Hosts |
|---|---|---|
| java | Normal.java | Shape/Circle/Rectangle/Square hierarchy, Drawable, ShapeCollection, Normal |
| java | Quirks.java | Quirks (overloads incl. parse ×2, dispatch), Coercer, CoerceMode enum, Coerce interface |
| java | Modern.java | record Point, sealed Animal + Cat/Dog |
| java | MultiSuper.java | diamond/chain interfaces (DiamondTop…), Named/Tagged/Identified + record LabelPoint, sealed shapes, Op enum |
| java | Probes.java | Probe/ProbeAux/ProbeProdChild (scope fixtures) |
| java | GenericSuper.java, LambdaSuper.java, StaticSuper.java, NegativeSuper.java | super-methods campaign fixtures (BaseRepo/Repo, LambdaHost, StaticBase/Derived, Standalone) |
| java | Broken.java | deliberate compile errors (ERROR-diagnostics probe) |
| java | Extras.java | Plain (toString override → library super) |
| kotlin | Normal.kt | Shape hierarchy, Drawable, ShapeCollection |
| kotlin | Quirks.kt | Coercer/Coercion/AbsCoerce/IntCoerce, quirk* dispatch fns (incl. quirkDispatchMap) |
| kotlin | Modern.kt | Counter, Printer delegation trio, Channel enum, Plain toString |
| kotlin | MultiSuper.kt, GenericSuper.kt, CompanionSuper.kt, AsyncSuper.kt, OperatorSuper.kt, SetterSuper.kt, NegativeSuper.kt | super-methods campaign fixtures |
| kotlin | Probes.kt | Probe/ProbeProdChild (scope fixtures) |
| javascript | src/normal.js | Shape hierarchy, Drawable, ShapeCollection, makeDefaultShapes |
| javascript | src/quirks.js | q* dispatch functions (qBind/qCond/qComputed/…) |
| javascript | src/probes.js | Probe, freeProdCaller, ProbeProdChild |
| javascript | test/probe.test.js | ProbeTest, ProbeTestChild (cross-file CommonJS extends) |
| javascript | src/setter_super.js | Base/Derived accessors, writeProbe WRITE-usage site |
| javascript | src/accessors.js, mixin_super.js, multisuper.js, triple_super.js, async_super.js, negative_super.js, consumer.js | super-methods/mixin campaign fixtures |
| javascript | src/outline.js | export default object (not at line 1) with an array of object literals and a spread element over several lines (file structure) |
| typescript | src/normal.ts | Shape hierarchy, Drawable, ShapeCollection |
| typescript | src/multisuper.ts | diamond (DiamondTop/DiamondBottom), AbstractCombo/ConcreteCombo (readonly p), accessor/static supers |
| typescript | src/quirks.ts | q* dispatch, TypedCoercer |
| typescript | src/enums.ts, namespaces.ts, decorators.ts | Color/Direction enums, Geometry namespace, Service + traced decorator |
| typescript | src/decorators_caller.ts | useService — cross-file caller of decorated method |
| typescript | src/probes.ts, test/probe.test.ts | scope fixtures |
| typescript | src/setter_super.ts, const_super.ts, generic_super.ts, static_super.ts, async_super.ts, negative_super.ts | super-methods campaign fixtures |
| php | src/Normal.php | Shape hierarchy, ShapeCollection, area/add |
| php | src/Quirks.php | Quirks static dispatch (qMatch/…), IntCoercer/LenCoercer |
| php | src/Modern.php | Color/Status enums |
| php | src/MultiSuper.php, AbstractTraitSuper.php, EnumSuper.php, ConstructorSuper.php, StaticSuper.php, NegativeSuper.php | super-methods campaign fixtures (traits, backed enums, ctor supers) |
| php | src/Probes.php, tests/ProbeTest.php | scope fixtures |
| php | src/Php8.php | Php8/Php8Helper: nullsafe `?->`, first-class callable, const+property |
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
| python | src/enums.py | Channel(Enum) + member access |

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
  threshold — see "Snapshot file format"). In Go, a comment word that spells a
  declared name is a usage of that declaration in every scope, also the default
  `project_files` (`usageType` `COMMENT`, #132), and this applies to unexported
  names too (`baseShape`). Prefer a paraphrase that does not spell the name
  (`circle` for `Circle`), or re-bless the `find_usages` rows of that name.
- **Dictionary words only** in the diagnostics-pinned java files
  (`Broken.java`, `Quirks.java`, `Normal.java`) — a typo can spawn a
  spell-check inspection row.
- New fixture code ships **with** its header + construct comments. Inserting a
  comment into an already-pinned file shifts every anchor below it: re-anchor
  the affected input rows and re-bless (see "When fixtures change").

## Bless safety

`./run.py --bless` is gated. By default it refuses to:

1. Bless rows whose result is `tool_error_text` / `transport_error` /
   `jsonrpc_error`. Override with `--bless-errors` and `--tool` (rare; usually fix
   the probe first).
2. Bless rows whose fresh result is a structured `{"error": ...}` payload
   when the previously blessed result was **not** an error (or the row is
   new) — a degraded IDE must not silently poison snapshots. Rows already
   blessed as errors (intentional negative probes) stay re-blessable.
   Override with `--bless-errors` and `--tool` for the file of that row (e.g. when adding a
   new negative probe).
3. Drop orphan expected ids (ids in `expected/` no longer in any
   `inputs/<tool>.jsonl`). Override with `--prune`.
4. Run with `--tool` filter matching zero rows.

Writes are atomic (temp file + `os.replace`) — SIGINT-safe but not concurrency-
safe. Don't run parallel `--bless` against the same language.

A bless locks in whatever the live IDE returns as truth. If the IDE has a
regression, that regression becomes the new baseline. The rule for when a bless
needs a question to the owner of the repository is in [AGENTS.md](AGENTS.md) ("Bless").

A fixture row whose result differs between two equal runs shows a defect. Write an issue, and do
not bless the row. A fixture row has no compare mode and cannot be parked (see "Row keys"), so the
row fails until the correction. For a product row, see "A row that differs between two equal
runs".

### Check a bless

`--bless` has no option for one row. It writes each row that `--language`, `--product` and
`--tool` select, so restrict it with `--tool` to the tool whose rows your change affects.
Check what a bless changed before the commit:

- A bless that only adds rows: the run before it shows only `PASS` and `MISSING`. After it,
  `git diff --numstat -- <snapshot folder>/expected/` shows no deleted line. A deleted line
  means that the bless also pinned a changed or an unstable row: put the file back and
  examine that row.
- A bless that changes rows: the ids of the deleted lines (`git diff -U0`) equal the ids that
  you intended to change.
- To hold back a changed row, put its old line back from git. A new row that you hold back
  makes `--check-fixtures` fail until it is blessed.

## Path normalization — project vs library

`normalize()` in `suite/cli.py` keeps snapshots stable across machines, IDE installs,
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
- **Compiled classes inside the project** — a `.class` entry of a jar that the
  build of the project makes keeps its project-relative path. `line`/`column`
  are dropped. They are a position in the text that the IDE makes for the
  class, and that text depends on the IDE configuration: the stub text, or the
  decompiled text after the user accepts the legal notice of the decompiler.

Absoluteness is the signal because the plugin already emits project files
relative and library files absolute. We key off the **project root** (which we
are handed), never off library install locations — so a new host, install
manager, SDK version, or renamed checkout needs **zero** maintenance. A line
shift in a library file changes no row. A new qualified name or base name of a
library symbol (after an IDE or a toolchain update) still changes the row.
`enclosingScope` is kept: it is the enclosing method or class scope (a relative name
chain like `['ShapeCollection', 'Add']`), which is real signal. A file node or a
directory node has an empty list (#285), so the field holds no path of the machine.

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
6. Bless under the bless rule of [AGENTS.md](AGENTS.md):
   `./run.py --bless --language <lang> --tool <tool>`. It rewrites each row of that tool file.
   Check the diff (see "Check a bless").
7. If the result looks wrong but the IDE returns the same, add a note with the evidence
   (see "Ground-truth notes").
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
  `expected/` in lockstep (script it; ids are the join key). Then run
  `--write-anchors`, `--check-fixtures` and a full language run. Re-bless the
  rows whose names changed.

## Ground-truth notes

A row can pin a result that looks wrong but that the IDE also returns. Each such result has
a note with its evidence: an observation of the IDE window, or a citation of the source or
of the bytecode. A note can also record a result that differed between two equal runs (see "A
row that differs between two equal runs"). A note starts with a bold title that names the
language, the product or the row. Each note is in one file only:

- `fixtures/_snapshots/GROUND-TRUTH.md`: a note that covers more than one language.
- `fixtures/_snapshots/<lang>/GROUND-TRUTH.md`: a note of one fixture language.
- `real-products/_snapshots/<product>/GROUND-TRUTH.md`: a note of one product.

When a note refers to a note of another file, it names that file.

## Real products

The second suite is in `live-test/real-products/`. `README.md` has the layout, the commands
and the checklist for a new product. `AGENTS.md` has the rules for work against the shared
IDEs and for the product checkouts. The conventions above also apply to product rows, with
the additions of this section.

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
  `ide_find_symbol`, `ide_find_class` and `ide_find_file`. Use it only when no two items of
  the result have the same rank. `ide_find_file` gives files with the same name in the order
  of the IDE index, which changes with a new index, and the Go to File popup changes their
  order from one open to the next (seen on WebStorm 2026.3, see the uptime-kuma
  [GROUND-TRUTH.md](real-products/_snapshots/uptime-kuma/GROUND-TRUTH.md)).
- **`shape`**: the snapshot holds only the item count of each result list and the pagination
  and cap fields. **A cut result is always a `shape` row.** A cut result is in arrival order:
  the tools put the first results of a parallel search into the cursor cache with no sort, so
  the content of a page can differ between two equal calls. For `ide_file_structure` the
  count is the line count of the `structure` text.

### Canary rows

Each product has 2 to 4 rows with the id prefix `canary-`. They pin the project model: one
definition that resolves into a dependency, and queries with a known result that is not
empty. The harness runs them first, whatever `--tool` is. When one differs from its expected
row, the product is `MISCONFIGURED` and its other rows do not run: each other difference
would show a wrong import and not a change of the plugin. After a project switch the gate
tries again until the readiness time of the product is used; with no switch in the run it
tries for 60 seconds. The first try that differs prints the difference. When the IDE loads a
part of the project model after it reports smart mode (a nested dependency root, a library
that the sync of a build tool adds), one canary row must resolve into that part.

- The rule for a product that is `MISCONFIGURED` because of its project model is in
  AGENTS.md ("Bless").
- A change of the plugin can also alter a canary row, because a canary row is an exact
  snapshot of a normal tool. The printed difference shows it, and the fixture suite shows
  the same change. For a change of the plugin, only then is `--bless --bless-canary`
  correct, under the bless rule of AGENTS.md. Read the `git diff` of the expected files
  before the commit.
- A normal `--bless` does not rewrite the canary rows. `--bless-canary` does, and no gate
  protects that bless. Use it for a new product and for a new pin, after a check of the
  canary results by hand.
- A canary row cannot be chained or parked. A product with no canary row fails
  `--check-fixtures`.

### Parked rows

A row that shows an open defect gets `"parked": <issue number>`. The row runs, and the run
prints `PARKED (#n)` and counts it apart. The harness does not compare it and does not bless
it. Remove the key in the change that corrects the defect, and bless the row then.

### A row that differs between two equal runs

- The result is cut: the row is a `shape` row (see "Compare modes").
- The difference shows a defect, for example a result with a second copy of a part: write an
  issue and park the row.
- The difference occurred one time and its cause is not known: keep the expected row, and add
  a note with the observation to the `GROUND-TRUTH.md` of the product. At the second
  observation, write an issue and park the row.

### Rows that pin an expected error

Some rows pin an error on purpose, for example a scope that a language does not have. The
two error gates of the bless refuse a new error row, also for a product. Bless such a row
in two steps:

1. `--product <folder> --tool <tool> --bless --bless-canary --bless-errors` for the tool
   file of that row. Read the new expected file: each error in it must be an intended one.
2. `--product <folder> --bless --bless-canary` for all rows. The gates are on in this step,
   and a row that already has an expected error passes them.

The harness refuses `--bless-errors` without `--tool`: the flag switches off both gates for
each selected row, and a timeout or an IDE failure becomes an expected row.

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
