# Captured ground truth: ideavim

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.
The window checks used IntelliJ IDEA 2026.3 (IU-263.7307.200) with a window, on a copy of the
pin.

- **ideavim: `hier-sub-EditorActionHandlerBase` has 451 subtypes.** Go to Implementation of the
  IDE lists 456 classes. The 5 other classes are at depth 6, in
  `InsertCommandLineTextActions.kt`. The tool stops at its default depth 5 (an approved
  deviation, "`ide_call_hierarchy` limits" in
  [ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md)). `impls-EditorActionHandlerBase-paged`
  has `totalCollected` 456, the same as the IDE.
- **ideavim: `usage-VimEditor.fileSize-production-scope` has 69 usages.** The Find window of
  Find Usages (scope "Project Production Files") shows "66 results": it shows one row for each
  line, and 3 lines have two usages (`EngineEditorHelper.kt:302`, `VimPutBase.kt:457` and
  `:461`). Its module groups show 5 and 61 rows, the tool has 5 and 64 usages. The same search
  with the scope "Project Test Files" says "69 usages are out of scope 'Project Test Files'".
- **ideavim: `hier-caller-offsetToBufferPosition-d1` has 93 callers.** The row has no `scope`.
  The Call Hierarchy window with the scope "All" shows the same 93 callers. With the scope
  "Production" it shows 91: the 2 others are in test files.
- **ideavim: the outline of a Kotlin class.** In `file-structure-VimChangeGroupBase.kt` the
  Structure window collapses `VimChangesListener` and `companion object` by default. The tool
  lists their children, as in the blessed rows of the Kotlin fixture.
- **ideavim: the generated parser.** `canary-def-VimscriptParser-into-generated` goes to
  `vim-engine/build/generated-src/antlr/main/VimscriptParser.java`, a source root of the module.
  The bootstrap generates this file (see [notes.md](../../_setup/ideavim/notes.md)).
- **ideavim: no row names a file below `.teamcity/`.** The IDE imports `.teamcity/pom.xml` as the
  Maven module `IdeaVim_dsl` (see [notes.md](../../_setup/ideavim/notes.md)).

## Parked rows

| Row | Issue | Defect |
|---|---|---|
| `search-text-matchpairs` | #317 | 16 matches and no match in line 28 of `ideavim-common/src/main/resources/dictionaries/ideavim.dic`. Find in Files finds that line: 18 matches, the 16 lines of the tool, the `.dic` line and a second match on one line |
| `find-file-Range.kt` | #271 | Go to File lists 12 files: the 11 files of the tool and `vim-engine/src/main/kotlin/com/maddyhome/idea/vim/ex/ranges/Address.kt` |
| `find-file-VimEditor.kt` | #271 | the tool gives 9 files, Go to File at least 20 |
| `find-file-Command.kt` | #271 | a `shape` row: it pins the count of the tool (`totalCollected` 263, `hasMore: true`). The rows of Go to File for `Command.kt` are not counted. The count changes when #271 is fixed. |
| `find-class-AnAction-libraries-scope` | #316 | `internal_error` "Wrong offset: -1. Should be in range: [0, 4792]". Go to Class with the scope "All Places" lists 4 `AnAction` classes. A call can write a SEVERE entry to `idea.log` ("Tool execution failed: ide_find_class"); the product runs of this row wrote none. |
| `search-text-matchpairs-code` | #317 | 9 matches and no match in `ideavim.dic`, line 28 |
