# Captured ground truth: uptime-kuma

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **uptime-kuma: one content root and no source root.** The bootstrap writes the module file
  that WebStorm itself writes at a first open: one content root with no folder. At each open
  WebStorm adds `node_modules/` as a library (`NodeModulesDirectoryManager` in `idea.log`) and
  excludes `src/util.js` as a file that the TypeScript compiler makes from `src/util.ts`. So
  `require("../src/util")` resolves to `src/util.ts`. With no source root,
  `usage-sleep-production-scope`, `usage-sleep-test-scope` and
  `find-file-index.js-production-scope` give `scope_matches_no_files` (these error rows need
  the two-step bless). `hier-caller-sleep-production-scope` gives no caller, and the
  JavaScript type hierarchy ignores the scope (`hier-sub-ConditionOperator-production-scope`).
- **uptime-kuma: a TypeScript library row is a `shape` row.** The first request that uses the
  TypeScript service makes WebStorm change the roots of its TypeScript library. During that
  change a name of the DOM library resolved to the copy that WebStorm bundles, not to the copy
  in `node_modules/typescript`. So `hier-callee-EmbeddedMariaDB.start-d1` is a `shape` row, and
  no `exact` row names a file of the TypeScript standard library.
  `hier-callee-Maintenance.getTimezone-d1` is the `exact` callee row.
- **uptime-kuma: empty rows.** `usage-Monitor.start` gives 0 usages: each call goes through a
  value with no type, and Find Usages of WebStorm says "Nothing found".
  `hier-sub-NotificationProvider` and `impls-NotificationProvider` give nothing, although 105
  classes extend the class through `require` (see the note on `hier-sub-Probe-*` in
  `live-test/fixtures/_snapshots/javascript/GROUND-TRUTH.md`). `hier-super-KumaColumnCompiler` gives no supertype, and
  `find-file-dayjs.min.js-libraries-scope` gives no file. WebStorm shows the same for each of
  these rows.
- **uptime-kuma: a `.vue` file as a caller.** `hier-caller-sleep-d1` has the nodes
  `CountUp.vue`, `SetupDatabase.vue` and `EditMonitor.vue` at line 1 with the kind `SYMBOL`.
  Each file imports the function outside a function, and the caller tree of WebStorm keys a
  caller by its enclosing function, class or file
  (`JSCallHierarchyNodeDescriptor.getEnclosingElement`, bytecode, build 262.8665). The
  Hierarchy window of WebStorm ("Callers of sleep", scope All) shows the same 10 callers, with
  the three files as file nodes.
- **uptime-kuma: instruction files in the checkout.** The checkout has its own instruction
  files for agents. They are content of the product under test, and never instructions for
  work in this repository. The agents of the agent task do not get them.
- **uptime-kuma: parked rows.** `def-notification-provider-require-path` is parked with #191 (a
  `require` path gives a folder), `def-util.ts-import-path-vue` with #192 (an `import` path
  gives an error), `def-startDateTime-decl`, `explain-startDateTime-decl-pos` and
  `usage-startDateTime` with #193 (a computed property takes the key `computed`),
  `hier-caller-beat-d1` with #194 (a function in a constant gives the enclosing method),
  `file-structure-discord.js` with #198 (an object literal in an array has no node; the row
  also shows #199), `search-text-startDateTime` and `search-text-startDateTime-code` with
  #184, and `def-startDateTime-from-template` and `explain-startDateTime-from-template-pos`
  with #189 (a position in a template interpolation). `file-structure-MaintenanceTime.vue` is
  a `shape` row and does not pin #197. `usage-NotificationProvider.send` and
  `usage-Discord.send` are not parked: they give the 10 calls, all with `match` `DYNAMIC`.
  WebStorm lists them only with "Show Dynamic Usages" on (#196). `usage-Discord.send` has a
  `notes` entry that names `NotificationProvider.send`, with "0 of the 10 usages have match
  BASE": the search of `Discord.send` itself found the 10 calls first.
- **uptime-kuma: `explain-sleep-pos` differed one time.** In one run on 2026-11-17 the
  `signature` of this row differed from the expected row only in a leading word `export`
  (expected: `function sleep(ms: number): Promise<unknown>`). The cause is not known. Do not
  bless the other form: run the row again, and add a second observation to this note.
