# Captured ground truth: lexical

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.
The window checks used WebStorm 2026.3 (WS-263.7307.202) with a window, on a copy of the pin.

- **lexical: one content root and no source root.** The project model is in "Setup" in
  [notes.md](../../_setup/lexical/notes.md). With no source root,
  `find-file-App.tsx-production-scope`, `usage-$createImageNode-production-scope` and
  `usage-$createImageNode-test-scope` give `scope_matches_no_files` (these error rows need the
  two-step bless).
- **lexical: two declarations of one name (declaration merging).** `LexicalDecoratorNode.ts`
  declares `DecoratorNode` as an interface (line 23) and as a class (line 30). So
  `hier-super-ImageNode` has `DecoratorNode` two times, the interface with no supertype and the
  class with `LexicalNode`, `SlotHostNode` and `SlotChildNode`. The Supertypes view of the Type
  Hierarchy window shows the same tree. `hier-super-ParagraphNode` has `ElementNode` two times
  (lines 114 and 121), also the same as the window. `find-class-DecoratorNode` has 3 classes:
  the interface, the class and the Flow class of `Lexical.js.flow`. Go to Class lists the same 3.
- **lexical: the Flow stubs.** WebStorm gives a `.js.flow` file the language "Flow JS" (the
  `language` of `ide_file_structure` on `Lexical.js.flow`). So the filter `javascript` keeps no
  Flow declaration: `find-class-LexicalNode-lang-javascript` and
  `find-symbol-ParagraphNode-lang-javascript` are empty. `def-DecoratorNode-from-flow-stub`
  goes from `LexicalDecoratorBlockNode.js.flow:20:52` to the TypeScript class
  (`LexicalDecoratorNode.ts:30:14`), but `def-LexicalNode-in-flow-stub` stays in the Flow file
  (`Lexical.js.flow:489:22`). Go to Declaration opens the same two places.
- **lexical: a JSX tag of a lazy component.** `def-ImageComponent-jsx-lazy` goes from
  `<ImageComponent` (`ImageNode.tsx:304:8`) to `const ImageComponent = React.lazy(...)`
  (`ImageNode.tsx:53:7`, kind CONSTANT), not to the file of the component. Go to Declaration
  opens the same place.
- **lexical: `search-text-CollapsibleContainerNode` has 27 matches.** Find in Files gives 28
  occurrences. The tool keeps one match for each line (an approved deviation,
  [ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md)).
- **lexical: no row pins a subtype count of the node classes.** The counts of `ParagraphNode`,
  `ElementNode`, `LexicalNode` and `DecoratorNode` (subtypes, implementations, overrides of
  `createDOM` and `decorate`) can include classes of `examples/`. Each example folder has its
  own `tsconfig.json` and no `node_modules/`, so its import of `lexical` has no package (see
  [notes.md](../../_setup/lexical/notes.md)). But in some IDE sessions the IDE resolves the
  import to `packages/lexical/` all the same, and then the example class counts. One tool call
  can change the counts: in one session `ParagraphNode` had 8 subtypes, and one call of
  `ide_diagnostics` on `LexicalNode.ts`, with no editor open, changed it to 9
  (`CustomParagraphNode` of `examples/node-replacement`), `ElementNode` from 108 to 109,
  `LexicalNode` from 198 to 199 and the overrides of `createDOM` from 129 to 130. The new
  counts stayed in the session. In another session, after the open of 3 editors, `LexicalNode`
  had 203 subtypes and `DecoratorNode` 47. The window and the tool agree in the two states that
  the window check covered: Choose Implementation and the Type Hierarchy window gave 8 for
  `ParagraphNode` in one session, and Choose Implementation gave 9, 109, 199 and 130 in
  another. The exact cause in the IDE is not established. The fleet gave 8, 108, 198 and 43 in
  each of the 7 runs of the onboarding. So these 8 rows are not in the suite:
  `explain-ParagraphNode-pos`, `hier-sub-ElementNode`, `hier-sub-LexicalNode`,
  `hier-sub-DecoratorNode`, `impls-LexicalNode`, `impls-LexicalNode.createDOM`,
  `impls-DecoratorNode` and `impls-DecoratorNode.decorate`.
- **lexical: the form of the file structure.** The 4 `file-structure-*` rows give the same
  nodes in the same order as the Structure window in its default state. The form differs:
  the tool writes the modifier words (`export`, `declare`, `readonly`), and the window shows
  icons. The window strikes through a deprecated member, and the tool has no mark. The tool
  cuts a name that has more than one source line at 80 characters with `…` (the parameter
  list of `$createImageNode` in `ImageNode.tsx`), so `file-structure-ImageNode.tsx` is a
  `shape` row. For a computed member
  name (`[STATIC_NODE_TYPE]` in `LexicalNode.ts`) the tool and the window both show the name
  `null`.
- **lexical: instruction files in the checkout.** The checkout has its own instruction files
  for agents, `AGENTS.md`, `CLAUDE.md` and `.claude/settings.json` (see "Product checkouts" in
  [AGENTS.md](../../../AGENTS.md)).

## Parked rows

- `usage-ImageNode.setShowCaption-receiver-call` (#307): the usage
  `node.setShowCaption(show)` of `ImageComponent.tsx:427` has column 9, the receiver `node`.
  Find Usages lists the same 2 usages, and its jump puts the caret at 427:14, the method name.
- `usage-ImageResizer-jsx` and `usage-KatexRenderer-jsx` (#307): the usage of a JSX tag has the
  column of `<` (`ImageComponent.tsx:507:11`). Find Usages lists the same 4 usages of
  `ImageResizer`, and its jump to line 507 puts the caret at 507:12, the tag name.
- `search-text-gamma-after-escape` (#309): 1 match. Find in Files with "Match case" and
  "Words" gives 3 matches in `LexicalReconciler.test.ts` (lines 562, 570, 585). The matches of
  lines 570 and 585 come after the escape `\n` in `'alpha\n\nbeta\n\ngamma'`.
- `search-text-ImageNode-injected-fragment` (#144): 39 matches, the 39 lines of Find in Files
  ("43 matches in 14 files" with "Match case" and "Words"). Line 458 of
  `packages/lexical-website/docs/react/plugins.md`, a line of a code fence with the info string
  `jsx`, has the label `CODE`. The Find tool window lists it below "Usage in string constants".
- `hier-caller-$isCaptionEditorEmpty-d2` (#186): one child is a FILE node of a fragment in
  `packages/lexical-website/docs/serialization/serialization.md`. The tool gives the path
  `/serialization.md`, and the harness keeps the name only. The Call Hierarchy window shows the
  same 12 children, with a node `serialization.md`.
- `find-file-types.ts`, `find-file-App.tsx`, `find-file-App.tsx-directory-part`,
  `find-file-utils.ts`, `find-file-LexicalNode.ts`, `find-file-index.ts-paged` and
  `find-file-Doc.d.ts-libraries-scope` (#271): Go to File lists more files. `types.ts`: tool 9,
  Go to File 17. `App.tsx`: 16 and 25. `src/App.tsx`: 0 and 16. `utils.ts`: 30 and 75.
  `LexicalNode.ts`: 56 and 163. `index.ts`: 117 and 118 (the extra file is
  `packages/lexical-extension/src/NodeSelectionDataSelectedExtension.ts`). `Doc.d.ts` in "All
  Places": 98 and 99 (the extra file is
  `dev-examples/shadow-dom-web-component/src/vite-env.d.ts`). For these last four names, each
  file of the tool is in the Go to File list. For example, Go to File also lists
  `examples/agent-example/src/utils/extractEntityNodes.ts` for `utils.ts`.
- `usage-ParagraphNode-bysymbol` and `hier-super-ParagraphNode-byname` (#269): the name
  resolves to the TypeScript class with no candidates. Go to Symbol lists 2 classes
  `ParagraphNode`: the TypeScript class and the Flow class of `Lexical.js.flow:1128`.
- `def-ImageResizer-jsx-tag` (#315): the tag `<ImageResizer` of `ImageComponent.tsx:507:12`
  gives the import line `ImageComponent.tsx:56:8` (kind `IMPORTED_DEFAULT_BINDING`). Go to
  Declaration opens `ImageResizer.tsx` at 25:25, the function of the default export.
