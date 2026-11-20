# Captured ground truth: beets

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **beets: a base class through `import beets`.** `beetsplug/playlist.py` imports only
  `beets` and names the base class `beets.plugins.BeetsPlugin`. `beets/__init__.py` has a
  module `__getattr__`. `def-plugins-via-module-getattr` gives the error "Could not resolve
  symbol definition". In PyCharm, Go to Declaration does nothing at that position. The error
  row needs the two-step bless (see "Rows that pin an expected error" in
  `live-test/CONVENTIONS.md`).
- **beets: 103 subclasses of `BeetsPlugin`.** `impls-BeetsPlugin` and `hier-sub-BeetsPlugin`
  give 103 classes, and a scan of the source finds 105. The two other classes are
  `PlaylistPlugin` (its base is the name of the bullet above) and a local `OtherPlugin` whose
  base is a local class of another method. Choose Implementation of PyCharm says "103 found".
- **beets: 173 usages of `BeetsPlugin`.** Find Usages of PyCharm shows "Usages in Project
  Files (172 usages found)" and a separate group "Dynamic usages in Project Files" with one
  "Untyped (probable) usage" (`playlist.py:75`). The tool gives the sum, 173. The probable
  usage has the `usageType` `REFERENCE` and `match` `DYNAMIC`, and it is the only usage with a
  `match` (#143).
- **beets: no scope for Python subtypes.** `hier-sub-ImportHelper-production-scope` gives the
  same 92 subtypes as a call with no scope. `PySubTypesHierarchyTreeStructure.buildChildren`
  calls `PyClassInheritorsSearch.search(PyClass, boolean)`, which takes no scope (bytecode of
  `intellij.python.community.impl.jar`, build 262.8665).
- **beets: test modules have no `test.` prefix.** The project model marks `test` as a test
  root, so a qualified name in a test module starts at the module, for example
  `test_plugins.TestListeners`. The canary scope pair needs this test root.
- **beets: parked rows.** `find-class-DummyPlugin`, `find-symbol-template-lang-python`,
  `impls-BeetsPlugin`, `hier-sub-BeetsPlugin` and `hier-sub-FieldQuery` are parked with #176:
  a local class gets the qualified name of its function, and a class attribute the name of its
  class. `def-_.map-first-of-many` is parked with #178: the tool gives the first of the
  declarations that "Choose Declaration" lists. No row has `jquery.js` for
  `ide_file_structure` (#177).
- **beets: `file-structure-backbone.js` is not stable.** In 2 of 13 runs on 2026-11-17
  (PyCharm 2026.2.0.1) the outline had 311 lines and not the usual 166: the node at line 648
  was `[method]()`, and it held a second copy of the tree of the file. The two observations
  are in the comments of #177. The expected row holds the tree with 166 lines. Do not bless
  the tree with 311 lines: run the row again.
