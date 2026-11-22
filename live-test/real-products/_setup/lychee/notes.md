# lychee

- Repository: https://github.com/LycheeOrg/Lychee
- Pin: tag `v7.7.3`, commit `1002f793b018f12a768f8d8c8afe62f283d0d47f`, committed 2026-08-15
- License: MIT
- IDE: PhpStorm (port 29175)
- Languages: PHP, TypeScript and Vue 3 in `resources/js`. The pin uses Laravel v12.65.0
  (`laravel/framework` in `composer.lock`).
- PHP: `composer.json` needs PHP 8.4 and eleven extensions. PhpStorm needs no PHP interpreter
  to index the product.
- Autoload: PSR-4. `App\` is `app/`; `autoload-dev` has `Tests\`, `Scripts\`, `PHPStan\` and
  `Database\Factories\`.

## Setup

Run `bootstrap.sh`. It needs `php` on the `PATH`, composer 2 (`composer` on the `PATH`, or
else the `composer.phar` of the mise tool `github:composer/composer`), and `node` and `npm`. It
runs `composer install` and `npm ci` in the checkout, and it writes `.idea/modules.xml`,
`.idea/lychee.iml` and `.idea/php.xml` when they are absent. The product ignores `/.idea`,
`/vendor` and `node_modules` in its own `.gitignore`.

- `composer.lock` is committed, and `composer install` never writes it. Four packages come
  from the VCS repositories of `composer.json` (`LycheeOrg/phpstan-lychee`, `php-exif`,
  `log-viewer` and `verify`); the lock pins each one to a commit. `--ignore-platform-reqs`
  skips the check of the PHP version and the extensions of the machine. `--no-scripts` runs no
  script of the product (the scripts call `artisan`), and `--no-plugins` loads no composer
  plugin. The packages go to `vendor/` in the checkout: 253 packages.
- `package-lock.json` is committed, and `npm ci --ignore-scripts` never writes it. The packages
  go to `node_modules/` in the checkout. The product names no Node.js version.
- PhpStorm restores a project at its start only when the folder has IDE project files.
- The module file is the model that PhpStorm 2026.3 writes at the first open of the folder:
  `app` is a source root; `database/factories`, `phpstan`, `scripts` and `tests` are test roots
  (`tests` two times, one time with no package prefix); `vendor/composer` and the folder of
  each composer package are excluded, except `vendor/jetbrains/phpstorm-stubs`; and six folders
  of the Laravel framework are excluded (`bootstrap/cache`, `storage/app`, `storage/bootstrap`,
  `storage/debugbar`, `storage/framework`, `storage/tmp`). The bootstrap reads the packages
  from `vendor/composer/installed.json`. A restore adds no exclusion by itself.
- At each open, the composer sync of PhpStorm puts the package folders on the PHP include path
  (`IncludePathApplier` in `idea.log`), so they are library roots. It removes
  `vendor/jetbrains/phpstorm-stubs` from the include path, and the module does not exclude that
  folder.
- `php.xml` holds the language level 8.4, the level that PhpStorm uses after the first open,
  and turns off the check of the used language features. At the first open that check sets 8.5
  ("Language level was set to 8.5 based on the features used in the project"). At a later
  open, with the check turned off, the composer sync of PhpStorm sets the level from
  `composer.json` (`"php": "^8.4"`), and the status bar shows "PHP: 8.4". The rows give the same
  results with 8.5 and with 8.4 in `php.xml`.
- PhpStorm adds `node_modules/` as a library root by itself at each open.
- At each open, PhpStorm evaluates `vite.config.ts` with Node.js (`WebBundlerConfigExecutor` in
  `idea.log`). The Nuxt UI plugin of that file then writes `components.d.ts` in the checkout
  root and `node_modules/.nuxt-ui/` and `node_modules/.vite-temp/`. The product ignores these
  paths. The bootstrap runs no part of the product, so before the first open these files are
  absent.
- At each open, PhpStorm also runs `vendor/bin/phpstan` and PHP CS Fixer of the checkout with
  the PHP of the machine. With a PHP older than 8.4 both fail and show a notification. The
  index does not depend on them.
- The checkout has many folders (`vendor/` and `node_modules/`). When the inotify watch limit of
  the machine is too low, PhpStorm cannot watch the checkout ("External file changes sync might
  be slow"), and it sees a change from outside the IDE only at its next refresh. The rows do not
  change files, so they do not depend on it.

## Measured values

PhpStorm 2026.3 (PS-263.7307.215), plugin 2.1.1-dev.23, `-Xmx2048m`, 2026-11-22.

| Item | Value |
|---|---|
| Checkout with its dependencies | 1,000 MB: 164 MB, `vendor/` 392 MB, `node_modules/` 445 MB |
| First `composer install`, with the downloads | 4 min 45 s |
| Bootstrap, first run with the packages present (`npm ci` runs again, no stamp yet) | 19 s |
| Bootstrap, second run | 11 s |
| First open: switch, then ready | 27 s, 125 s |
| First indexing (four passes: 5,462, 24,251, 6,806 and 7,163 files) | 126 s |
| Next open after a switch to phpunit: switch, then ready | 17 s, 0 s |
| Resident memory, `php` fixture plus `lychee`, after the runs | 4,474 MB |
| Used heap after a full collection | 616 MB (limit 2,048 MB) |
| One run of the product rows, warm, then after a restart | 15 s, 57 s |
| `ide_call_hierarchy` callers of `ConfigManager::getValueAsBool`, `maxDepth: 2` (held row `hier-caller-getValueAsBool-d2`, above the request limit of 60 s) | 85 s; 113 + 87 nodes, cut at the node budget of 200 |

## Rows that depend on a library

| Row | Library (lockfile) |
|---|---|
| `canary-def-FormRequest-into-dependency`, `def-DB.table-via-facade` | `laravel/framework` v12.65.0 (`composer.lock`) |
| `canary-def-axios.get-into-node-modules` | `axios` 1.19.0 (`package-lock.json`) |
| `find-class-UrlGenerator-libraries-scope` | `laravel/framework` v12.65.0, `symfony/routing` v7.4.15, `rector/rector` 2.6.1 (its scoped copy of `illuminate/contracts`) |
| `find-file-FormRequest.php-libraries-scope` | `laravel/framework` v12.65.0, `dedoc/scramble` v0.13.39, `larastan/larastan` v3.10.0, `spatie/laravel-data` 4.23.0 |
| `super-FlushOldOrdersTest.setUp`, `hier-super-FlushOldOrdersTest` | `laravel/framework` v12.65.0, `phpunit/phpunit` 11.5.56 |
