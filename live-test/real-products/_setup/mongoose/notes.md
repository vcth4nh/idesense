# mongoose

- Repository: https://github.com/Automattic/mongoose
- Pin: tag `9.10.0`, commit `396a2a674173b12d570a9dca0e919197a212bc1d`, committed 2026-09-10
- License: MIT (`LICENSE.md`)
- IDE: WebStorm (port 29173), fixture languages JavaScript and TypeScript
- Node.js: `engines.node` is `>=20.19.0` in `package.json`. The bootstrap ran with Node.js
  24.16.0 and npm 11.13.0.
- Languages: the library is CommonJS JavaScript (`lib/`, 265 files; `"type": "commonjs"`).
  `types/` holds the TypeScript declarations of the library (29 `.d.ts` files, `"types":
  "./types/index.d.ts"`), and `test/types/` holds 44 TypeScript type tests. `tsconfig.json`
  maps the module name `mongoose` to `./types/index.d.ts` (`paths`). `test/` holds the mocha
  tests in JavaScript. JavaScript has two inheritance forms: ES classes (`class CastError
  extends MongooseError`) and prototype chains (`SchemaString.prototype =
  Object.create(SchemaType.prototype)`).

## Setup

Run `bootstrap.sh`. It needs `node` 20.19 or later and `npm` on the `PATH`.

- Upstream has no lockfile: the `.npmrc` of the product sets `package-lock=false`, and its
  `.gitignore` ignores `package-lock.json`. So `package-lock.json` next to `bootstrap.sh` pins
  the dependencies (lockfile version 3, 635 packages). The first bootstrap run made it with
  `npm install --package-lock-only` on 2026-11-22. The `.npmrc` of the product also sets
  `min-release-age=2`: npm 11 turns it into `before`, the time two days before the run, so
  the lockfile has no version that was younger than two days.
- The bootstrap copies the lockfile into the checkout, where the product ignores it, and runs
  `npm ci --ignore-scripts` when the lockfile differs from the one of the last install. It runs
  no script of the product and no install script of a package. The packages go to
  `node_modules/` in the checkout (635 packages, 184 MB).
- WebStorm restores a project at its start only when the folder has IDE project files. The
  module file holds what WebStorm itself writes at the first open of this folder: one content
  root with no source folder, no test folder and no excluded folder. Evidence: on 2026-11-22 a
  WebStorm 2026.3 (WS-263.7307.202) with a window opened a copy of the pin with no `.idea`
  folder, and its `mongoose.iml` and `modules.xml` were equal to the files of the bootstrap.
  WebStorm adds `node_modules/` as a library root by itself at each open.
- So the project has no source root and no test root. `ide_find_usages` and `ide_find_file`
  with `project_production_files` or `project_test_files` give `scope_matches_no_files`.
- Times: the first bootstrap run took 29.4 s (the lockfile and the `npm ci`). A second run took
  0.03 s and changed no file.

## Import

Measured on 2026-11-22 with WebStorm 2026.3 (WS-263.7307.202) and the plugin 2.1.1-dev.23:

- The first open of the product took 11 s. WebStorm added `node_modules/` as a library root
  (`NodeModulesDirectoryManager - Contributed` in `idea.log`, 3,273 included files) 5 s after
  the open. The first indexing ended 22 s after the open. Later opens took 22 s to 27 s.
- After the first open: resident memory 2.75 GiB, used heap 302 MB after a full collection
  (`jcmd GC.run`, then `GC.heap_info`). The heap limit is 2,048 MB.
- Size: 9.9 MB without `node_modules/`, 194 MB with it.
- A run of all rows takes 4 s to 9 s, and 27 s to 35 s when it starts the TypeScript service.
- The first request that uses the TypeScript service starts it. Then WebStorm changes the roots
  of its TypeScript library ("Root changed for updating the ts library") and makes a dumb pass of
  2 s. Until the service has loaded the project of `test/types/tsconfig.json`, which extends the
  `paths` of `tsconfig.json`, the name `mongoose` in a test file does not resolve to `types/`.
  So in the first run after a project switch two canary rows can differ:
  `canary-def-Schema-ts-paths` gives the import specifier in the same file, and
  `canary-def-mpath.set-into-dependency` gets `index_not_ready` in the dumb pass
  (`canary-def-Collection-d.ts-into-dependency` is the first TypeScript request of a run). This
  occurred in the first run after each of two switches. The canary gate tries again until the
  rows match, and the next runs of the same IDE session were equal.
- No row names a file of the TypeScript standard library: a callee row first named
  `node_modules/typescript/lib/lib.es2015.core.d.ts` (the uptime-kuma notes give the reason), so
  `hier-callee-CastError.init-d1` has only callees in project files.
- Four JavaScript files of `lib/` are above 100 KB (`model.js`, `query.js`, `document.js`,
  `schema.js`), and six test files. No row calls `ide_file_structure` on one of them (#177).
  `file-structure-expressions.d.ts` calls it on `types/expressions.d.ts`, a TypeScript
  declaration file of 117 KB, and the call returns at once.

## Library files in the expected rows

All dependency files of the rows are in `node_modules/` of the checkout. An entry of
`package-lock.json` in this folder decides each of them.

| Row | File | Lock entry |
|---|---|---|
| `canary-def-Collection-d.ts-into-dependency`, `hier-super-Collection-d.ts-into-dependency`, `find-class-Collection-libraries-scope`, `find-file-mongodb.d.ts-libraries-scope` | `node_modules/mongodb/mongodb.d.ts`, `node_modules/mongodb/src/collection.ts` | `packages["node_modules/mongodb"]`, version 7.6.0 |
| `canary-def-mpath.set-into-dependency` | `node_modules/mpath/lib/index.js` | `packages["node_modules/mpath"]`, version 0.9.0 |
| `def-BSON-into-dependency` | `node_modules/bson/bson.d.ts` | `packages["node_modules/bson"]`, version 7.3.4 |
| `def-Kareem-into-dependency` | `node_modules/kareem/index.d.ts` | `packages["node_modules/kareem"]`, version 3.4.0 |
| `def-mquery-into-dependency` | `node_modules/mquery/lib/mquery.js` | `packages["node_modules/mquery"]`, version 6.0.0 |
