# Captured ground truth: fixtures, all languages

Some snapshot rows encode platform quirks intentionally. When you see a
"weird" expected result that looks like a bug, check this list first — the
IDE legitimately returns that output, and changing the probe to "fix" it
will just snapshot a different empty/odd result.

This file holds the notes that cover more than one language. The notes of one language are
in `<lang>/GROUND-TRUTH.md`.

- **`hier-callee-makeDefault` constructor callees split by language.** **Kotlin & PHP**
  return empty callees — constructor invocations inside a method body don't surface as
  call-hierarchy callees there. **Java & TypeScript** are non-empty: Java surfaces the
  `Circle`/`Rectangle`/`Square` constructors as `CONSTRUCTOR` callees, and WebStorm
  surfaces them (in TS) as `CLASS` callees — so both the Java and TS
  `hier-callee-makeDefault` snapshots are non-empty.
- **Enum type hierarchy — `direction:both` returns the *supertypes* view, which the IDE's
  combined Type Hierarchy widget hides.** `hier-type-Direction` (TS numeric enum) blesses
  `supertypes: [Number ×3]`; `hier-type-Severity-enum` (PHP string-backed enum) blesses
  `supertypes: [BackedEnum → UnitEnum, Labeled]`. Verified in WebStorm/PhpStorm: the
  **Supertypes** view shows exactly these, but the default combined ("both") widget shows
  *nothing* for the enum — a rendering quirk of that view, not a tool error. Don't re-bless
  these to empty. (`direction: both` is the union of the supertypes walk and the subtypes
  walk, not the combined widget: see "Why `direction: both` is a union" in
  `docs/ARCHITECTURE.md`.)
- **Library/SDK targets show as a bare basename**: a hit resolving into a
  JDK / stdlib / stub file (`java.lang.Object`, JS `Number.parseInt`, Python
  `int`, …) is reduced to basename + symbol identity, with no directory and no
  line/column — so it reads as `Object.class` / `lib.es5.d.ts` / `builtins.pyi`,
  not a path. By design (see "Path normalization — project vs library" in
  `live-test/CONVENTIONS.md`); a
  toolchain or IDE bump no longer drifts these rows, so it is not a re-bless
  trigger.
- **JS/TS return the full transitive super chain**: e.g.
  `super-LeafMix.greet-3level` (JS) and `super-DeepLeaf.m`/`super-DeepMid2.m` (TS)
  return every transitive super, matching the Java/Kotlin/Python analogs and
  WebStorm's overriding-gutter. The provider recurses on
  `JSInheritanceUtil.findNearestOverriddenMembers` to a fixpoint. Resolved in
  #23 (was previously immediate-parent only).
- **JavaScript and TypeScript `find_usages` search the base declaration too (#171, #196).**
  For a member that overrides a base member, WebStorm asks whether to search the
  base method. The result is the union of the answers Yes and No, with marks. The
  `DYNAMIC` rule is the platform rule (`UsageInfo(PsiReference)`: the reference
  resolves to nothing) and the rule of `JSUsageViewElementsListener`. The window
  observations of WebStorm 2026.2.0.1 on 2026-11-17:
  - TS `Circle.area` (`src/normal.ts:25:5`): Yes gives 4 usages of `Shape.area`
    (`normal.ts:14` and the 3 calls in `ShapeCollection`). No gives "Nothing
    found". Row `usage-Circle.area-override`: 4 usages, all `BASE`.
  - JS setter `Derived.value` (`src/setter_super.js:12:9`): Yes gives 2 results
    (the write at line 25, the read at line 26). No gives 1 result (line 25). Row
    `usage-Derived.value-write`: line 25 with no `match`, line 26 with `BASE`.
  - JS `Circle.area` (`src/normal.js:28:5`): Yes gives 2 results (`consumer.js:8`,
    `normal.js:17`). No gives 1 result. With "Show Dynamic Usages" on, the group
    "Dynamic usages in Project Files" also lists line 59 and line 65 (two calls).
    Row `usage-area-libraries-scope`: `consumer.js:8` with no `match`,
    `normal.js:17` with `BASE`, and the three `s.area()` / `best.area()` calls
    with `DYNAMIC`.
  - JS `Shape.area` (`src/normal.js:16:5`): 2 results and the same 3 dynamic
    usages. Row `usage-area-from-totalArea`.
  - The parameter `v` of the setter (`usage-Derived.value-param`): 1 usage, no
    `match`, no `notes`. The search does not walk up from an element inside a
    member to the member.
- **Java and Kotlin `find_usages` search the method itself and its super declarations (#175).**
  The window observations of IntelliJ IDEA 2026.2.0.1 on 2026-11-17. The IDE asks no
  question in the two languages.
  - Java `Circle.area` (`src/main/java/demo/Normal.java:33:12`): the IDE searches
    `Shape.area` only. The group "Usages or usages of base method in Project Files" has 3
    results: lines 21, 83 and 91 (line 91 holds two usages). Row `usage-Circle.area-override`
    gives the same 4 usages (21:61, 83:22, 91:35, 91:49), each with `BASE`. The `notes` entry
    names `demo.Shape#area` (`src/main/java/demo/Normal.java:18:21`).
  - Kotlin `Circle.area` (`src/main/kotlin/demo/Normal.kt:20:18`): the IDE searches
    `Shape.area` and `Circle.area`. The same group has 3 results: lines 16, 42 and 44. Rows
    `usage-Circle.area-override` and `usage-area-libraries-scope` give 16:74, 42:49 and 44:53,
    each with `BASE`. The `notes` entry names `demo.Shape#area`
    (`src/main/kotlin/demo/Normal.kt:13:18`).
  - No fixture call has a receiver of a subclass type, so each usage of these rows has
    `BASE`. A probe on a copy of the Kotlin fixture (2026-11-17, not in the suites) added
    `fun circleAreaProbe(c: Circle): Double = c.area()` and a Java class that extends
    `Shape`. The tool gave the probe call with no `match` and the other 5 usages with `BASE`,
    and the IDE listed the same 6 usages.
  - The Java rows on a method or a constructor (`usage-Circle-ctor`,
    `usage-Probe.target-files-scope`, the two `usage-Quirks.parse-*` rows,
    `usage-area-from-totalArea`, `usage-area-libraries-scope`) lost their `warnings` entry.
    Their usages did not change.
- **A reference inside a doc comment is a `COMMENT` usage in every language.**
  PHP `usage-Shape-class` lists `Shape` in `/** @var Shape[] */`
  (src/Normal.php:53) with `usageType` `COMMENT`. The platform rule of the
  "Usage in comments" group (`UsageTypeGroupingRule`) gives this type to each
  usage inside a comment, and a doc comment is a comment, before a language
  gives its own usage type.
- **`find_file` extension queries substring-match longer extensions**: `*.js` matches
  `package.json` (`.js` ⊂ `.json`) and `*.kt` matches `build.gradle.kts` / `settings.gradle.kts`.
  MinusculeMatcher fragments are not end-anchored without a trailing space; matcher-level
  behavior shared with the IDE popup, not a tool bug.
