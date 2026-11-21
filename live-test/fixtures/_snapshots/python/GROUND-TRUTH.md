# Captured ground truth: Python fixture

These results of the Python fixture look wrong, but the IDE returns the same. Do not change
a probe to "fix" one. The notes that cover more than one language are in
[../GROUND-TRUTH.md](../GROUND-TRUTH.md).

- **Python `impls-Drawable.draw`**: returns empty. `Drawable` is a
  `typing.Protocol`, so PyCharm has no nominal implementer set to enumerate
  (`usage-Drawable-protocol` is likewise empty).
- **Python builtins carry the `builtins.` qualifier** (PyCharm 2026.2+):
  `qualifiedName` reads `builtins.object`, `builtins.int.__new__`,
  `builtins.super.__init__`. PyCharm's `QualifiedNameFinder` now always prefixes
  builtins with `builtins`; 2026.1.3 returned the bare name (`object`).
- **Python usage rows with `match` `DYNAMIC`.** `usage-area-from-describe` and
  `usage-area-libraries-scope` give `src/normal.py:79:47` (`key=lambda s: s.area()`:
  the parameter `s` has no type) with `match` `DYNAMIC`. The platform rule gives
  it: the PyCharm handlers do not override `processElementUsages`, so Find Usages
  of PyCharm builds each usage with `new UsageInfo(reference)`
  (`FindUsagesHandlerBase.processElementUsages`,
  `lib/intellij.platform.analysis.impl.jar`, build 262.8665), and that constructor
  sets the dynamic flag when the reference resolves to nothing. The window
  observation of the same rule is the beets note "173 usages of `BeetsPlugin`" in
  `live-test/real-products/_snapshots/beets/GROUND-TRUTH.md` (group "Dynamic usages in
  Project Files").
- **Python `find_usages` searches the base method too (#208).** The window
  observations of PyCharm 2026.2.0.1 on 2026-11-17:
  - `Circle.area` (`src/normal.py:36:9`): the IDE asks "Method area overrides method of
    class Shape. Do you want to find usages of the base method?". Yes targets
    `Circle.area` and `Shape.area`. Yes shows "Usages in Project Files 2 results"
    (line 29, line 74) and "Dynamic usages in Project Files 1 result" (line 79). No
    shows the dynamic usage only. Row `usage-Circle.area-override`: 29:51 `BASE`, 74:20
    `BASE`, 79:47 `DYNAMIC`. The `notes` entry names `Shape.area`.
  - `Square.__init__` (`src/normal.py:59:9`): Yes has 4 targets: `Square.__init__`,
    `Rectangle.__init__`, and `object.__init__` two times (the builtins stub and
    builtins). Yes shows 2 result rows: line 60 `super().__init__(side, side)` and line
    85 (`Rectangle(` and `Square(` on one row). Row `usage-Square.__init__-override`:
    85:47 with no `match`, 85:26 `BASE`, 60:9 `BASE`. The first `notes` entry names
    `Rectangle.__init__`. The second `notes` entry is "The base method
    builtins.object.__init__ is not searched: each class is a subclass of object." The
    fixture has no usage of `object.__init__`, so the result equals the Yes list. Approved
    deviation: see "Where a tool differs from the IDE on purpose" in
    [docs/ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose).
