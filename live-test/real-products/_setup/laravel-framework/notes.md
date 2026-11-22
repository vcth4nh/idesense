# laravel-framework

- Repository: https://github.com/laravel/framework
- Pin: tag `v13.25.0`, commit `ed36fe882bd4eed4e6ff75343cbad8dbda03fdba`, committed 2026-08-11
- License: MIT (`LICENSE.md`)
- IDE: PhpStorm (port 29175)
- Languages: PHP. The product also has Blade templates (124 `.blade.php` files) and 87 `.stub`
  files (the templates of the `make:` commands below `src/`).
- PHP: `composer.json` needs PHP 8.3 and seven extensions. PhpStorm needs no PHP interpreter
  to index the product.
- Autoload: PSR-4. `Illuminate\` is `src/Illuminate/`, and `Illuminate\Support\` is also in
  `src/Illuminate/Macroable/`, `Collections/`, `Conditionable/` and `Reflection/`.
  `autoload-dev` has `Illuminate\Tests\` (`tests/`). 37 of the 38 components below
  `src/Illuminate` have a `composer.json` of their own (each with a PSR-4 entry for its
  folder); `Foundation` has none. Two test fixtures below `tests/Foundation/fixtures` have a
  `composer.json` too. The checkout has 3,030 PHP files: `src/` 265,503 lines, `tests/`
  275,358 lines, and 60 files in `types/` (type assertion scripts of PHPStan).

## Setup

Run `bootstrap.sh`. It needs `php` on the `PATH` and composer 2: `composer` on the `PATH`, or
else the `composer.phar` of the mise tool `github:composer/composer`. It runs `composer install`
in the checkout, and it writes `.idea/modules.xml`, `.idea/laravel-framework.iml` and
`.idea/php.xml` when they are absent. The product ignores `/.idea`, `/vendor` and
`composer.lock` in its own `.gitignore`.

- Upstream has no lockfile. So `composer.lock` next to `bootstrap.sh` pins the dependencies
  (140 packages: 73 for production, 67 for development). The first bootstrap run made it on
  2026-11-22 with `composer update --no-install` and `COMPOSER_ROOT_VERSION=13.25.0`. Composer
  has no option for a date limit. So the bootstrap read the release time of each locked
  package: a package with a release at or after 2026-11-20 00:00 UTC got the constraint
  "lower than the locked version", and composer resolved again. Three passes took the newest
  release before the limit for six packages (`aws/aws-sdk-php`, `guzzlehttp/guzzle`,
  `guzzlehttp/promises`, `guzzlehttp/psr7`, `phpseclib/phpseclib`, `resend/resend-php`). The
  newest package in the lockfile has the time 2026-11-19 20:34 UTC.
- The version of the root package is the pin. So `orchestra/testbench-core`, which requires
  `laravel/framework`, resolves to v11.4.0 (2026-08-07). No copy of an `illuminate/*` package
  is in `vendor/`: the root package replaces each one.
- The bootstrap copies the lockfile into the checkout, where the product ignores it, and runs
  `composer install`. `--ignore-platform-reqs` skips the check of the PHP version and the
  extensions of the machine. `--no-scripts` runs no script of the product, and `--no-plugins`
  loads no composer plugin. The packages go to `vendor/` in the checkout.
- PhpStorm restores a project at its start only when the folder has IDE project files.
- The module file is the model that PhpStorm 2026.3 writes at the first open of the folder.
  It has a source root for each PSR-4 entry of each `composer.json` of the product (46 roots),
  with the namespace as the package prefix: `src/Illuminate`, one root for each component
  folder, the four `Illuminate\Support\` folders two times (one time from the root
  `composer.json`, one time from the `composer.json` of the component), `tests` as a test root
  (`Illuminate\Tests\`), and `tests/Foundation/fixtures/laravel1/app` and `laravel2/app` as
  production roots inside the test root. `vendor/composer` and the folder of each composer
  package are excluded (140 folders). The bootstrap reads the packages from
  `vendor/composer/installed.json`. A restore adds no exclusion by itself.
- At each open, the composer sync of PhpStorm puts the package folders on the PHP include path
  (`IncludePathApplier` in `idea.log`), so they are library roots.
- `php.xml` holds the language level 8.3. The composer sync sets it from `composer.json`
  (`"php": "^8.3"`), and the status bar shows "PHP: 8.3".
- `vendor/phpstan/phpstan/phpstan.phar` is a library root, and PhpStorm indexes its content
  (`ide_find_class` with `project_and_libraries` finds `\PHPStan\Analyser\Analyser` in it
  after the second open). `vendor/bin/phpstan.phar` is a composer proxy script, not a phar:
  at the first open, `idea.log` has the warning "Stub end marker missing" for it. No row
  resolves into the phar or counts a result in it (see phpunit, "phar").
- The bundled plugin Laravel Idea 13.4.1.261 adds the library file
  `laravel-idea-library/.phpstorm.meta.php` (in `plugins/laravel-idea/lib/laravel-idea-13.4.1.261.jar`
  of PhpStorm). The Callers window and `ide_call_hierarchy` show this file as a caller of
  `Arr::pull`.

## Measured values

PhpStorm 2026.3 (PS-263.7307.215), plugin 2.1.1-dev.31, `-Xmx2048m`, 2026-11-22.

| Item | Value |
|---|---|
| Checkout with its dependencies | 297 MB: 36 MB, `vendor/` 261 MB (140 packages, 14,924 PHP files; `aws/aws-sdk-php` 78 MB) |
| First bootstrap, with the downloads and three resolution passes (no curl extension) | 8 min 16 s |
| Bootstrap, second and third run | 1 s |
| First open: switch, then ready | 11 s, 50 s |
| First indexing (three passes: 3,345, 15,812 and 7,079 files) | 42 s |
| Next open after a switch to phpunit: switch, then ready | 11 s, 0 s |
| Resident memory, `php` fixture plus `laravel-framework`, after the first open | 4,182 MB |
| Used heap after a full collection, after the first open | 335 MB (limit 2,048 MB) |
| One run of the product rows, warm, then after a switch | 13 s to 18 s, 32 s |
| Slowest row at its first call after the open (callers of `Arr::pull`, `maxDepth: 2`; the suite has no such row now, see GROUND-TRUTH.md) | 8.8 s |
| `hier-caller-Arr.random-d2`, first call (not the first call after an open) | 2.9 s |
| `ide_call_hierarchy` callers of `Arr::wrap`, `maxDepth: 2` (no row: `hier-caller-Arr.wrap-d1` has depth 1) | 31 s; 167 + 33 nodes, cut at the node budget of 200 |

## Rows that depend on a library

| Row | Library (lockfile, or the PhpStorm build) |
|---|---|
| `canary-def-Finder-into-dependency` | `symfony/finder` v8.1.11 |
| `super-Repository.get-into-psr` | `psr/simple-cache` 3.0.0 |
| `find-class-Uuid-libraries-scope` | `fakerphp/faker` v1.24.1, `ramsey/uuid` 4.10.0, `symfony/uid` v8.1.9, `symfony/polyfill-uuid` v1.43.0, the PHP stubs of PhpStorm |
| `find-file-Carbon.php-libraries-scope` | `nesbot/carbon` 3.15.1, `carbonphp/carbon-doctrine-types` 3.2.1, `rector/rector` 2.8.5 |
| `hier-caller-Arr.wrap-d1` | `orchestra/sidekick` v1.2.23, `orchestra/testbench-core` v11.4.0 |
| `def-array_map-into-stubs`, `hier-callee-Arr.get-d1` | the PHP stubs of PhpStorm |

The rows that reach a file of the PhpStorm installation (the PHP stubs in
`plugins/php-impl/lib/modules/intellij.php.backend.jar`) are `shape` rows:
`def-array_map-into-stubs`, `hier-callee-Arr.get-d1` and `find-class-Uuid-libraries-scope`. An
update of PhpStorm can move a stub to another file.
| `search-text-dynamodb`, `search-text-dynamodb-strings` | `composer.lock` of the bootstrap: it has one match |
