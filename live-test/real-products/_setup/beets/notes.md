# beets

- Repository: https://github.com/beetbox/beets
- Pin: tag `v2.14.1`, commit `00724b78377d06151ac6c672f3b2ba23b2688bfa`, committed 2026-09-17
- License: MIT
- IDE: PyCharm (port 29172)
- Python: `requires-python = ">=3.10,<3.15"`. The bootstrap uses Python 3.12.
- Layout: flat. `beets` is a package, `beetsplug` is a namespace package, `test` is a package.

## Setup

Run `bootstrap.sh`. It needs `uv` on the `PATH`. It runs `uv sync --locked --python 3.12` in
the checkout, and it writes `.idea/modules.xml` and `.idea/beets.iml` when they are absent.
The product ignores `.idea` and `.venv` in its own `.gitignore`.

- `uv.lock` is committed. `--locked` stops when the lock is not up to date and never writes
  it. The lock has markers for the Python version, so the bootstrap fixes the version: uv
  takes an installed Python 3.12 or downloads one. The environment is `.venv` in the checkout
  with the default group `dev` and no extras.
- PyCharm restores a project at its start only when the folder has IDE project files.
- The module file has `external.system.id="pyproject.toml"`. PyCharm 2026.2 rebuilds the
  module from `pyproject.toml` at each open ("Rebuild project model based on pyproject.toml").
  Without the attribute, the rebuild writes the source roots again with no `isTestSource`,
  and at the next start `test` is a plain source root: `WorkspaceToolsKt.updateModule` creates
  the roots again with no Java root properties when the content root has another entity
  source, and `ModuleImlFileEntitiesSerializer.saveSourceRoot` writes `isTestSource` only for a
  root with Java root properties (bytecode, 262.8665). With the attribute, the module and its
  content root have the pyproject entity source, and the rebuild keeps the roots.
- The module file names `inheritedJdk`. At the first open PyCharm makes a uv SDK from `.venv`
  and gives it to the module (`autoConfigureSdkIfNeeded` of the SDK configurator). PyCharm
  writes this SDK to `options/jdk.table.xml` itself, with the path of `.venv` as its name, and
  rewrites the `orderEntry` of the module file. The bootstrap writes no option file.
- On a fresh machine, PyCharm makes this interpreter entry by itself at the first open of the
  product. No manual step is necessary. The name of the entry holds the absolute path of the
  `.venv` of the checkout, so each checkout gets its own entry.
- Model: the repository root is the source root, `test` is the test root, `.venv` is
  excluded. PyCharm gives a module the qualified name from the nearest root, so a test module
  has a name with no `test.` prefix (`test_util.HelperTest`). Without the written model,
  PyCharm makes one module with no source root and no test root: the names then have the
  prefix, and the usage scope `project_test_files` matches no file. The design keeps the test
  root: the canary scope pair needs it, and the pair is worth more than the prefix.

Times on 2026-11-12: the first bootstrap ran in 10 s, a second run takes 1 s.

## Library files in the expected rows

A library file keeps only its base name in a snapshot, and loses its line.

| File | Decided by |
|---|---|
| `.venv/lib/python3.12/site-packages/confuse/core.py` | `uv.lock` (confuse 2.2.1) and `--python 3.12` |
| `.venv/lib/python3.12/site-packages/mediafile/__init__.py` | `uv.lock` (mediafile 0.17.0) and `--python 3.12` |
| `builtins.pyi`, `abc.pyi`, `re.pyi` | the typeshed that the PyCharm build bundles |
| `lib.es2025.iterator.d.ts` | the TypeScript library that the PyCharm build bundles |

No row names a file of the standard library of the interpreter: that file depends on the
Python 3.12 that uv takes on the machine.

## Measured

PyCharm 2026.2 (PY-262.8665.369), `-Xmx2048m`, plugin 2.1.1-dev.12, 2026-11-12.

| Item | Value |
|---|---|
| Switch: stop PyCharm, mark the projects, start, all projects listed | 11 s |
| Ready after the switch, first open | 30 s |
| First indexing: 500 files, then 16,351 files | 32 s from project open to smart mode |
| Python fixture rows while `beets` is open | 122 passed |
| Resident memory of PyCharm, `python` fixture plus `beets` | 2593 MB |
| Used heap after a full collection, after the open | 242 MB |

The used heap stays far below 1200 MB (60% of the limit), so PyCharm keeps `-Xmx2048m`.

Facts about the switch:

- A next open takes 11 s for the switch and 0 s to readiness. PyCharm scans the project again
  and indexes about 1,700 files in 17 s.
- At the first open, PyCharm reports smart mode before it has set the SDK. The canary gate
  covers it: after a switch it tries the canary rows again until the readiness time is used.
- On a next open, the module file already names the SDK, and run 4 of the stability check
  at once after the switch gave the same rows as before the switch.

## Import check

Done on 2026-11-12 with plugin 2.1.1-dev.12. The product is accepted.

| Call | Result |
|---|---|
| `ide_find_class`, query `BeetsPlugin` | the class `BeetsPlugin`, `beets/plugins.py:89` |
| `ide_find_definition`, `beets/__init__.py:24:33` | `LazyConfig` in `confuse/core.py` of `.venv` (confuse 2.2.1) |
| `ide_find_usages`, `beets/plugins.py:89:7`, `pageSize` 100 | 100 usages, `totalCollected` 173, `hasMore` true |
| `ide_type_hierarchy`, `beets/plugins.py:89:7`, subtypes | 103 subtypes |
| `ide_file_structure`, `beets/plugins.py` | a structure of 105 lines |

Comparison with PyCharm itself. A second PyCharm with a window opened a copy of the pin that
had no `.idea` folder, so that PyCharm made the project model by itself:

- The model of PyCharm has one module with `external.system.id="pyproject.toml"`, the uv SDK
  of `.venv`, `.venv` excluded, and no source root and no test root.
- 14 tool calls on both projects: 9 give the same result. 3 differ only in the `test.` prefix
  of the test modules, 1 is a cut page of `ide_search_text`, and the test scope gives
  `scope_matches_no_files` on the model of PyCharm.
- Go to Implementation on `BeetsPlugin` shows "Choose Implementation of ... (103 found)". The
  tool gives 103.
- Find Usages on `BeetsPlugin` shows 172 usages and a separate group of 1 dynamic usage. The
  tool gives 173, the same list.
- Go to Declaration on `plugins` at `beetsplug/playlist.py:75:29` does nothing. The tool gives
  the error "Could not resolve symbol definition".

Project model facts that the probe rows rely on:

- `test` is a test root and the repository root is a source root, so the usage scopes
  `project_production_files` and `project_test_files` split the usages of `path_as_posix`
  into 8 production and 4 test usages (the canary pair).
- A definition into a dependency goes to `.venv` in the checkout, a project file. `uv.lock`
  and `--python 3.12` decide the file.
- The Python outline shows the parameter lists with their default values and the base lists
  of the classes. Only the structure rows of files with no default value are `exact` rows.
- `ide_file_structure` on `beetsplug/web/static/jquery.js` gives no answer and leaves the walk
  at work in the IDE. No row has this file (#177).
- A local class gets the qualified name of the function that contains it, and a class
  attribute gets the name of its class (#176). The 5 rows that show it are parked.
- `ide_find_definition` on `_.map` in `beetsplug/web/static/beets.js` gives only the first of
  the declarations that "Choose Declaration" lists (#178). Its row is parked.
