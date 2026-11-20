# Captured ground truth: phpunit

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **phpunit: no source root and no test root.** The autoload of the product is `classmap`, and
  PhpStorm makes one module with no source root and no test root. The bootstrap keeps this
  model. So `ide_find_usages` with `project_production_files` or `project_test_files` gives
  `scope_matches_no_files` (`usage-wasSuccessful-production-scope`, `-test-scope`; these error
  rows need the two-step bless). `ide_find_file` gives the same error and tells the agent to
  omit the scope. The call hierarchy scope `production` gives no caller
  (`hier-caller-wasSuccessful-production-scope`), and the PHP type hierarchy ignores the scope
  (`hier-sub-Exception-production-scope` equals `hier-sub-Exception`).
- **phpunit: the nested composer root comes after smart mode.** PhpStorm attaches the root
  `build/scripts/phar-set-timestamps` some seconds after it reports smart mode. After a start
  of PhpStorm, the definition at `build/scripts/phar-set-timestamps/run.php:52:13` gave
  "Could not resolve symbol definition" at 16.9 s, while the IDE was smart, and the file
  `Timestamps.php` of that root from 22.3 s on. So the row that resolves into it is a canary
  row (`canary-def-Timestamps-into-vendored`), and the gate waits for it.
- **phpunit: phar files.** PhpStorm indexes the content of each `.phar` file as a library, at
  a path that is not on the disk. After a restart this content can be present or absent. So no
  row resolves into a phar, and no row counts a result in a phar.
- **phpunit: qualified names from `PhpQualifiedNameProvider`.** A local variable gets the
  namespace and its name: `def-contextLines-local` gives `\PHPUnit\Util\contextLines`. An
  anonymous class has an empty `name` and the namespace with a trailing `\` as its
  `qualifiedName` (6 subtypes of `hier-sub-Printer`). The provider returns `getFQN()` of the
  element (bytecode, build 262.8665).
- **phpunit: the callees of a method include the method.**
  `hier-callee-DeferringDispatcher.dispatch-d1` lists `DeferringDispatcher.dispatch` itself.
  The Hierarchy window of PhpStorm shows the same.
- **phpunit: the usages of `Dispatcher::dispatch` and of its implementations (#182, #183).**
  `Dispatcher::dispatch` (`src/Event/Dispatcher/Dispatcher.php:22:21`) is an interface method
  with 3 implementations. Find Usages of PhpStorm with this target shows 115 results.
  `usage-Dispatcher.dispatch` gives 115 usages: 104 with no `match`, and 11 with `OVERRIDE`
  (calls on a value whose type is an implementing class). The `notes` entry names the 3
  overriding declarations. `usage-DeferringDispatcher.dispatch-override`
  (`DeferringDispatcher.php:40:21`) gives the same 115 usages from the side of one
  implementation: 6 with no `match` (calls on a `DeferringDispatcher` value) and 109 with
  `BASE`. Its `notes` entry names `Dispatcher::dispatch`. No row has a `warnings` entry:
  `explain-DeferringDispatcher.dispatch-pos` has `usageCount` 115 (before the change: 103 and
  the entry "Find-usages handler factory PhpFindUsagesHandlerFactory threw").
- **phpunit: a class row has no `$this`, `self` or `static` reference (#179).**
  `usage-DeferringDispatcher` (`DeferringDispatcher.php:17:13`) gives 13 usages, and the
  `notes` entry says that 18 references through `$this`, `self` or `static` inside the class
  are not in the list. Find Usages of PhpStorm shows "Usages in Project Files 13 results".
  The class `ShellExitCodeCalculator` (no row) gives 4 usages and the count 16; PhpStorm shows
  4 results.
- **phpunit: parked rows.** `find-symbol-SHORT_OPTIONS` and `def-SHORT_OPTIONS-const` are
  parked with #180 (a class constant gets the kind `CLASS`), `search-text-unordered-code` with
  #181 (comment and string lines in `context: "code"`), `search-text-wget` with #184 (a match
  in an injected fragment comes two times) and `search-text-updateTimestamps-build` with #146.
