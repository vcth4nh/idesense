# Captured ground truth: nest

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **nest: one content root and no source root.** The project model is in "Setup" in
  [notes.md](../../_setup/nest/notes.md). With no source root,
  `usage-ParseFilePipe-production-scope`, `usage-ParseFilePipe-test-scope` and
  `find-file-app.module.ts-production-scope` give `scope_matches_no_files` (these error rows
  need the two-step bless).
- **nest: two marked extras in the usages of `ParseFilePipe`.** `usage-ParseFilePipe` has 15
  usages: 13, and 2 with `match` `DYNAMIC`. The 2 are the JSDoc `@see {ParseFilePipe}` of
  `packages/common/pipes/file/file-validator.interface.ts:6` (`usageType` COMMENT) and the
  string `'ParseFilePipe'` of `packages/common/test/pipes/file/parse-file.pipe.spec.ts:28`
  (`usageType` REFERENCE). Find Usages of WebStorm 2026.3 shows "Usages in Project Files 13
  results". With the toggle "Show Dynamic Usages" on (it is off by default), it also shows
  "Dynamic usages in Project Files 2 results": "Usage in comments 1" and "Usage in string
  constants 1". So the result equals the IDE, with the marks of "Marked false positives" in
  [PRINCIPLES.md](../../../../docs/PRINCIPLES.md). The `usageType` REFERENCE of the string is
  the taxonomy gap of #27.
- **nest: `null.listen` as a qualified name.** `impls-Server.listen` has 14 implementations.
  Six of them are the fields `listen` of the anonymous classes
  `new (class extends Server { ... })()` in
  `packages/microservices/test/nest-microservice.spec.ts` (lines 58, 76, 99, 119, 138, 220).
  Their `qualifiedName` is `null.listen`. Copy Reference of WebStorm 2026.3 on such a field
  gives the same text, `null.listen`. The text comes from the IDE:
  `JSQualifiedNameProvider.getQualifiedName` joins `JSClass.getQualifiedName()`, a `.` and the
  member name (bytecode, `plugins/javascript-plugin/lib/modules/intellij.javascript.backend.jar`,
  build WS-263.7307.202), and an anonymous class has no qualified name.
- **nest: `hier-caller-isNil-d1` has exactly 100 callers.** 100 is no cap: the tree limit is 200
  nodes, and `truncated` is false. 41 callers are FILE nodes, one for each file that imports
  `isNil`. `ide_find_usages` at the same position gives 41 imports and 78 references in 60
  enclosing scopes. The two tools group the call sites in different ways (nested functions,
  test callbacks), so the call hierarchy has 59 callers that are no FILE node.

## Parked rows

- `impls-Server` (#277): 9 implementations. Go to Implementation of WebStorm lists 15, with 6
  "anonymous" entries: the 6 anonymous classes of
  `packages/microservices/test/nest-microservice.spec.ts`.
- `usage-AppModule-bysymbol`, `usage-Module-bysymbol` and `hier-super-NoopAdapter-byname`
  (#269): the product has 73 classes `AppModule`, several declarations of `Module` (the
  decorator function, the class of `packages/core/injector/module.ts`, test classes) and 2
  classes `NoopAdapter`. Each name resolves to one declaration with no candidates.
- `explain-AppModule-bysymbol` (#274, and also #269): its `signature` is
  `export class AppModule` at the first explain call of an IDE session and `class AppModule`
  at a later call. Keep this row as the first `ide_explain_symbol` row of the product: then
  the other explain rows are not the first call. In a WebStorm process with a window, the first
  two calls had the first-call form, and `explain-Catch-pos` gave the parameter type
  `Type<any> | Abstract<any>[]` (the text of Quick Documentation) for the source
  `Array<Type<any> | Abstract<any>>`.
- `hier-sub-Server` (#304): 15 subtypes, as the Type Hierarchy window of WebStorm shows.
  The 6 anonymous classes of `packages/microservices/test/nest-microservice.spec.ts` get the
  first 60 characters of their source text as `name`, and `strategy` (the variable that holds
  the instance) as `qualifiedName`. The window shows these nodes with no text. The row has
  `compare` `shape`, because its result holds source text.
- `super-ExpressAdapter.listen-deep-chain` (#305): the result has one of the three
  overloads of `AbstractHttpAdapter.listen` (`packages/core/adapters/http-adapter.ts`, lines
  132-134), and the line changes between IDE sessions (132, 133 or 134). The gutter marker of
  WebStorm lists all three: "Choose Super Method of Method 'listen' (3 found)".
- `find-file-app.module.ts` and `find-file-app.module.ts-paged` (#271): 67 files
  (`totalCollected` 67): the 65 files `app.module.ts`, `integration/typeorm/src/app-async.module.ts`
  and `integration/repl/src/long-living-app.module.ts`. Go to File of WebStorm (tab "Files",
  scope "Project Files") lists 77 files: the same 67, and 10 files that match the query through
  their folder path, for example `sample/01-cats-app/src/core/core.module.ts` and
  `integration/nest-application/raw-body/src/fastify.module.ts`.
- `def-kafka.interface-import-path-js-ext` (#192): the import path
  `'../external/kafka.interface.js'` of `packages/microservices/server/server-kafka.ts:25`
  gives "Could not resolve symbol definition". Go to Declaration of WebStorm opens
  `packages/microservices/external/kafka.interface.ts`.
