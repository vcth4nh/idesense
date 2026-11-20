# Captured ground truth: PHP fixture

These results of the PHP fixture look wrong, but the IDE returns the same. Do not change
a probe to "fix" one. The notes that cover more than one language are in
[../GROUND-TRUTH.md](../GROUND-TRUTH.md).

- **PHP `hier-callee-makeDefault`**: empty callees — constructor invocations don't
  surface (same as Kotlin; unlike Java/TS).
- **PHP `find_usages` takes the search of Find Usages of PhpStorm (#179, #182, #183).** The
  search facts come from the bytecode of `php.jar` (build 262.8665). The window observations
  are the one of #182 below and the notes in
  `live-test/real-products/_snapshots/phpunit/GROUND-TRUTH.md`.
  - A method. The tool asks the handler factory for no PHP method, so the question "Do you
    want to find usages of base method?" (a dialog that throws off the EDT) cannot occur, and
    no row has a `warnings` entry. The tool searches the method, each base method, the other
    methods that override a base method, and the methods that override the method
    (`PhpFindUsagesHandler.processElementUsages` with `checkImplementedMethods`). The
    declaration of an overriding method is no usage.
  - `Circle::area` (`src/Normal.php:22:21`), row `usage-Circle.area-override`: 4 usages
    (15:51, 63:21, 71:35, 71:48), each with `BASE`. Each call is on a value of the type
    `Shape`. The `notes` entry names `\Demo\Shape::area` (`src/Normal.php:12:30`). PhpStorm
    2026.2.0.1 (2026-11-17) lists the same 4 usages for the answer Base Method and for the
    answer Current Method. The reference of a call on a value of an abstract type resolves to
    the base method and to each implementation (`resolveInSubclasses`), so the mark rule looks
    for a base method among the targets first.
  - `Shape::area` (`src/Normal.php:12:30`), rows `usage-area-from-totalArea` and
    `usage-area-libraries-scope`: the same 4 usages with no `match`. The `notes` entry names
    the 2 overriding declarations and ends with "0 of the 4 usages have match OVERRIDE": the
    fixture has no call on a value of the type `Circle` or `Rectangle`. The phpunit row
    `usage-Dispatcher.dispatch` has `OVERRIDE` usages.
  - A class, interface, trait or enum. The `$this` references and the `self` / `static` class
    references inside the class are not in the list. This is the default of the Usage View of
    PhpStorm (`PhpThisOrSelfFilteringRule`, toggle "Show $this/self references"). The first
    page has a `notes` entry with their count. `usage-Rectangle-class`: 3 usages, 4 left out.
    `usage-Shape-class` and `usage-Shape-bysymbol`: 5 and 2. `usage-Quirks-class`: 0 and 2.
    `usage-Status-enum`: 4 and 1. `ide_explain_symbol` has the same count and the same entry
    (`explain-Circle-pos`: `usageCount` 2, 3 left out; `explain-Shape-name`: 5 and 2). A usage
    of a method or of a field keeps its `$this` rows (15:51 above is `$this->area()`).
