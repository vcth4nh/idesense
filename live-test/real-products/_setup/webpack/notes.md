# webpack

- Repository: https://github.com/webpack/webpack
- Pin: tag `v5.112.2`, commit `e95a7f2764281318c038e9384371797dfef0e48a`, committed 2026-10-23.
- License: MIT (`LICENSE`)
- IDE: WebStorm (port 29173), fixture languages JavaScript and TypeScript
- Node.js: `engines.node` is `>=10.13.0` in `package.json`. The field `packageManager` names
  `yarn@1.22.22` with its hash. The bootstrap ran with Node.js 24.16.0 and yarn 1.22.22 through
  corepack.
- The checkout has 21,650 tracked files: 17,178 JavaScript files, 70 TypeScript files and 731
  JSON files. 19,770 of them are below `test/`.
- The sources in `lib/` are CommonJS (`require`, `module.exports`) with JSDoc types. The JSDoc
  types name other modules with `@import` tags, `@typedef {import("...")}` and
  `import("...")` types. Two open defects of the tools concern these types: #323
  (`ide_find_definition` at a type name in a JSDoc comment) and #324 (a JSDoc `@typedef` is a
  declaration with no name for the tools).
- `types.d.ts` (1.0 MB) is a generated declaration file of the public API: its header says
  "This file was automatically generated". `package.json` names it in `types`. It declares
  most classes of `lib/` one more time. So a class name often has two or more declarations
  (#269).
- `test/` and `examples/` have committed `node_modules/` folders (1,022 and 54 tracked
  files). They are test data. The install does not touch them.
- `.gitmodules` names 8 submodules below `test/external/`. The bootstrap does not initialize
  them, and no row needs them.
- 68 tracked files are above 100 KB, for example `types.d.ts`, `lib/javascript/syntax-printer.js`
  (1.7 MB) and test data of several MB. `ide_file_structure` on such a file can stop the IDE
  (#177). No row calls it on a file above 100 KB.

## Setup

Run `bootstrap.sh`. It needs `node` 10.13 or later with `corepack` on the `PATH`. It needs no
global install of yarn and no `corepack enable`.

- `yarn.lock` is committed (1,375 packages). `--frozen-lockfile` refuses each change of it.
- `--ignore-scripts` runs no script of the product (the product has `prepare`) and no install
  script of a package.
- yarn 1 keeps each package in its cache and copies it into `node_modules/` of the checkout.
  The install writes these folders outside the checkout:

  | Folder | Size | Content |
  |---|---|---|
  | `~/.cache/yarn/v6` | 889 MB | the cache of the packages |
  | `~/.cache/node/corepack/v1/yarn` | 5.2 MB | yarn itself (corepack) |

  `YARN_DISABLE_SELF_UPDATE_CHECK` keeps yarn from writing `~/.yarnrc`.
- The checkout has 149 MB, and 754 MB with `node_modules/` (882 top-level packages). The new
  data of the first install was about 1.49 GB.
- WebStorm restores a project at its start only when the folder has IDE project files. The
  module file holds what WebStorm itself writes at the first open of this folder: one content
  root with no source folder, no test folder and no excluded folder. Evidence: on 2026-11-22 a
  WebStorm 2026.3 (WS-263.7307.202) with a window opened a copy of the pin with no `.idea`
  folder. Its module file and `modules.xml` were equal to the files of the bootstrap, except
  the module name (the folder name) and the final newline. WebStorm adds `node_modules/` as a
  library root by itself at each open.
- So the project has no source root and no test root. `ide_find_usages` and `ide_find_file`
  with `project_production_files` or `project_test_files` give `scope_matches_no_files`.
- Times: the first bootstrap run took 30.9 s. A second run took 0.26 s and changed no file. A
  third run, after the IDE had the product open, took 0.33 s and changed no tracked file.

## Import

Fleet WebStorm 2026.3 (WS-263.7307.202), plugin 2.1.1-dev.31, 2026-11-22.

| Value | Measured |
|---|---|
| Switch time, first open | 11 s; ready 0 s |
| `node_modules` library root added | 12 s after the IDE start (`NodeModulesDirectoryManager`, 13,683 files); it grew to 14,253 files at 56 s |
| First index build | 18.6 s for 20,283 files of the project, then 11.3 s for the 13,683 files of `node_modules`; dumb mode ended 57 s after the IDE start |
| Resident memory after the first open | 3.90 GiB; 3.15 GiB after a full collection |
| Used heap after a full collection | 337 MB (`jcmd GC.run`, `GC.heap_info`; limit 2,048 MB) |
| Resident memory after the stability runs | 4.31 GiB, 38 min after the start |
| Low memory signals | none in the first 12 min; then 15 in 26 min (`LowMemoryWatcher` in `idea.log`): 12 while call hierarchies at depth 2 ran, 3 during three runs of the rows |
| One run of all rows | 9 s to 14 s |

The harness reports "ready 0s" before the library root and the dumb pass of the index build
come. Wait for the quiet state before the first row.

Heap: the fleet WebStorm ran with its heap limit of 2,048 MB (`-Xmx2048m`), with `webpack` and
the fixture projects `javascript` and `typescript` open. The 15 low memory signals came with no
failed call, and the used heap after a full collection was 337 MB. The heap limit was not
changed for this product.

The values above are from plugin 2.1.1-dev.31. The bless and the two verify runs ran on plugin
2.1.1-dev.35 (2026-11-23), after a second open of the product (switch 11 s, `node_modules`
library root with 14,253 files). The first run of all rows after this open took 59 s, and the
next runs took 8 s to 17 s. The 4 runs with the final rows gave the same result for each row.

## Results that change between runs

`hier-caller-getCompilationHooks-bysymbol` (parked with #269) gave 34 callers in the runs 1 and
2, and 35 in the runs 3 and 4, in one session of the fleet WebStorm. The 35th caller is
`lib/schemes/FileUriPlugin.js:24`, which takes `NormalModule` from `require("..")`. The position
row `hier-caller-getCompilationHooks-d1` gave 36 callers, with this file, in all 4 runs. The cause
is not tested. On plugin 2.1.1-dev.35 the parked row gave 35 callers in each run.

## Library files in the expected rows

| Row | File | Lock entry |
|---|---|---|
| `canary-def-SyncHook-into-tapable`, `def-tap-into-tapable`, `find-file-tapable.d.ts-libraries-scope` | `node_modules/tapable/tapable.d.ts` | `tapable@2.3.3` (the only version of tapable in the lockfile and in `node_modules/`) |

## Call hierarchy times

The callers of `NormalModule.getCompilationHooks` (`lib/module/NormalModule.js:742`) at depth
2 took 46.6 s at the first call, and the callers of `getRuntimeKey` (`lib/util/runtime.js:93`)
at depth 2 took 38.1 s. At depth 1 they took 0.66 s (36 callers) and 0.12 s (10 callers). The
depth 2 row uses `Dependency.setLocWithIndex` (`lib/graph/Dependency.js:335`) instead: 5.7 s
at its first call, cut at 200 nodes.
