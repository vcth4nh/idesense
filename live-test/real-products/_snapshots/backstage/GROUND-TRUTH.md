# Captured ground truth: backstage

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.
The window checks used WebStorm 2026.3 (WS-263.7307.202) with a window, on a copy of the pin.

- **backstage: one content root and no source root.** The project model is in "Setup" in
  [notes.md](../../_setup/backstage/notes.md). With no source root,
  `usage-EntityProvider-production-scope`, `usage-EntityProvider-test-scope` and
  `find-file-index.ts-production-scope` give `scope_matches_no_files` (these error rows need
  the two-step bless).
- **backstage: each caller in a workspace package two times.** yarn links each workspace
  package into `node_modules/@backstage/`, and WebStorm adds `node_modules/` as a library root.
  The Call Hierarchy window (scope "All", the default) shows each caller in a workspace package
  two times: one time with the real path, and one time with the path through the link. A jump
  from the second node of `escapeRegExp.test.ts` opens
  `node_modules/@backstage/backend-defaults/src/lib/escapeRegExp.test.ts`.
  `hier-caller-escapeRegExp-d1` gives the same 38 nodes (2 x 19): two times
  `escapeRegExp.test.ts` and its 16 test callbacks, and two times `WinstonLogger.ts` and its
  callback. The window shows the same names, for example `callback for test('character: ^',
  ...)`. `hier-caller-useApi-d1` is a `shape` row: the tool cuts the callers at 200
  (`truncated`); 128 of the 200 nodes have the real path and 72 the path through the link.
  Find Usages of `useApi` gives 317 function calls. The search tools and their windows show
  each file one time, with its real path ([notes.md](../../_setup/backstage/notes.md),
  "Workspace packages and their symbolic links").
- **backstage: a usage in a string has the mark `DYNAMIC`.** `usage-escapeRegExp` gives 20
  usages: 19, and the string of `describe('escapeRegExp', ...)` at
  `packages/backend-defaults/src/lib/escapeRegExp.test.ts:18:10` with `match` `DYNAMIC`.
  `usage-UrlReaderPredicateMux` and `usage-UrlReaderPredicateMux-bysymbol` give 6 usages: 5,
  and the string of `describe('UrlReaderPredicateMux', ...)` at
  `packages/backend-defaults/src/entrypoints/urlReader/lib/UrlReaderPredicateMux.test.ts:19:10`
  with `DYNAMIC`. `explain-UrlReaderPredicateMux-pos` has the `usageCount` 6. Find Usages shows
  19 and 5 results. With the toggle "Show Dynamic Usages" on (it is off by default), it also
  shows "Dynamic usages in Project Files 1" with "Usage in string constants" at the same line.
  So the result equals the IDE, with the marks of "Marked false positives" in
  [PRINCIPLES.md](../../../../docs/PRINCIPLES.md) (the first deviation in
  [ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md), "Where a tool differs from the IDE on
  purpose").
- **backstage: the window puts one string usage in the sure group.** For `GithubEventRouter`
  (`plugins/events-backend-module-github/src/router/GithubEventRouter.ts:30:14`), Find Usages
  shows 5 results with the default settings. With "Show Dynamic Usages" on, it shows 9:
  "Usages in Project Files 6" (the 5, and "Usage in string constants" at
  `GithubEventRouter.ts:39`, `return 'GithubEventRouter';`) and "Dynamic usages in Project
  Files 3" (the strings of `GithubEventRouter.test.ts:20` and `:35`, and of
  `eventsModuleGithubEventRouter.test.ts:39`). The tool gives the mark `DYNAMIC` to all 4
  string usages, also to `GithubEventRouter.ts:39:12`. The tool also gives 27 usages in
  Markdown backtick spans with `DYNAMIC`, and the window shows them in no state. So
  `usage-GithubEventRouter`, `usage-GithubEventRouter-bysymbol` and
  `explain-GithubEventRouter-pos` are not in the suite, and the rows of `UrlReaderPredicateMux`
  stand in for them.
- **backstage: `find-class-Config` has 83 classes.** Go to Class `Config` in the scope Project
  Files gives 257 results. 83 of them declare the exact name `Config` (81 interfaces of
  `config.d.ts` files and 2 type aliases), and they are the 83 of the tool. The tool matches
  the exact name by default (`fuzzySearch` in [USAGE.md](../../../../docs/USAGE.md)).
- **backstage: the form of the file structure.** The 8 `file-structure-*` rows give the same
  nodes in the same order as the Structure window. The form differs: the tool writes the
  modifier words (`export`, `protected`, `abstract`), and the window shows icons. The window
  strikes through the deprecated `slackChannel` of `InfoCard.tsx`, and the tool has no mark.
  For `catalog-info.yaml` the window has a root node with the path, and the tool has the file
  name as a header. In its default state the window collapses some nodes (the constructor of
  `GithubEventRouter`, the keys of the YAML document), and the tool shows all nodes.
- **backstage: the Structure window of an OpenAPI file.** For
  `plugins/catalog-backend/src/schema/openapi.yaml` the Structure tool window shows the OpenAPI
  view: the root row "OpenAPI 3.1 openapi.yaml", then `servers`, `Components` and `Paths`. It
  has no node for the keys `openapi`, `info` and `tags`, and the tool has none. With all nodes
  expanded the window has 217 rows: the root row and the 216 nodes of the tool, with the same
  names, order and nesting. The tool has the file name as a header and no root node. A row of
  the window shows the name and then the `description` of the node, on one row, and the tool
  writes the description as the signature of the node, on one line (since the fix of #335).
  `file-structure-openapi.yaml` is a `shape` row: it pins the 218 lines of the result (the file
  name, an empty line and the 216 nodes).
- **backstage: the TypeScript service.** WebStorm starts the TypeScript service of the product
  (the `typescript` 5.7.3 of `node_modules/`, Node.js with `--max_old_space_size=3072`) at the
  first request that needs it. After four runs of all rows the service had 3.16 GB resident
  memory, and the IDE 4.47 GB. The service first loads the root `tsconfig.json`, and a request waits
  for at most 20 s (`JSLanguageServiceUtil`, `DEFAULT_TIMEOUT`, in
  `plugins/javascript-plugin/lib/modules/intellij.javascript.backend.jar` of WS-263.7307.202).
  After each of three opens of the fleet IDE, the first row of the first run met this limit. The
  row was the callees of `determineDestinationTopic`. `idea.log` has "Loading TypeScript
  project", 20 s later SEVERE `JSLanguageServiceQueue` "Failed to process command
  ideGetElementType - timed out" with "Plugin to blame: IdeSense", and then WARN
  `JsonRpcHandler` "Tool 'ide_call_hierarchy' was cancelled". The row gave `internal_error`
  "kotlinx.coroutines.TimeoutCancellationException: Coroutine "request-handler" timed out
  waiting for 20000 ms". A later direct call of the same row took 0.04 s. The WebStorm with a
  window met the same limit with its own first request (`provideInlayHints`) in three of four
  sessions. So the row is the canary `canary-hier-callee-determineDestinationTopic-d1`: the gate
  tries a canary with an expected entry again every 10 s, up to the readiness budget after a
  switch (`live-test/suite/cli.py`). In a `--product backstage` run that opened the product
  itself, the canary first gave this error, the harness tried the canary rows again, and the
  run passed. The plugin answer (`internal_error` with no cause and no hint to call again) is
  issue #333.

## Parked rows

Each of these rows shows an open defect (see "Parked rows" in `live-test/CONVENTIONS.md`).

| Row | Issue | Defect |
|---|---|---|
| `usage-InfoCard`, `usage-InfoCard-page1`, `usage-InfoCard-page2` | #307 | the usage of a JSX tag has the column of `<`, for example `InfoCard.stories.tsx:57:5` (`<InfoCard {...args}>`); the tag name is at column 6. The 99 usages are the 98 of Find Usages and the JSDoc `{@link InfoCard }` of `BottomLink.tsx:53:37` with `DYNAMIC`, which Find Usages shows with "Show Dynamic Usages" on |
| `def-DateInput-jsx-default-import` | #315 | the tag `<DateInput` of `DateWidget.tsx:29:11` gives the import line `DateWidget.tsx:22:8` (kind `IMPORTED_DEFAULT_BINDING`); Go to Declaration opens `DateInput.tsx` at 56:25, the function of the default export |
| `find-file-index.ts-paged`, `find-file-package.json-paged`, `find-file-plugin.ts-paged` | #271 | Go to File also lists the files that match through the directory path: `index.ts` 1,255 against 1,259, `package.json` 287 against 325, `plugin.ts` 151 against 4,595; each file of the tool is in the Go to File list. The control `find-file-setupTests.ts-paged` gives the same 130 files as Go to File |
| `find-file-module.ts.hbs`, `find-file-GithubEventRouter.ts-directory-part`, `find-file-plugin.ts-directory-part` | #271 | `module.ts.hbs`: 7 files, and Go to File lists the same 7 first, then more than 30 templates below `packages/cli-module-new/`. `router/GithubEventRouter.ts`: 0, and Go to File 2 (All Places). `src/plugin.ts`: 0, and Go to File many |
| `usage-Config-bysymbol`, `explain-Config-ambiguous` | #269 | the name `Config`, which 83 declarations share, resolves to one declaration (33 usages) with no `candidates` |
| `search-text-GithubEventRouter`, `search-text-GithubEventRouter-code`, `search-text-GithubEventRouter-strings` | #144 | 88, 83 and 7 matches. Find in Files gives "91 matches in 16 files" on the same 88 lines. The Find tool window lists 57 matches below "Usage in string constants": 7 lines of TypeScript files, and 50 lines of code fences in 10 Markdown files, which the tool gives the label `CODE`. So `context: "strings"` leaves the 50 lines out (Find in Files with "In String Literals": "57 matches in 15 files"), and `context: "code"` returns them (the window has 33 matches below "Unclassified"). `search-text-GithubEventRouter-comments` has 1 match, as Find in Files with "In Comments" ("1 match in 1 file") |
