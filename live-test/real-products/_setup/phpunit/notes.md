# phpunit

- Repository: https://github.com/sebastianbergmann/phpunit
- Pin: tag `13.3.1`, commit `fc024931d6ad047404e9d86536735923fe63a06b`, committed 2026-08-13
- License: BSD-3-Clause
- IDE: PhpStorm (port 29175)
- PHP: `composer.json` needs PHP 8.4.1 or later and six extensions. The machine has PHP 8.2.
  PhpStorm needs no PHP interpreter to index the product.
- Autoload: `classmap` of `src/` and `tests/_files`, not PSR-4.

## Setup

Run `bootstrap.sh`. It needs `php` on the `PATH` and composer 2: `composer` on the `PATH`, or
else the `composer.phar` of the mise tool `github:composer/composer`. It runs `composer install`
in the checkout, and it writes `.idea/modules.xml`, `.idea/phpunit.iml` and `.idea/php.xml`
when they are absent. The product ignores `.idea` and `vendor` in its own `.gitignore`.

- `composer.lock` is committed, and `composer install` never writes it.
  `--ignore-platform-reqs` skips the check of the PHP version and the extensions of the
  machine. The packages go to `vendor/` in the checkout.
- The product has three composer roots: the root, `build/scripts/phar-set-timestamps` and
  `tools/.phpstan`. The packages of the last two are committed in their `vendor/` folders.
- PhpStorm restores a project at its start only when the folder has IDE project files.
- The module file is the model that PhpStorm writes at the first open of the folder: one
  module with no source root and no test root, and each package folder of the three composer
  roots excluded (36 folders, read from `vendor/composer/installed.json` of each root). A
  restore adds no exclusion by itself.
- At each open, the composer sync of PhpStorm puts the same package folders on the PHP
  include path (`IncludePathApplier` in `idea.log`). So they are library roots.
- The composer sync sets the language level from `composer.json` (8.4). At a first open, the
  check of the used language features of PhpStorm can set 8.5 before the sync, because one
  test file uses the pipe operator. `php.xml` fixes 8.4 and turns that check off.

Times on 2026-11-12: the first `composer install` took 29 s with the downloads. With a warm
composer cache the bootstrap runs in 4 s, and a second run takes 2 s.

## Library files in the expected rows

A file of `vendor/` is a file of the checkout, so a row keeps its path and its line. A
bundled stub file keeps only its base name.

| Row | File | Decided by |
|---|---|---|
| `canary-def-Differ-into-dependency` | `vendor/sebastian/diff/src/Differ.php` | `composer.lock`: sebastian/diff 9.0.0 |
| `def-OriginalExporter-via-alias` | `vendor/sebastian/exporter/src/Exporter.php` | `composer.lock`: sebastian/exporter 8.2.1 |
| `find-class-Version-libraries-scope` | `vendor/sebastian/version/src/Version.php`, `vendor/phar-io/version/src/Version.php`, `vendor/phpunit/php-code-coverage/src/Version.php` | `composer.lock`: sebastian/version 7.0.0, phar-io/version 3.2.1, phpunit/php-code-coverage 14.3.0 |
| `find-file-Facade.php-libraries-scope` | `vendor/phpunit/php-file-iterator/src/Facade.php` and three `Facade.php` below `vendor/phpunit/php-code-coverage/src/Report` | `composer.lock`: phpunit/php-file-iterator 7.0.1, phpunit/php-code-coverage 14.3.0 |
| `canary-def-Timestamps-into-vendored` | `build/scripts/phar-set-timestamps/vendor/seld/phar-utils/src/Timestamps.php` | the pin: the folder is committed (seld/phar-utils 1.2.2 in the `composer.lock` of that root) |
| `def-count-into-stubs` | `standard_8.php` | the PHP stubs that the PhpStorm build bundles |
| `hier-super-MockObjectTest`, `super-UnaryOperator.count` | `Core_c.php` | the PHP stubs that the PhpStorm build bundles |

The language level is in `.idea/php.xml` of the bootstrap: `php_language_level="8.4"` and
`suggestChangeDefaultLanguageLevel` false.

## Measured

PhpStorm 2026.2 (PS-262.8665.325), `-Xmx2048m`, plugin 2.1.1-dev.12, 2026-11-12.

| Item | Value |
|---|---|
| Switch: stop PhpStorm, mark the projects, start, all projects listed | 11 s |
| Ready after the switch, first open | 20 s |
| First indexing: 4,803, 834, 21, 334 and 6,806 files | 23 s |
| PHP fixture rows while `phpunit` is open | 116 passed (116 before the open) |
| Resident memory of PhpStorm, `php` fixture plus `phpunit` | 2832 MB |
| Used heap after a full collection, after the open | 276 MB |

The used heap stays far below 1200 MB (60% of the limit), so PhpStorm keeps `-Xmx2048m`.

A next open takes 11 s for the switch and 0 s to readiness.

## Import check

Done on 2026-11-12 with plugin 2.1.1-dev.12. The product is accepted.

| Call | Result |
|---|---|
| `ide_find_class`, query `TestResult` | 2 classes |
| `ide_find_definition`, `src/Util/DifferBuilder.php:31:20` | the constructor of `Differ`, `vendor/sebastian/diff/src/Differ.php:38` |
| `ide_find_usages` of `TestCase`, `pageSize` 100 | 100 usages, `totalCollected` 500, `truncated` true |
| `ide_type_hierarchy`, subtypes of `TestCase` | 1,429 subtypes on the first open |
| `ide_file_structure`, `src/Runner/TestResult/TestResult.php` | a structure of 136 lines |

Comparison with PhpStorm itself. A second PhpStorm with a window opened a copy of the pin
with no `.idea` folder, so that PhpStorm made the project model by itself:

- The model of PhpStorm is the model of the bootstrap: the same module file and the same 36
  excluded folders. A restore of the bootstrap files gives the same model.
- Go to Declaration at `src/Util/DifferBuilder.php:31:20` opens the constructor of `Differ` in
  `vendor/sebastian/diff/src/Differ.php`. The tool gives the same.

Project model facts that the probe rows rely on:

- No folder is a source root or a test root. The usage scopes `project_production_files` and
  `project_test_files` give `scope_matches_no_files`, also for `ide_find_file`, and the
  hierarchy scope `production` gives no caller. The rows pin these results. The bootstrap marks
  no root: it keeps the model that PhpStorm makes by itself.
- `vendor/` itself is no excluded folder: only its package folders and `vendor/composer` are.
- Canary rows: 4. `canary-def-Differ-into-dependency` pins the include path of the root
  composer packages, `canary-find-class-TestFinishedSubscriber` the project index, and
  `canary-find-file-Differ.php` the excluded package folders (no `vendor/` file in the
  project scope). `canary-def-Timestamps-into-vendored` pins the nested composer root
  `build/scripts/phar-set-timestamps`: PhpStorm attaches it about 5 s after it reports smart
  mode, so the gate waits for it.
- PhpStorm indexes the content of each `.phar` file as a library. A path in a phar has the form
  `tools/.phpstan/vendor/phpstan/phpstan/phpstan.phar/src/...`, a path that is not on the disk.
  After a restart, the content of this phar can be present or absent in the index: `idea.log`
  shows "Updating PHARs" two times at the first open and one time after a restart. On
  2026-11-12, `ide_find_class` for a class of the phpstan phar found it after one restart and
  not after the next one.
- Rule: no row resolves into a phar, and no row counts a result in a phar. The rows that did
  were replaced. Two more close and open cycles, one with the phar content present and one with
  it absent, gave the same result for all 66 rows.
- The PHP outline shows the default values of properties and parameters, the values of
  constants and of enum cases, and no attribute. Only the structure row of a file with no such
  value is an `exact` row.

## Issues

These rows are parked. Each one changes with the fix of its issue only.

| Row | Issue |
|---|---|
| `usage-DeferringDispatcher` | #179: the `$this`, `self` and `static` references in the class, which Find Usages hides |
| `find-symbol-SHORT_OPTIONS`, `def-SHORT_OPTIONS-const` | #180: a class constant gets the kind `CLASS` (sub-issue of #27) |
| `search-text-unordered-code` | #181: `context: "code"` returns comment lines and string lines |
| `usage-Dispatcher.dispatch` | #183: the usages of the overriding methods are absent (104 of 115) |
| `search-text-wget` | #184: a match in an injected fragment (a Markdown code block) comes two times |
| `search-text-updateTimestamps-build` | #146: the files under `build/` are absent |

`explain-DeferringDispatcher.dispatch-pos` is blessed with its `warnings` entry: its count
equals Current Method of Find Usages (103). #182 tracks the warning.
