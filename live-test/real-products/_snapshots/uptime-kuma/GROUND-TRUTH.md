# Captured ground truth: uptime-kuma

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **uptime-kuma: one content root and no source root.** The project model is in "Setup" in
  [notes.md](../../_setup/uptime-kuma/notes.md). With no source root,
  `usage-sleep-production-scope`, `usage-sleep-test-scope` and
  `find-file-index.js-production-scope` give `scope_matches_no_files` (these error rows need
  the two-step bless). `hier-caller-sleep-production-scope` gives no caller, and the
  JavaScript type hierarchy ignores the scope (`hier-sub-ConditionOperator-production-scope`).
- **uptime-kuma: a TypeScript library row is a `shape` row.**
  `hier-callee-EmbeddedMariaDB.start-d1` is a `shape` row, and no `exact` row names a file of
  the TypeScript standard library. `hier-callee-Maintenance.getTimezone-d1` is the `exact`
  callee row. The reason is in "Setup" in [notes.md](../../_setup/uptime-kuma/notes.md).
- **uptime-kuma: empty rows.** `usage-Monitor.start` gives 0 usages: each call goes through a
  value with no type. Find Usages of WebStorm says "Nothing found in 'Project Files'", and the
  code vision shows "no usages". `hier-sub-NotificationProvider` and
  `impls-NotificationProvider` give nothing, although 105 classes in other files extend the
  class through `require` (see the note on `hier-sub-Probe-*` in
  `live-test/fixtures/_snapshots/javascript/GROUND-TRUTH.md`). The Type Hierarchy of WebStorm
  shows no subtype, and Go to Implementation says "No implementations found". The usages of
  the class are 107 (`usage-NotificationProvider`), the same as Find Usages of WebStorm.
  `hier-super-KumaColumnCompiler` gives no supertype: the base class comes from a `require` of
  a knex file, and the Supertypes view of WebStorm shows no supertype either.
  `find-file-dayjs.min.js-libraries-scope` gives no file, and Go to File of WebStorm with "All
  Places" finds nothing either.
- **uptime-kuma: the files with the name `index.js` have no fixed order.** `find-file-index.js`
  gives four files with the name `index.js` and one file whose name only holds the query. The
  tool ranks the files by the match of the file name, so the fifth file is always last. The
  four files keep the order in which the IDE index gives them, and that order changes with a new
  index: the fleet gave three orders (WebStorm 2026.2, and WebStorm 2026.3 with two checkouts of
  the product), and two instances of a throwaway WebStorm 2026.3 gave two more. Go to File of
  WebStorm 2026.3 (the tab "Files" of Search Everywhere, scope "Project Files") also puts the
  fifth file last, and it changes the order of the four files from one open of the popup to the
  next: 7 opens gave 7 orders. So the row has the compare mode `exact`, not `ordered`.
- **uptime-kuma: a `.vue` file as a caller.** `hier-caller-sleep-d1` has the nodes
  `CountUp.vue`, `SetupDatabase.vue` and `EditMonitor.vue` at line 1 with the kind `SYMBOL`.
  Each file imports the function outside a function, and the caller tree of WebStorm keys a
  caller by its enclosing function, class or file
  (`JSCallHierarchyNodeDescriptor.getEnclosingElement`, bytecode, build 262.8665). The
  Hierarchy window of WebStorm ("Callers of sleep", scope All) shows the same 10 callers, with
  the three files as file nodes.
- **uptime-kuma: two symbols named `startDateTime`.** `find-symbol-startDateTime` gives the
  computed property of `MaintenanceTime.vue` and a local constant of a method in
  `server/model/maintenance.js`. Go to Symbol of WebStorm lists the same two. The qualified
  name of the computed property is `default.computed.startDateTime`, the same as Copy
  Reference of WebStorm.
- **uptime-kuma: instruction files in the checkout.** The checkout has its own instruction
  files for agents (see "Product checkouts" in [AGENTS.md](../../../AGENTS.md)).
- **uptime-kuma: the usages of `send` are dynamic usages (#196, #171).**
  `usage-NotificationProvider.send` and `usage-Discord.send` give the 10 calls, all with
  `match` `DYNAMIC`. Find Usages of WebStorm hides them by default ("0 of 10 usages") and lists
  them only with "Show Dynamic Usages" on. For `Discord.send`, WebStorm first asks "Do you want
  to find usages of the base method?", and the 10 calls are the answer No.
  `usage-Discord.send` has a `notes` entry that names `NotificationProvider.send`, with "0 of
  the 10 usages have match BASE": the search of `Discord.send` itself found the 10 calls first.
- **uptime-kuma: `file-structure-MaintenanceTime.vue` shows #197.** The node `default` of
  `export default` has line 1. The row is a `shape` row, which pins only the line count, so it
  is not parked.
- **uptime-kuma: parked rows.** Each of these rows shows an open defect (see "Parked rows" in
  `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `def-notification-provider-require-path` | #191 | a position in a `require` path gives the folder of the first path segment (`PACKAGE`), not the module file |
  | `def-util.ts-import-path-vue` | #192 | a position in the module path of an ES6 `import` gives "Could not resolve symbol definition" |
  | `def-startDateTime-decl`, `explain-startDateTime-decl-pos`, `usage-startDateTime` | #193 | the name of a computed property takes the reference of the outer key `computed`: the result is the `.vue` file, or the key as the only usage |
  | `hier-caller-beat-d1` | #194 | a function in a local constant gives the hierarchy of the enclosing method |
  | `file-structure-discord.js` | #198 | an object literal node that has no text (an object in an array) is absent, with its children. The row also shows #199: the full text of a spread element is a node name over several lines |
  | `search-text-startDateTime`, `search-text-startDateTime-code` | #184 | a match in an injected fragment comes a second time, with the path `/<file name>` |
  | `def-startDateTime-from-template`, `explain-startDateTime-from-template-pos` | #189 | a position in a template interpolation is no anchor: the result is the `div` element of the HTML schema |

  #195 and #200 have no row.
- **uptime-kuma: `explain-sleep-pos` differed one time.** In one run on 2026-11-17 the
  `signature` of this row differed from the expected row only in a leading word `export`.
  The cause is not known. At a second observation, write an issue and park the row (see "A row
  that differs between two equal runs" in `live-test/CONVENTIONS.md`).
