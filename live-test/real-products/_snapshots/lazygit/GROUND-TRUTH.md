# Captured ground truth: lazygit

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.
The observations are from GoLand 2026.3 (263.7307.211) with a window, on a copy of the pin.

- **lazygit: `vendor/` is outside "Project Files".** `find-class-Entry-vendored` gives no
  class, `find-file-entry.go-vendored` gives no vendored file, and
  `find-file-modules.txt-vendored` gives no file (the only `modules.txt` is
  `vendor/modules.txt`). Go to Class `Entry` and Go to File `entry.go` with the scope "Project
  Files" show no vendored item either. `search-text-humanlog` gives 14 matches in 6 files and
  none in `vendor/`: Find in Files "In Project" says "14 matches in 6 files". A definition still
  resolves into `vendor/` (`canary-def-logrus.Entry-into-vendor`), and a usage search on a
  vendored declaration finds the project usages (`usage-logrus.Entry-from-vendor`, 29 usages;
  Find Usages says "Usages in Project Files 29 results").
- **lazygit: no fuzzy class for `BrCtrl`.** `find-class-BrCtrl-fuzzy` gives no class. Go to
  Class `BrCtrl` finds nothing, also with "All Places". The query `BrCon` gives the same 7 types
  in Go to Class and in the tool.
- **lazygit: the hint "49 implementations" at `IController`.** `canary-impls-IController` and
  `hier-sub-IController` give 45 types. The inlay hint at `type IController interface` says
  "49 implementations", but Go to Implementation from the gutter says "Type 'IController'
  Implemented in 45 Types". The tool gives the result of the popup. No interface embeds
  `IController`, and all 45 types are structs. The source of the number 49 is not known.
- **lazygit: the structure of a generated file.** `file-structure-test_list.go` gives the
  variable `tests` and the function `GetTests` of `tests.go`. The File Structure popup with
  "Show package structure" on gives the same 2 items; with it off, only `tests`. The Go
  structure covers the package (see the note "Structure of a Go file" in
  `../caddy/GROUND-TRUTH.md`, and #149).
- **lazygit: Go scopes.** `usage-NewChangesSet-production-scope` and
  `usage-NewChangesSet-test-scope` give `scope_matches_no_files` (these error rows need the
  two-step bless). See the note "Usage scopes in Go" in `../caddy/GROUND-TRUTH.md`.
- **lazygit: qualified method name.** `find-symbol-controllers.BranchesController.GetKeybindings-qualified`
  gives no symbol, and `find-symbol-BranchesController.GetKeybindings-qualified` gives 2. See
  the note "Qualified method name" in `../caddy/GROUND-TRUTH.md`.
- **lazygit: the order of `ide_find_file`.** For `options.go`, `keybindings.go` and `entry.go`,
  the tool and Go to File give the same files in a different order (#272). Go to File puts a
  name that starts with the query first, and the tool does not. No row pins the order:
  `find-file-options.go` and `find-file-entry.go-vendored` are `exact` rows, which sort the
  lists, and `find-file-keybindings.go-paged` is a `shape` row.
- **lazygit: parked rows.** Each of these rows shows an open defect (see "Parked rows" in
  `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `find-file-test_list.go`, `find-file-shared.go-paged` | #271 | the tool matches the query only against the file name; Go to File also matches a part of the query against the directory path, and it gives 2 more files for `test_list.go` and 1 more for `shared.go` |
