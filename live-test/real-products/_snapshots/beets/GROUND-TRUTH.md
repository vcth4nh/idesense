# Captured ground truth: beets

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **beets: a base class through `import beets`.** `beetsplug/playlist.py` imports `beets`
  but not `beets.plugins`, and names the base class `beets.plugins.BeetsPlugin`.
  `beets/__init__.py` has a module `__getattr__`. `def-plugins-via-module-getattr` gives the
  error "Could not resolve symbol definition". In PyCharm, Go to Declaration does nothing at
  that position. The error row needs the two-step bless (see "Rows that pin an expected error"
  in `live-test/CONVENTIONS.md`).
- **beets: 103 subclasses of `BeetsPlugin`.** `impls-BeetsPlugin` and `hier-sub-BeetsPlugin`
  give 103 classes, and a scan of the source finds 105. The two other classes are
  `PlaylistPlugin` (its base is the name of the bullet above) and a local `OtherPlugin` whose
  base is a local class of another method. Choose Implementation of PyCharm says "103 found".
  On PyCharm 2026.3.0.1 at `beets/plugins.py:89:7`, the popup title is "Choose Implementation
  of BeetsPlugin(metaclass=BeetsPluginMeta) (103 found)", and `PlaylistPlugin` is not in the
  list: the filter "PlaylistPlugin" of the popup shows only `SmartPlaylistPlugin` and
  `SubsonicPlaylistPlugin`.
- **beets: 173 usages of `BeetsPlugin`.** Find Usages of PyCharm shows "Usages in Project
  Files (172 usages found)" and a separate group "Dynamic usages in Project Files" with one
  "Untyped (probable) usage" (`playlist.py:75`). The tool gives the sum, 173. The probable
  usage has the `usageType` `REFERENCE` and `match` `DYNAMIC`, and it is the only usage with a
  `match` (#143).
- **beets: a call or a reference that PyCharm does not resolve is in no usage list (#220).**
  Seen on 2026-11-22 with PyCharm 2026.3.0.1 (build 263.7307.329), the interpreter of the
  project (`.venv`, Python 3.12.3) and the scope "Project Files". Instances of this build on the
  same tree gave the windows of this bullet and of the next two bullets: an instance with no
  plugin, and instances with a development build of the plugin code of main @ 2b4c071, which
  also gave the tool answers. No position of this bullet has a row. At each call or reference
  below, Go to Declaration shows the hint "Cannot find declaration to go to" and does not jump,
  and `ide_find_definition` gives the error "Could not resolve symbol definition". Where the
  window showed Find Usages of the method, the list does not have the call or the reference,
  and `ide_find_usages` gives the same list. The observed kinds:
  - A receiver with a type that does not declare the method. Find Usages at
    `beets/importer/tasks.py:544:9` (`handle_created`) lists 4 usages, and not the calls at
    `beets/importer/stages.py:75:30` and `:88:30`. Error Description at `stages.py:75:30` says
    "Unresolved attribute reference handle_created for class BaseImportTask". The hint also
    shows at `beets/ui/commands/help.py:30:44` (`_subcommand_for_name`; Error Description:
    "Member OptionParser of OptionParser | None does not have attribute
    _subcommand_for_name"), at the calls on `self.plugin` at
    `test/plugins/test_lastgenre.py:182:28` (`_fetch_va_genres`), `:325:30` (`_filter_valid`)
    and `:79:28` (`_format_genres`), and at `test/plugins/test_lyrics.py:531:26`
    (`make_search_result`). At these four calls the name has a wavy underline.
  - `self` in a method with a decorator. `convert_item` has the decorator
    `@pipeline.mutator_stage` (`beetsplug/convert.py:418`). Its calls at
    `beetsplug/convert.py:429:21` (`get_item_destination`) and `:567:33` (`_get_art_resize`)
    are not in the lists. The calls in methods with no decorator are in the lists: Find Usages
    at `beetsplug/convert.py:403:9` (`get_item_destination`) lists lines 609 and 708, and at
    `:766:9` (`_get_art_resize`) line 628.
  - A function of a module that comes from `pytest.importorskip`. Find Usages at
    `extra/release.py:250:5` (`changelog_as_markdown`) lists only line 279. The call at
    `test/extra/test_release.py:133:22` is not in the list: its module `release` comes from
    `pytest.importorskip("extra.release")` (line 10).
  - A reference on a `Mock` object. At `test/plugins/test_smartplaylist.py:171:11`, `:206:11`
    and `:249:11`, the reference `i.evaluate_template` gets a `side_effect`, and `i` is a
    `Mock` (line 170) or a `MagicMock` (lines 201 and 242). These are references, not calls.
    Find Usages at `beets/dbcore/db.py:695:9` (`evaluate_template`) lists 16 usages, and not
    these three lines. The name has no wavy underline, and Error Description at `:171:11`
    shows no text.

  The window did not show Find Usages of `_subcommand_for_name`, `_fetch_va_genres`,
  `_filter_valid`, `_format_genres` and `make_search_result`. For these methods, the audit run
  of 2026-11-22 (a development build of the plugin code of main @ d63e284, the same PyCharm
  build) gave `ide_find_usages` lists without these calls. That run also gave the error of
  `ide_find_definition` at `stages.py:88:30`.
- **beets: Find Usages does not list some calls that Go to Declaration resolves (#220).** For
  six methods (no row), the Find Usages window and `ide_find_usages` give the same list, and
  the list does not have calls at which Go to Declaration jumps to the method:
  - `add_all_common_options` (`beets/ui/__init__.py:615:9`): 1 usage. Not listed:
    `beets/ui/commands/list.py:46`, `beetsplug/bareasc.py:75`, `beetsplug/duplicates.py:139`,
    `beetsplug/limit.py:68` and `beetsplug/random.py:73`. The jump was seen at
    `beets/ui/commands/list.py:46:17`.
  - `fetch_genres` (`beetsplug/lastgenre/client.py:69:9`): 1 usage. Not listed:
    `test/plugins/test_lastgenre.py:225` and `:229`. The jump was seen at `:225:29`.
  - `_make_album_match` (`beets/test/helper.py:831:9`): 4 usages. Not listed:
    `test/ui/test_ui_importer.py:66`. The jump was seen at `:66:35`.
  - `create_mediafile_fixture` (`beets/test/helper.py:377:9`): 8 usages. Not listed:
    `test/dbcore/test_query.py:606` and `:610`. The jump was seen at `:606:28`.
  - `dispatch_events` (`beetsplug/bpd/__init__.py:297:9`): 3 usages. Not listed:
    `test/plugins/test_bpd.py:240:20`, `:242:20`, `:261:20` and `:264:20`. The jump was seen
    at each of these positions.
  - `send_command` (`test/plugins/test_bpd.py:158:9`): 32 usages. Not listed: `:201:31`,
    `:558:31`, `:564:32` and `:565:33` of the same file. The jump was seen at each of these
    positions.

  For the first four methods, `ide_find_definition` at the call of the jump returns the
  method. **Not equal to the IDE, a defect of the tool (#322):** at 10 call positions, Go to
  Declaration jumps to the method, and `ide_find_definition` gives the error "Could not resolve
  symbol definition". These are the calls of `dispatch_events` and `send_command` above, a call
  of `send_commands` (`test/plugins/test_bpd.py:438`) and a call of `add_duplicate_action`
  (`test/ui/test_ui_importer.py:98`). #322 has the positions and the detail.
- **beets: 2 dynamic usages of `send_commands`.** Find Usages at
  `test/plugins/test_bpd.py:163:9` (`send_commands`, no row) lists 28 usages in "Usages in
  Project Files", and the group "Dynamic usages in Project Files" > "Untyped (probable) usage"
  with lines 438 and 545. The code vision text of line 163 is "30 usages (2 dynamic)". At both
  lines the receiver is a parameter with no annotation. The tool gives 30 rows: the rows of
  lines 438 and 545 have `match` `DYNAMIC`, and the 28 other rows have no `match`, as for the
  probable usage of `BeetsPlugin` in the bullet "173 usages of `BeetsPlugin`".
- **beets: no callers of a property (#224).** In PyCharm 2026.3.0.1 (build 263.7307.329,
  2026-11-22, a development build of the plugin code of main @ 2b4c071 in the same instance),
  the Call Hierarchy window (callers) of a property shows only the root, with no caller under
  it and no message. Seen at `beets/autotag/match.py:130:9` (`disambig_string`, the decorator
  `@property`) and at `beetsplug/musicbrainz.py:247:9` (`genres_field`, the decorator
  `@cached_property`). Neither position has a row of the suite. `ide_call_hierarchy` gives no
  caller for both.
  `ide_find_usages` gives the 2 reads of each: `beets/ui/commands/import_/display.py:89` and
  `beets/ui/commands/import_/session.py:481` for `disambig_string`, and
  `beetsplug/musicbrainz.py:512` and `:513` for `genres_field`. The code vision of each
  property says "2 usages".
- **beets: no scope for Python subtypes.** `hier-sub-ImportHelper-production-scope` gives the
  same 92 subtypes as a call with no scope. `PySubTypesHierarchyTreeStructure.buildChildren`
  calls `PyClassInheritorsSearch.search(PyClass, boolean)`, which takes no scope (bytecode of
  `intellij.python.community.impl.jar`, build 262.8665).
- **beets: test modules have no `test.` prefix.** A qualified name in a test module starts at
  the module, for example `test_plugins.TestListeners`. The cause is the test root `test` of the
  project model (see "Setup" in [notes.md](../../_setup/beets/notes.md)).
- **beets: 15 callees of `split_into_lines` on PyCharm 2026.3.** `hier-callee-split_into_lines-d1`
  counts one callee for each overload of a type stub that a call resolves to. The Hierarchy
  window of PyCharm 2026.3.0.1 (PY-263.7307.329, callee view) shows the same 15 rows as the
  tool: one row for `str.split` (the overload at `builtins.pyi:619`; the overload for
  `LiteralString` at line 617 is absent), two for `Pattern.finditer` (`re.pyi:181` and `:187`;
  the overload for `Pattern[bytes]` at line 183 is absent), three for `Match.group`, two for
  `str.join` and two for `range.__new__`. The line numbers are those of the stubs that this
  PyCharm build bundles. With PyCharm 2026.2 the tool gave 17 callees; the list of that version
  is not recorded.
- **beets: three lines of `docs/plugins/mbsubmit.rst` have the label `STRING_LITERAL`.** They
  are lines 21, 23 and 25, hyperlink targets (`.. _name: https://...`) that hold the word
  `picard`. `search-text-picard` and `search-text-picard-strings` give them with the label
  `STRING_LITERAL`, and `search-text-picard-code` does not give them. PyCharm PY-263.7307.329,
  in a project that holds copies of these files, with "Match case" and "Words": Find in Files
  lists them with "In String Literals" and not with "Except Comments and String Literals", and
  the Find tool window has them below "Usage in string constants". The other lines of the file
  with the word (17, 80, 82, 83 and 84) have the label `CODE`. The window lists them with
  "Except Comments and String Literals", below "Unclassified".
- **beets: two docstring lines have the label `COMMENT`.** Line 52 of `beets/dbcore/queryparse.py`
  and line 274 of `beets/dbcore/types.py` are lines of a docstring that hold the word
  `backslash`. `search-text-backslash` and `search-text-backslash-comments` give them the label
  `COMMENT`, and `context: "comments"` returns them. PyCharm PY-263.7307.329, in a project that
  holds copies of these files, with "Match case" and "Words": Find in Files lists both lines
  with "In Comments" and with "In String Literals", and the Find tool window has them below
  "Usage in comments". In that IDE the tool also returns both lines with `context: "strings"`,
  with the label `COMMENT`. The product has no row with that filter for this word.
- **beets: parked rows.** `find-class-DummyPlugin`, `find-symbol-template-lang-python`,
  `impls-BeetsPlugin`, `hier-sub-BeetsPlugin` and `hier-sub-FieldQuery` are parked with #176:
  a local class gets the qualified name of its function, and a class attribute the name of its
  class. `def-_.map-first-of-many` (`_.map` in `beetsplug/web/static/beets.js`) is parked with
  #178: the tool gives the first of the declarations that "Choose Declaration" lists.
  `file-structure-backbone.js` is parked with #177 (see the next note). No row has `jquery.js`
  for `ide_file_structure` (#177): the tool gives no answer for
  `beetsplug/web/static/jquery.js` and leaves the walk at work in the IDE.
- **beets: `file-structure-backbone.js` differs between equal runs.** In 2 of 13 runs on
  2026-11-17 (PyCharm 2026.2.0.1) the outline had 311 lines and not the usual 166: the node at
  line 648 was `[method]()`, and it held a second copy of the tree of the file. The two
  observations are in the comments of #177. The expected row holds the tree with 166 lines.
