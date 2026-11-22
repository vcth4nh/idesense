# django

- Repository: https://github.com/django/django
- Pin: tag `6.1.2`, commit `2212534bae393714e1e51db2341d4fd5545e19f6`, committed 2026-10-06
- License: BSD-3-Clause (`LICENSE`)
- IDE: PyCharm (port 29172)
- Python: `requires-python = ">= 3.12"`. The bootstrap uses Python 3.12.
- Layout: flat. `django` is a package at the repository root. `tests` is no package: the test
  runner of Django puts it on `sys.path`, so each test folder is a top-level package
  (`admin_views`, `migrations`).
- Other languages: the JavaScript of the admin and of `gis` (`django/contrib/*/static/`), the
  QUnit tests in `js_tests`, and vendored JavaScript (`jquery`, `select2`, `xregexp`) in
  `django/contrib/admin/static/admin/js/vendor/`. Four vendored files are above 100 KB (#177).

## Setup

Run `bootstrap.sh`. It needs `uv` on the `PATH`. It makes `.venv` in the checkout with Python
3.12, installs the packages of `constraints.txt`, and writes `.idea/modules.xml` and
`.idea/Django.iml` when they are absent. The `.gitignore` of the product ignores neither
`.idea` nor `.venv`: uv writes `.venv/.gitignore`, and `.idea` stays an untracked folder of
the checkout. The harness allows untracked files.

- Upstream has no lockfile. The packages are those of the test setup of the Django docs
  (`tests/requirements/py3.txt`), without `pylibmc` and `pywatchman`: these two have no wheel
  and need a native build. The docs permit to skip such a package. The first run resolved
  them with the packages of the pin date (`--exclude-newer 2026-10-06T11:32:30Z`) and wrote
  `constraints.txt`: 52 packages. Each run installs exactly these packages with
  `uv pip sync`, from wheels only, so no code of a package runs at the install.
- PyCharm restores a project at its start only when the folder has IDE project files.
- At a first open of a copy with no `.idea` folder, PyCharm 2026.3 itself writes
  `.idea/Django.iml` (the project name of `pyproject.toml`) with
  `external.system.id="pyproject.toml"`, a source folder `src` that does not exist, `.venv`
  excluded, and the uv SDK of `.venv`. That model has no test root, and the production scope
  holds only the 4 files of `tests/i18n/sampleproject`.
- The bootstrap writes the module file in the same form, with the repository root as the
  source root and `tests` as the test root. At each open PyCharm rebuilds the module from
  `pyproject.toml` ("Rebuild project model based on pyproject.toml"). With
  `external.system.id` the rebuild keeps the roots of the file; it adds the folder `src`.
- The module file names `inheritedJdk`. At the first open PyCharm makes a uv SDK from
  `.venv` and gives it to the module. In the module file of 2026.3 the SDK name is
  `$MODULE_DIR$/.venv`; in `options/jdk.table.xml` the name is the absolute path.

## Library files in the expected rows

A file in `.venv` is below the checkout: a snapshot keeps its path and its line. A file
outside the checkout keeps only its base name in a snapshot, and loses its line.

| File | Decided by |
|---|---|
| `.venv/lib/python3.12/site-packages/asgiref/sync.py` | `constraints.txt` (asgiref 3.12.1) and `--python 3.12` |
| `.venv/lib/python3.12/site-packages/sqlparse/__init__.py` | `constraints.txt` (sqlparse 0.6.0) and `--python 3.12` |
| `builtins.pyi` | the typeshed that the PyCharm build bundles |

No row names a file of the standard library of the interpreter.

## Measured

PyCharm 2026.3 (PY-263.7307.329), `-Xmx2048m`, plugin 2.1.1-dev.23, 2026-11-22.

| Item | Value |
|---|---|
| Checkout with `.venv` (`.venv` alone: 144 MB) | 218 MB |
| Switch: stop PyCharm, mark the projects, start, all projects listed | 17 s |
| Ready after the switch, first open, as the harness reports it | 0 s |
| First indexing: 5,680 files, then 2,882 files after the SDK | 67 s from the switch command to the last smart mode |
| Python fixture rows while `django` is open | 125 passed |
| Resident memory of PyCharm, `python` fixture plus `django`, after the open | 3279 MB |
| Used heap after a full collection, after the open | 292 MB |
| Product rows: first run after an open, next runs | 56 to 70 s, 6 to 15 s |

The used heap stays far below 1200 MB (60% of the limit), so PyCharm keeps `-Xmx2048m`.

Facts about the switch:

- PyCharm goes in and out of dumb mode several times while it syncs `pyproject.toml` and adds
  the SDK. The harness takes the first smart answer as ready, so it reports 0 s. The rows meet
  no dumb mode: the canary gate and the retry of a row in dumb mode cover the time.
- A next open (after `beets`) takes 12 to 17 s for the switch, and PyCharm is smart for good
  31 s after the switch command. Run 4 of the stability check at once after the switch gave
  the same rows as before the switch.
- The machine limit of inotify watches is too low for the checkout. PyCharm logs
  `inotify_add_watch ... No space left on device` and does not watch the project folder. The
  rows do not change files, so this does not change a result.

## Import check

Done on 2026-11-22 with plugin 2.1.1-dev.23. The product is accepted.

| Call | Result |
|---|---|
| `ide_find_class`, query `QuerySet` | the class `QuerySet`, `django/db/models/query.py:364` |
| `ide_find_definition`, `django/core/handlers/asgi.py:9:50` | `sync_to_async` in `asgiref/sync.py` of `.venv`, line 645 |
| `ide_find_definition`, `django/db/backends/base/operations.py:369:39` | `split` in `sqlparse/__init__.py` of `.venv`, line 63 |
| `ide_find_usages`, `django/utils/encoding.py:233:5`, the two usage scopes | 4 production and 5 test usages |
| `ide_find_implementations`, `django/db/models/fields/__init__.py:128:7` | 122 implementations |

Comparison with PyCharm itself. A second PyCharm with a window (plugin 2.1.1-dev.22) opened a
copy of the pin:

- A copy with no `.idea` folder gets the model of PyCharm (see "Setup"). On that model the
  production scope holds 4 files, the test scope gives `scope_matches_no_files`, and the test
  import `from migrations.base import` does not resolve.
- On a copy with the bootstrap model, the tool results of the window instance equal the
  results of a PyCharm in `serverMode` for all exploration calls (order aside).
- Go to Declaration on `sync_to_async` at `django/core/handlers/asgi.py:9:50` goes to
  `asgiref/sync.py:645:5`. The tool gives the same.
- Go to Implementation on `Field` shows "Choose Implementation of Field(RegisterLookupMixin)
  (122 found)". The tool gives 122.
- Go to Declaration on `objects` at `tests/basic/tests.py:54:34` does nothing, and the
  inspection says "Unresolved attribute reference objects for class Article". The log of that
  PyCharm lists the plugin `JetBrains Ultimate` (`com.intellij.modules.ultimate`) as disabled.
  The tool gives the error "Could not resolve symbol definition".

Project model facts that the probe rows rely on:

- The repository root is a source root and `tests` is a test root, so the usage scopes split
  the usages of `filepath_to_uri` into 4 production and 5 test usages (the canary pair).
- A definition into a dependency goes to `.venv` in the checkout, a project file.
  `constraints.txt` and `--python 3.12` decide the file.
- The Python outline shows the parameter lists with their default values and the base lists
  of the classes. Only the structure rows of files with no default value are `exact` rows
  (`tests/admin_views/tests.py` is a `shape` row).

The notes on the results of the rows and the parked rows are in
[../../_snapshots/django/GROUND-TRUTH.md](../../_snapshots/django/GROUND-TRUTH.md).
