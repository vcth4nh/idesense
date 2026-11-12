# uptime-kuma

- Repository: https://github.com/louislam/uptime-kuma
- Pin: tag `2.5.3`, commit `1f0755fb044fe08e99fccde6722062fb2bf6c8f4`, committed 2026-08-22
- License: MIT
- IDE: WebStorm (port 29173), fixture languages JavaScript and TypeScript
- Node.js: `engines.node` is `>= 20.4.0` in `package.json`. The fleet host has Node.js 24.16.0
  and npm 11.13.0.
- Languages: the server is CommonJS JavaScript (`server/`), the frontend is Vue 3 single-file
  components (`src/`), and `src/util.ts` is the shared TypeScript module. `src/util.js` is the
  compiled copy of `src/util.ts`, and it is in the repository. `extra/` holds four small
  packages, each with its own `package.json`, and `test/` holds 61 test files.

## Setup

Run `bootstrap.sh`. It needs `node` 20.4 or later and `npm` on the `PATH`. It runs
`npm ci --ignore-scripts` when the lockfile differs from the one of the last install, writes
`.idea/modules.xml` when it is absent, and writes `.idea/uptime-kuma.iml` when its content
differs. The product ignores `/.idea` and `node_modules` in its own `.gitignore`.

- `package-lock.json` is committed (lockfile version 3, 1,307 packages), and `npm ci` never
  writes it. `--ignore-scripts` runs no script of the product and no install script of a
  package. The packages go to `node_modules/` in the checkout (1,259 packages, 620 MB).
- WebStorm restores a project at its start only when the folder has IDE project files. The
  module file holds what WebStorm itself writes at the first open of this folder: one content
  root with no source folder, no test folder and no excluded folder. Evidence: on 2026-11-13 a
  WebStorm with a window opened a copy of the pin with no `.idea` folder, and its module file
  had only the content root. WebStorm adds `node_modules/` as a library root by itself at each
  open (`NodeModulesDirectoryManager`, "Contributed ... allIncludedFileCount:14987" in
  `idea.log`). A close and open cycle kept this model.
- So the project has no source root and no test root. `ide_find_usages` and `ide_find_file`
  with `project_production_files` or `project_test_files` give `scope_matches_no_files`, and
  the call hierarchy scope `production` gives no caller. The JavaScript type hierarchy ignores
  the scope.
- At each open WebStorm excludes `src/util.js` as a file that the TypeScript compiler makes
  from `src/util.ts` (`TypeScriptStartupActivity`: "Exclude 1 generated js files"). So
  `require("../src/util")` resolves to `src/util.ts`, and no tool result has `src/util.js`.
- The first open of a new checkout path can stop before the `node_modules` library exists: on
  2026-11-13 the framework detection of WebStorm changed the project to Vue during the scan,
  the project reloaded, and no "Contributed" line came. Then a `require` of a package did not
  resolve. A close and open cycle repaired it. This occurred at one of approximately four first opens. In
  `idea.log` the signs are a line `PolyContext - Reloading project uptime-kuma on PolyContext
  framework change (none -> vue)` during the first scan, and no line
  `NodeModulesDirectoryManager - Contributed` after it. In this state the canary
  `canary-def-BeanModel-into-dependency` differs: the gate tries again for the readiness time
  (900 s) and then prints `MISCONFIGURED`. Then close the product (`--close-products`), open it
  again (`--open-product uptime-kuma`), and start the run again.
- The first request that uses the TypeScript service (a row on a `.ts` or a `.vue` file) starts
  `@vue/typescript-plugin`, and some seconds later WebStorm changes the roots of its TypeScript
  library ("Root changed for updating the ts library"). In one session this made a dumb pass of
  1 s. In another session it made no dumb pass, but during the change `setInterval` resolved to
  the `lib.dom.d.ts` that WebStorm bundles and not to `node_modules/typescript/lib/lib.dom.d.ts`.
  So no row names a file of the TypeScript standard library, and
  `hier-callee-EmbeddedMariaDB.start-d1` is a `shape` row. The `exact` callee row is
  `hier-callee-Maintenance.getTimezone-d1`: its two callees are methods in project files.

Times on 2026-11-13: the first bootstrap took 26.5 s (the `npm ci`). A second run took 0.06 s
and changed no file. An open of the product took 11 s. The second of two smart reads 15 s apart
came 45 s after the open at the second open (a dumb pass of 16 s for `node_modules`) and 28 s
after it at the third open (no dumb pass). A run of all rows takes 3 to 5 s, and
20 s when it starts the TypeScript service.

## Library files in the expected rows

All dependency files of the rows are in `node_modules/` of the checkout, so they keep their
path and position. An entry of `package-lock.json` decides each of them.

| Row | File | Lock entry |
|---|---|---|
| `canary-def-BeanModel-into-dependency`, `hier-super-Monitor-into-dependency`, `find-class-BeanModel-libraries-scope`, `find-file-bean-model.d.ts-libraries-scope` | `node_modules/redbean-node/dist/*.d.ts` | `packages["node_modules/redbean-node"]`, version 0.3.3 |
| `def-Dayjs.valueOf-into-dependency`, `def-dayjs-vue-import-into-dependency` | `node_modules/dayjs/index.d.ts` | `packages["node_modules/dayjs"]`, version 1.11.21 |
| `find-file-dayjs.min.js-libraries-scope` (no file) | `node_modules/dayjs/dayjs.min.js` | `packages["node_modules/dayjs"]`, version 1.11.21 |

No row uses a file of the typings cache of WebStorm (`javascript/typings/` in the system
folder). WebStorm downloads these type files by itself, and the lockfile does not decide them:
`ide_find_class` for `Router` with the libraries scope gives two `index.d.ts` files of
`@types/express` 4.17.25 from that cache.

## Captured ground truth

- `usage-Monitor.start` gives 0 usages. Find Usages of WebStorm says "Nothing found in
  'Project Files'", and the code vision shows "no usages": each call goes through a value with
  no type.
- `hier-sub-NotificationProvider` gives 0 subtypes and `impls-NotificationProvider` gives 0
  implementations, while 105 classes in other files extend it through `require`. The Type
  Hierarchy of WebStorm shows no subtype, and Go to Implementation says "No implementations
  found" (see the JavaScript fixture note on CommonJS subtypes). The usages of the class are
  107, the same as Find Usages of WebStorm.
- `hier-super-KumaColumnCompiler` gives no supertype. The base class comes from a `require` of
  a knex file, and the Supertypes view of WebStorm shows no supertype either.
- `find-file-dayjs.min.js-libraries-scope` gives no file. Go to File of WebStorm with "All
  Places" finds nothing either.
- `find-symbol-startDateTime` gives the computed property of `MaintenanceTime.vue` and a local
  constant of a method in `server/model/maintenance.js`. Go to Symbol of WebStorm lists the
  same two. The qualified name of the computed property is `default.computed.startDateTime`,
  the same as Copy Reference of WebStorm.

## Parked rows

Each of these rows shows an open defect (see "Parked rows" in `live-test/CLAUDE.md`).

| Row | Issue | Defect |
|---|---|---|
| `def-notification-provider-require-path` | #191 | a position in a `require` path gives the folder of the first path segment (`PACKAGE`), not the module file |
| `def-util.ts-import-path-vue` | #192 | a position in the module path of an ES6 `import` gives "Could not resolve symbol definition" |
| `def-startDateTime-decl`, `explain-startDateTime-decl-pos`, `usage-startDateTime` | #193 | the name of a computed property takes the reference of the outer key `computed`: the result is the `.vue` file, or the key as the only usage |
| `hier-caller-beat-d1` | #194 | a function in a local constant gives the hierarchy of the enclosing method |
| `usage-NotificationProvider.send`, `usage-Discord.send` | #196 | the tool gives the 10 dynamic usages that Find Usages of WebStorm hides by default ("0 of 10 usages"). For `Discord.send` WebStorm first asks "Do you want to find usages of the base method?", and the 10 are the answer No (#171) |
| `file-structure-discord.js` | #198 | an object literal node that has no text is absent, with its children. The row also shows #199: the full text of a spread element is a node name over several lines |
| `search-text-startDateTime`, `search-text-startDateTime-code` | #184 | a match in an injected fragment comes a second time, with the path `/<file name>` |
| `def-startDateTime-from-template`, `explain-startDateTime-from-template-pos` | #189 | a position in a template interpolation is no anchor: the result is the `div` element of the HTML schema |

`file-structure-MaintenanceTime.vue` shows #197 (the node `default` of `export default` has
line 1), but it is a `shape` row, which pins only the line count. So it is not parked. #195 and #200 have no row.
