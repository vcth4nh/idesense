# Captured ground truth: mongoose

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **mongoose: one content root and no source root.** The project model is in "Setup" in
  [notes.md](../../_setup/mongoose/notes.md). With no source root,
  `usage-PathTrie-production-scope`, `usage-PathTrie-test-scope` and
  `find-file-index.js-production-scope` give `scope_matches_no_files` (these error rows need
  the two-step bless).
- **mongoose: two definitions that WebStorm does not resolve.** `def-Document.$get-alias`
  (`$get` on `this` in `lib/document.js:1185`; line 2060 assigns `Document.prototype.get` to
  `Document.prototype.$get`) and `def-Schema.emit-via-prototype` (`emit` on `this` in an arrow
  function in `lib/schema.js:422`; the prototype of `Schema` is made from the prototype of the
  `EventEmitter` of the module `events`) give the error "Could not resolve symbol definition".
  Go to Declaration of WebStorm 2026.3 says "Cannot find declaration to go to" at both
  positions. These error rows need the two-step bless.
- **mongoose: implementations with no super method.** `impls-SchemaType.cast` gives
  `SchemaMap.cast` (`lib/schema/map.js:55`) and `Union.cast` (`lib/schema/union.js:34`). Both
  classes extend `SchemaType` through `require`. For `SchemaMap.cast`, WebStorm shows no gutter
  marker for a super method, and Go to Super Method does not navigate. So no row asks for the
  super method of these methods.
- **mongoose: four marked extras in the usages of the TypeScript class `Document`.**
  `usage-Document-d.ts-ts-to-js` has four rows with `match` `DYNAMIC` that Find Usages of
  WebStorm does not list in any group, also with text occurrences on:
  `test/index.test.js:901` (`typeof mongoose.Document`), and `test/types/aggregate.test.ts:142`,
  `:158` and `test/types/models.test.ts:973` (the string `'Document'` as the first argument of
  `model(...)`). A marked extra is permitted ("Marked false positives" in
  [PRINCIPLES.md](../../../../docs/PRINCIPLES.md)). The four rows come from the search of the
  symbol itself: the result has no `notes` of a base or an overriding declaration. Which
  reference search gives them is not established. The nine `DYNAMIC` rows in Markdown prose are
  the group "Dynamic usages" of WebStorm (8 lines; `docs/documents.md:19` has two usages). The
  row is parked with #186 for its other rows (see "Parked rows").
- **mongoose: `file-structure-connection.js` differs in a WebStorm with a window.** In 2 of 2
  calls on a WebStorm 2026.3 started with a window (two processes), the outline had 706 lines and
  not the usual 158: each node `<anonymous>(err): never (line 1083)` held a second copy of the
  members of `Connection`, and the top-level node `set(val): void (line 133)` held one more copy.
  The File Structure popup of the same process showed no copy. The fleet WebStorm
  (`serverMode`) gave 158 lines in 10 calls in three IDE sessions. The observation is in a
  comment of #177. The expected row holds the tree with 158 lines.
- **mongoose: instruction files in the checkout.** The checkout has its own instruction file for
  agents, `.github/instructions/type-tests.instructions.md` (see "Product checkouts" in
  [AGENTS.md](../../../AGENTS.md)).

## Parked rows

- `usage-Document-d.ts-ts-to-js` (#186): 16 usages in code fences of Markdown files have the
  path `/<file name>.md` and a line of the fence. The three imports of
  `docs/typescript/populate.md` (lines 6, 34 and 66) become one usage.
- `explain-MissingSchemaError-bysymbol`, `usage-MissingSchemaError-bysymbol` and
  `hier-sub-MissingSchemaError-byname` (#269): two JavaScript classes have the name
  `MissingSchemaError`. The name resolves to the class of `lib/error/browserMissingSchema.js`
  with no candidates, in each IDE session.
- `hier-caller-ValidationError.addError-bysymbol` (#269): the name resolves to the method of
  `lib/error/validation.js` in one IDE session, and gives two candidates (the method and the
  field of `types/error.d.ts`) in the next sessions.
