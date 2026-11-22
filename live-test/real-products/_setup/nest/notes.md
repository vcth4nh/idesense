# nest

- Repository: https://github.com/nestjs/nest
- Pin: tag `v12.0.0`, commit `6494a6c27400547ea6cd9b78da07b2e9c2547ca0`, committed 2026-08-27
  ("chore(release): publish v12.0.0 release"). The repository also has a branch with the name
  `v12.0.0` at another commit. The pin is the tag.
- License: MIT (`LICENSE`)
- IDE: WebStorm (port 29173), fixture languages JavaScript and TypeScript
- Node.js: `engines.node` is `>= 20` in `package.json`. The bootstrap ran with Node.js 24.16.0
  and npm 11.13.0.
- Languages: TypeScript with decorators and dependency injection. The root `package.json`
  declares the npm workspaces `packages/*`: nine packages (`common`, `core`, `microservices`,
  `platform-express`, `platform-fastify`, `platform-socket.io`, `platform-ws`, `testing`,
  `websockets`). `lerna.json` has the version 12.0.0, each package has 12.0.0, and the root
  `package.json` has the version 11.1.10 and the name `@nestjs/core`, the same name as
  `packages/core`. This is the state of the pin.
- `tsconfig.json` maps each package name (`@nestjs/common`, `@nestjs/common/*` and the others)
  to the sources in `packages/`, and it includes `packages/` and `integration/`. `integration/`
  holds 583 files in 25 folders, with 30 `tsconfig.json` files. `sample/` holds 702 files in
  36 folders with 40 applications, each with its own `package.json`, outside the root
  `tsconfig.json`. The JavaScript files are 11 small files (`sample/09-babel-example`,
  `sample/08-webpack`, `sample/34-hmr-esm`, `scripts/`, `gulpfile.mjs`); the largest has 1.7 KB.
- `packages/microservices/external/` holds type declarations of other libraries (for example
  `kafka.interface.ts`, a copy of the types of kafkajs, 34 KB).
- 65 files have the name `app.module.ts`, and 73 classes have the name `AppModule`.

## Setup

Run `bootstrap.sh`. It needs `node` 20 or later and `npm` on the `PATH`.

- `package-lock.json` is committed (lockfile version 3), and `npm ci` never writes it. The
  lockfile has peer dependency conflicts: `graphql` 17.0.2 is outside the peer range of
  `@apollo/server` 5.5.1. A plain `npm ci` stops with `ERESOLVE`. The bootstrap uses
  `npm ci --legacy-peer-deps`, the install command of `CONTRIBUTING.md` of the product.
- `--ignore-scripts` runs no script of the product (`postinstall`, `prepare`) and no install
  script of a package. The packages go to `node_modules/` in the checkout (1,597 packages,
  631 MB). npm links each workspace package into `node_modules/@nestjs/` (a symbolic link to
  `packages/<name>`).
- WebStorm restores a project at its start only when the folder has IDE project files. The
  module file holds what WebStorm itself writes at the first open of this folder: one content
  root with no source folder, no test folder and no excluded folder. Evidence: on 2026-11-22 a
  WebStorm 2026.3 (WS-263.7307.202) with a window opened a copy of the pin with no `.idea`
  folder, and its module file and `modules.xml` were equal to the files of the bootstrap
  (except the module name, which is the folder name). WebStorm adds `node_modules/` as a
  library root by itself at each open.
- So the project has no source root and no test root. `ide_find_usages` and `ide_find_file`
  with `project_production_files` or `project_test_files` give `scope_matches_no_files`.
- Times: the first bootstrap run took 22.6 s (the `npm ci`). A second run took 0.05 s and
  changed no file.

## Import

Fleet WebStorm 2026.3 (WS-263.7307.202), plugin 2.1.1-dev.31, 2026-11-22.

| Value | Measured |
|---|---|
| Switch time, first open | 11 s; ready 0 s |
| `node_modules` library root added | 5 s after the open of the project (`NodeModulesDirectoryManager - Contributed`, 8,272 files) |
| First indexing | 2,614 project files and 8,280 files with the library root; dumb mode ended 25 s after the open of the project |
| First TypeScript request | the TypeScript service starts, then a dumb pass of about 3 s follows |
| Later open (after a switch to uptime-kuma) | switch 11 s; ready 0 s |
| Resident memory after the first open | 3.07 GiB; 2.64 GiB after a full collection |
| Used heap after a full collection | 316 MB (`jcmd GC.run`, `GC.heap_info`; limit 2,048 MB) |
| Checkout size | 16 MB, 646 MB with `node_modules/` |
| One run of all rows | 5 s to 14 s; 35 s at once after a project switch |

The harness reports "ready 0s" before the library root and the first dumb pass come. A direct
tool call during the dumb pass of the TypeScript service got `index_not_ready`. A harness run
13 s after a project switch passed the canary rows, and no row got `index_not_ready`.

## Library files in the expected rows

All dependency files of the rows are in `node_modules/` of the checkout. An entry of
`package-lock.json` decides each of them.

| Row | File | Lock entry |
|---|---|---|
| `canary-def-Observable-into-dependency` | `node_modules/rxjs/dist/types/internal/Observable.d.ts` | `packages["node_modules/rxjs"]`, version 7.8.2 |
| `def-iterate-into-dependency`, `find-file-iterate.d.ts-libraries-scope` | `node_modules/iterare/lib/iterate.d.ts` | `packages["node_modules/iterare"]`, version 1.2.1 |
| `def-querystringParse-alias-into-dependency` | `node_modules/fast-querystring/lib/index.d.ts` | `packages["node_modules/fast-querystring"]`, version 1.1.2 |
| `find-class-Kafka-libraries-scope` | `node_modules/kafkajs/types/index.d.ts` | `packages["node_modules/kafkajs"]`, version 2.2.4 |
