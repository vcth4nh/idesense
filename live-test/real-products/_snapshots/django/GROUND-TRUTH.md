# Captured ground truth: django

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.
The window observations are from PyCharm 2026.3.0.1 (PY-263.7307.329) on 2026-11-22.

- **django: no target for `objects` of a model.** `def-objects-dynamic-manager`
  (`tests/basic/tests.py:54:34`, `Article.objects`) gives the error "Could not resolve symbol
  definition". In PyCharm, Go to Declaration does nothing at that position, and the inspection
  says "Unresolved attribute reference `objects` for class `Article`". The log of that PyCharm
  lists the plugin `JetBrains Ultimate` (`com.intellij.modules.ultimate`) as disabled. The error
  row needs the two-step bless (see "Rows that pin an expected error" in
  `live-test/CONVENTIONS.md`).
- **django: no scope for Python subtypes.** `hier-sub-BaseCache-production-scope` gives the
  same 12 subtypes as a call with no scope, the classes in `tests/cache/` too.
  `PySubTypesHierarchyTreeStructure.buildChildren` calls
  `PyClassInheritorsSearch.search(PyClass, boolean)`, which takes no scope, and
  `HierarchyTreeStructure.getChildElements` adds no filter after `buildChildren` (bytecode of
  `intellij.python.community.impl.jar` and `intellij.platform.lang.impl.jar`, build 263.7307.329).
  The beets note on Python subtypes gives the same for build 262.8665.
- **django: two callees `str.format` of `duration_string`.** `hier-callee-duration_string-d1`
  gives 3 callees: `_get_duration_components` and two `str.format(self, *args, **kwargs)`, one
  for each overload of the stub that the three calls resolve to (`builtins.pyi` lines 524 and
  526; the snapshot keeps no line of a library file, so the two items are equal). The Hierarchy
  window (callee view) shows the same 3 rows, each `str.format` row with "(3 usages)".
- **django: test modules have no `tests.` prefix.** A qualified name in a test module starts at
  the module below `tests`, for example `cache.closeable_cache.CacheClass`. The cause is the
  test root `tests` of the project model (see "Setup" in
  [notes.md](../../_setup/django/notes.md)). The test runner of Django puts `tests` on
  `sys.path` in the same way.
- **django: no usage of `reset_cache`.** `usage-reset_cache-empty` gives 0 usages. The function
  is a signal receiver (`@receiver(setting_changed)` in
  `django/utils/translation/trans_real.py`), and no file names it.
- **django: `self` in the structure of `Operation` differs between IDE sessions.** The outline
  of `django/db/migrations/operations/base.py` lists `self (line 52)` under `Operation` in some
  PyCharm sessions and not in others. Line 52 is `self = object.__new__(cls)` in `__new__`. On
  the fleet: not in 2 sessions, in 2 sessions; the result stays the same inside one session. In
  a PyCharm with a window and plugin 2.1.1-dev.23 (3 sessions, 8 looks), the Structure window
  and `ide_file_structure` agreed at each look: `self` in sessions 1 and 2, no `self` in session
  3. The tool passes the structure model of the IDE, and `PyStructureViewElement` takes the
  attributes from `PyClass.getInstanceAttributes()` (bytecode of
  `intellij.python.community.impl.jar`, build 263.7307.329). The row
  `file-structure-operations.base.py` is not in the input files for this reason.
- **django: parked rows.** `impls-Field`, `hier-sub-Field`, `find-class-Node`,
  `find-class-QuSe-fuzzy` and `hier-sub-BaseCommand-production-scope` are parked with #176: a
  class declared in a function gets the qualified name of the function. The rows
  `impls-BaseDatabaseOperations`, `hier-sub-BaseCache-production-scope` and
  `find-class-DaOp-fuzzy` have no such class and are blessed. `def-DEBUG-via-lazy-settings`
  (`settings.DEBUG`: the tool gives an error, "Choose Declaration" lists 4 results by name only)
  and `def-jQuery-into-vendored-js` (the tool gives the first of 2 declarations of `jQuery`) are
  parked with #178. `usage-get_valid_filename` is parked with #186: the usage in the doctest of
  `django/utils/text.py:271` comes with the path `/text.py` and line 1, and the snapshot form
  would keep only `text.py`.
