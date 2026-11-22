# Captured ground truth: webpack

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.
The window checks used WebStorm 2026.3 (WS-263.7307.202) with a window, on a copy of the pin.

- **webpack: one content root and no source root.** The project model is in "Setup" in
  [notes.md](../../_setup/webpack/notes.md). With no source root,
  `usage-ModuleFactory-production-scope`, `usage-ModuleFactory-test-scope` and
  `find-file-index.js-production-scope` give `scope_matches_no_files` (these error rows need the
  two-step bless).
- **webpack: `def-AutomaticPrefetchPlugin-lazy-getter` gives `types.d.ts:861:2`, not a file of
  `lib/`.** The position is a `new` expression of `AutomaticPrefetchPlugin`, a member of the
  package root that a test configuration takes with `require`. `lib/index.js` gives this member
  through a deprecated getter. The result is the constructor of the class that the generated
  `types.d.ts` declares. Go to Declaration at the same position opens the same line.
- **webpack: `hier-caller-getRuntimeKey-d1` has 10 nodes, all in `lib/util/runtime.js`.** The
  nodes are the file node and 9 functions of that file. 7 other files call `getRuntimeKey`
  through a destructured `require`, and `usage-getRuntimeKey-destructured-require` has their
  usages (36 usages in 8 files). The Call Hierarchy window (callers) shows the same 10 nodes, and
  Find Usages shows "36 results". `hier-caller-compareRuntime-d1` has 1 node, the file node of
  `runtime.js`; the window shows the same.
- **webpack: `find-file-byDependency.js-test-node-modules` gives no file, and
  `find-file-big.js-test-node-modules` gives no file of a `node_modules` folder below `test/`.**
  `test/` has committed `node_modules` folders. Go to File (tab "Files") gives no such file with
  the scope "All Places" and with the scope "Project Files". Whether WebStorm marks these
  folders as excluded or as libraries: not tested.
- **webpack: `usage-Dependency-page1` and `usage-Dependency-page2` count 101 usages, Find Usages
  shows "100 results".** The tool gives one entry for each usage. The Find Usages view shows
  one row for each line, and `lib/Compilation.js:661` has two usages of `Dependency`. The other
  99 rows match the other 99 usages of the tool (the view was exported to text and compared).
- **webpack: `hier-callee-keyToRuntime-d1` is a `shape` row: 1 callee of the kind `METHOD`.**
  The callee is `String.split`. Its file differs between two IDE instances of the same build: the
  WebStorm of the fleet gives the declaration in
  `node_modules/assemblyscript/std/assembly/index.d.ts` (4 runs). The WebStorm with a window
  gives the declaration in `node_modules/typescript/lib/lib.es5.d.ts`, in the tool and in the
  Call Hierarchy window (callees). The window of the fleet IDE is not tested. Neither shows a
  node for `new SortableSet(items)` in the same function.
- **webpack: `file-structure-BannerPlugin.json` keeps the order of the file.** The top level is
  `definitions`, `title`, `anyOf`. The Structure tool window shows the same 97 nodes in the same
  order and nesting (all nodes expanded, exported to text and compared). The File Structure
  popup (Ctrl+F12) has "Alphabetically" on in a new profile, so it shows `anyOf`, `definitions`,
  `title`.
- **webpack: node names of the form `callback for f(ARG, ...)`.**
  `hier-caller-getCompilationHooks-d1` has 34 such nodes, for example `callback for
  compiler.hooks.compilation.tap(PLUGIN_NAME, ...)`. The Call Hierarchy window shows the same
  form of name.
- **webpack: parked rows.** Each of these rows shows an open defect (see "Parked rows" in
  `live-test/CONVENTIONS.md`). "Go to Declaration" and "Go to Class" are the results of the
  WebStorm with a window.

  | Row | Issue | Defect |
  |---|---|---|
  | `def-Compilation-jsdoc-import-tag`, `def-Compiler-jsdoc-import-tag-root`, `def-NormalModule-jsdoc-generic` | #323 | a type name in a JSDoc comment gives "Could not resolve symbol definition". Go to Declaration gives Choose Declaration with `lib/Compilation.js` first, `lib/Compiler.js:189:7` and `lib/module/NormalModule.js:737:7` |
  | `def-Module-jsdoc-generic`, `def-LoaderRunnerLoaderContext-import-type` | #323 | the tool gives another name of the same JSDoc type: the typedef at `lib/Compiler.js:143:1` and the typedef at `lib/hmr/HotModuleReplacementPlugin.js:79:1`. Go to Declaration gives Choose Declaration with 6 entries (`lib/module/Module.js` among them) and `lib/loaders/LoaderRunner.js:157:1` |
  | `find-class-Compilation`, `find-class-Module`, `find-class-Module-lang-javascript`, `find-class-NorModFac-fuzzy`, `find-class-SyncHook-libraries-scope` | #324 | the JSDoc typedefs that Go to Class lists drop out: `Compilation` 3 of 12 rows, `Module` 5 of 9, `Module` with the filter `javascript` 2 of the 6 rows in `.js` files, `NorModFac` 2 of 3, `SyncHook` with "All Places" 1 of 2 (the typedef of `lib/cache/ResolverCachePlugin.js`). So the canary row of `ide_find_class` uses `ChunkGraph`, a name with no typedef |
  | `def-compilation-hook-into-types.d.ts`, `def-getCompilationHooks-package-self-require` | #178 | Go to Declaration gives Choose Declaration (2 entries; a long list). The tool gives the first entry |
  | `def-Rule-json-schema-ref` | #193 | the tool gives the property `$ref` itself (`BannerPlugin.json:61:17`). Go to Declaration does not move the caret |
  | `usage-ModuleFactory-bysymbol`, `hier-super-Module-byname`, `hier-caller-getCompilationHooks-bysymbol` | #269 | the name takes the declaration of `types.d.ts` with no candidates. Each name also has a declaration in `lib/` |
  | `find-file-Module.js-directory-part` | #271 | the tool gives no file. Go to File gives `lib/module/Module.js` first |
