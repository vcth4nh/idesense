# backstage

- Repository: https://github.com/backstage/backstage
- Pin: tag `v1.54.0`, commit `a4bdc49ed664661bc69fe42bfaebcf24dc96e6b3`, committed 2026-08-18.
- License: Apache-2.0 (`LICENSE`)
- IDE: WebStorm (port 29173), fixture languages JavaScript and TypeScript
- Node.js: `engines.node` is `22 || 24` in `package.json`, and `.npmrc` sets
  `engine-strict=true`. The field `packageManager` names `yarn@4.8.1`. The bootstrap ran with
  Node.js 24.16.0 and the committed yarn release `.yarn/releases/yarn-4.8.1.cjs`.
- The checkout has 11,948 tracked files: 5,440 TypeScript files, 1,802 TSX files, 423
  JavaScript files, 684 YAML files, 1,841 Markdown files and 125 Handlebars templates. 5,633
  files are below `plugins/`, 3,987 below `packages/`, 875 below `docs/` and 865 below
  `microsite/`. 1,717 files are tests (`*.test.ts`, `*.test.tsx`).
- The workspaces of `package.json` are `packages/*` and `plugins/*`: 228 packages (70 below
  `packages/`, 158 below `plugins/`). 216 of them name `src/index.ts` in `main` and `types`. So
  an import of a workspace package by its name (`@backstage/...`) resolves to the TypeScript
  sources, not to a built file.
- One root `tsconfig.json` covers the packages: its `include` names `packages/*/src`,
  `packages/*/config.d.ts`, `plugins/*/src`, `plugins/*/config.d.ts`, `plugins/*/dev` and
  `plugins/*/migrations`. It extends `@backstage/cli/config/tsconfig.json`, a file of the
  workspace package `packages/cli`. Seven more `tsconfig.json` files exist: `docs-ui/`,
  `microsite/`, `scripts/`, `packages/cli/config/`, `workspaces/ui/` and two templates below
  `packages/create-app/templates/`. `workspaces/ui/` has its own `yarn.lock`; the bootstrap does
  not install it.
- 557 tracked Markdown files are reports: 307 API reports (`*.api.md`, TypeScript in code
  fences), 221 `knip-report.md`, 17 `cli-report.md` and 12 SQL reports (`*.sql.md`).
- 81 `config.d.ts` files each declare `export interface Config`: the configuration schema of
  one package. With the type aliases `Config` of `packages/config/src/types.ts` and
  `plugins/auth-backend/src/identity/StaticTokenIssuer.ts`, 83 declarations have the name
  `Config` (#269 for a row that names the symbol).
- 36 tracked files are below folders with the name `node_modules` (test fixtures of
  `packages/cli-module-build`, `packages/backend-dynamic-feature-service` and
  `packages/eslint-plugin`). WebStorm associates each such folder with its parent folder, as it
  does with the `node_modules/` folders of the install (`NodeModulesDirectoryManager - Associate`
  in `idea.log`). A search in the project files does not find them: `ide_find_file` with
  `package.json` gives 287 files, 264 of the 271 tracked `package.json` files and the 23
  `package.json.hbs` templates. The 7 other `package.json` files are in such folders.
- The product tracks the instruction files `AGENTS.md`, `.claude/CLAUDE.md` (a symbolic link),
  `.github/copilot-instructions.md` and `plugins/catalog-backend/CLAUDE.md`. They are product
  content.
- 359 tracked files are above 100 KB. Code and JSON among them: the three yarn releases
  (`.yarn/releases/yarn-4.8.1.cjs`, and `yarn-4.13.0.cjs` in two templates below
  `packages/create-app/templates/`), `plugins/bitbucket-cloud-common/bitbucket-cloud.oas.json`
  (1.28 MB) and five JSON fixtures below `plugins/kubernetes*/src/__fixtures__/` (116 KB to
  150 KB). The others are Markdown files. `ide_file_structure` on such a file can stop the IDE
  (#177). No row calls it on a file above 100 KB.

## Setup

Run `bootstrap.sh`. It needs `node` 22 or 24 on the `PATH`. It needs no global install of yarn,
no corepack and no network access for yarn itself: Node.js runs the committed release
`.yarn/releases/yarn-4.8.1.cjs` (the `yarnPath` of `.yarnrc.yml`).

- `yarn.lock` is committed (4,126 resolutions: 3,884 npm packages, 229 workspaces, 11 patches,
  2 links). `--immutable` refuses each change of it. `.yarn/patches/` has 6 patch files.
- No script of the product may run. `package.json` has `postinstall` (`husky || true`) and
  `prepare` (`husky`). A run of husky writes below `.husky/` and sets `core.hooksPath` in the git
  configuration of the checkout. `--mode=skip-build` runs no build step, also not the
  `postinstall` of the root workspace, and `YARN_ENABLE_SCRIPTS=false` turns the scripts of the
  packages off. The log of the install has a fetch step and a link step and no build step. The
  bootstrap fails when `core.hooksPath` has a value or `.husky/_` exists.
- `YARN_ENABLE_TELEMETRY=0` sends no telemetry.
- `.yarnrc.yml` sets `nodeLinker: node-modules` and `enableGlobalCache: true`. yarn keeps each
  package in the cache of its global folder and copies it into `node_modules/` of the checkout.
  The install writes these folders outside the checkout:

  | Folder | Size | Content |
  |---|---|---|
  | `~/.yarn/berry/cache` | 413 MB | the cache of the packages (3,738 zip files) |
  | `~/.yarn/berry/index` | 1.1 MB | the index of the cache |

  It writes no `~/.yarnrc.yml`.
- yarn links each workspace package into `node_modules/` with a symbolic link to its folder:
  212 links below `node_modules/@backstage/`, 228 links into `packages/` and `plugins/` in all.
- The checkout has 271 MB of tracked files, and 2.9 GB on the disk with `node_modules/` (root
  `node_modules/` 2.5 GB with 1,978 unscoped and 1,314 scoped top-level packages, and 25 nested
  `node_modules/` folders with 60 MB). The install also writes `.yarn/install-state.gz`
  (7 MB). The new data of the first install was 3.01 GB. yarn reported "3738 packages were
  added to the project (+ 405.39 MiB)".
- WebStorm restores a project at its start only when the folder has IDE project files. The
  module file holds what WebStorm itself writes at the first open of this folder: one content
  root with no source folder, no test folder and no excluded folder. Evidence: on 2026-11-23 a
  WebStorm 2026.3 (WS-263.7307.202) with a window opened a copy of the pin with no `.idea`
  folder. Its module file and `modules.xml` were equal to the files of the bootstrap, except
  the module name (the folder name) and the final newline. WebStorm adds `node_modules/` as a
  library root by itself at each open. The product ignores `.idea/` in its `.gitignore`.
- Times: the first bootstrap run took 105.3 s (fetch step 31 s, link step 69 s). A second run
  took 0.38 s and changed no file.

## Import

The fleet WebStorm 2026.3 (WS-263.7307.202, `-Xmx2048m`) with plugin 2.1.1-dev.36 opened the
product two times with `--open-product backstage` (2026-11-23). The rows "Switch" and "First
run" give the values of the two opens. The other values are of the first open.

| Value | Measured |
|---|---|
| Switch | switch 11 s and 16 s, ready 0 s (output of `--open-product`) |
| Scan of the project files | 12,226 files (11,352 for indexing), 27 s after the IDE start |
| `node_modules` library root added | 22 s after the IDE start (`NodeModulesDirectoryManager - Contributed`, `allIncludedFileCount` 284,404) |
| Scan of `node_modules` | 50,992 files (50,984 for indexing), 31 s after the IDE start |
| First index build | "Unindexed files update took 54496ms"; dumb mode ended 85 s after the IDE start, then one more dumb pass of 1.3 s (204 files, "update node_modules libraries (count=31)") |
| Resident memory of the IDE | 4.26 GB; 3.60 GB after a full collection |
| Used heap after a full collection | 414 MB of 2,048 MB (1,857 MB before it) |
| Low memory signals | 0 |
| inotify watches of `fsnotifier` | 32,342; no inotify warning in `idea.log` |
| TypeScript service of the product (Node.js, `--max_old_space_size=3072`) | 3.16 GB resident memory after four runs of all rows |
| First run of all rows after the open | 87 s (77 rows) and 90 s (71 rows); the TypeScript service loads the project (see below) |
| Later runs of all rows | 12 s to 14 s |
| `bootstrap.sh` after the first and the second open | 0.41 s and 0.36 s; no change of a tracked file; module file and `modules.xml` unchanged; no `core.hooksPath`, no `.husky/_` |

A WebStorm 2026.3 (WS-263.7307.202) with a window and plugin 2.1.1-dev.35 opened a copy of the
pin with `node_modules/` (2026-11-23):

| Value | Measured |
|---|---|
| Scan of the project files | 12,224 files (11,663 for indexing), 39 s after the IDE start |
| `node_modules` library root added | 33 s after the IDE start (`NodeModulesDirectoryManager - Contributed`, `allIncludedFileCount` 284,404); 285,947 at 121 s |
| Scan of `node_modules` | 50,992 files, 44 s after the IDE start |
| First index build | "Unindexed files update took 75421ms"; dumb mode ended 119 s after the IDE start, then one more dumb pass of 3 s (204 files) |
| Low memory signals | 1 during the first index build |

## Workspace packages and their symbolic links

The search tools and their windows show each file of a workspace package one time, with its
real path below `packages/` or `plugins/`, and no path through `node_modules/@backstage/`.
Evidence (WebStorm with a window, plugin 2.1.1-dev.35): Go to File `GithubEventRouter.ts` gave
4 files in the scope Project Files and in All Places; Go to Class `GithubEventRouter` gave 1
class; Go to Declaration at `SubTopicEventRouter` in `GithubEventRouter.ts` opened
`plugins/events-node/src/api/SubTopicEventRouter.ts` (the package
`@backstage/plugin-events-node`). The tools gave the same files.

The call hierarchy is different. The Call Hierarchy window (scope "All", the default) shows each
caller in a workspace package two times: one time with the real path, and one time with the
path through the link, for example
`node_modules/@backstage/backend-defaults/src/lib/escapeRegExp.test.ts`. `ide_call_hierarchy`
gives the same two nodes for each caller: the callers of `escapeRegExp` are 38 = 2 x 19.
`ide_find_usages` gives each usage one time (20 for `escapeRegExp`). Evidence: WebStorm with a
window and plugin 2.1.1-dev.36, the window of the callers of `escapeRegExp`; a jump from the
second node of `escapeRegExp.test.ts` opened the path through the link.

## TypeScript service

WebStorm starts the TypeScript service of the product (the `typescript` 5.7.3 of
`node_modules/`) at the first request that needs it. The service then loads the root
`tsconfig.json` ("Loading TypeScript project" in `idea.log`). A request during the load waits
for at most 20 s; then `JSLanguageServiceQueue` logs SEVERE "Failed to process command ... -
timed out". After each of three opens, the first row run met this limit: the first row,
the callees of `determineDestinationTopic` (now the canary
`canary-hier-callee-determineDestinationTopic-d1`), gave `internal_error`. A later direct call
of the same row took 0.04 s. A WebStorm with a window met the same limit with no plugin call.
The canary gate takes the error: in a `--product backstage` run that opened the product itself,
the canary first gave `internal_error`, the harness asked the canary rows again, and the run
passed (57 passed, 0 failed, 14 parked, 119 s).
The details are in [GROUND-TRUTH.md](../../_snapshots/backstage/GROUND-TRUTH.md), "The
TypeScript service".

## Scopes

The project has no source folder and no test folder. So `ide_find_usages` and `ide_find_file`
give `scope_matches_no_files` for the scopes `project_production_files` and
`project_test_files`. `ide_call_hierarchy` passes the scope to the IDE: the callers of
`escapeRegExp` are 0 in the scope `production`, 34 in the scope `test` (the 17 callers in
`escapeRegExp.test.ts`, each one two times) and 38 in the scope `this_module`. Which rule of
the IDE makes `escapeRegExp.test.ts` a test file: not read.

## Library files in the expected rows

| Row | File | Lock entry |
|---|---|---|
| `canary-def-Logger-into-winston` | `node_modules/winston/index.d.ts` | `winston@3.19.0` (the only version of winston in the lockfile and in `node_modules/`) |
