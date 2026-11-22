# Captured ground truth: vitess

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.
The observations are from GoLand 2026.3 (263.7307.211) with a window, on a copy of the pin.

- **Usage scopes in Go.** `usage-yyParsePooled-production-scope` and
  `usage-yyParsePooled-test-scope` give `scope_matches_no_files` (these error rows need the
  two-step bless). See the note "Usage scopes in Go" in `../caddy/GROUND-TRUTH.md`.
- **Structure of a Go file.** The result covers the package. `file-structure-tables.go-giant`
  also gives `blockSize` of `index.go`, and `file-structure-vterrors.go` gives the declarations
  of `state.go`. See the note "Structure of a Go file" in `../caddy/GROUND-TRUTH.md`.
- **`ide_search_text` rows.** The search-text rows pin the approved deviation
  "`ide_search_text`: one match for each line, and a label filter" (see "Where a tool differs
  from the IDE on purpose" in
  [docs/ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose)).
  `search-text-allowPartial-code` (12) and `search-text-allowPartial-comments` (3) have no
  match after an escape in a Go string. `search-text-allowPartial` and
  `search-text-allowPartial-strings` are parked (see "Parked rows" below).
- **vitess: the hint "64 implementations" at `Statement`.** `impls-Statement` and
  `hier-sub-Statement` give 59 types. Go to Implementation on `Statement` (`go/vt/sqlparser/ast.go`
  line 41) shows 59 types in its popup, but the code vision hint above the interface says 64.
  The tool gives the result of the popup.
- **vitess: Go to File `primitive.go` gives `primitive_executor.go`.** `find-file-primitive.go`
  gives 4 files, and one of them is
  `go/vt/vttablet/tabletmanager/vdiff/primitive_executor.go`. Go to File `primitive.go` shows
  the same 4 files.
- **vitess: a Go definition into a `.proto` file.** `def-BindVariable-via-import-alias` goes from
  `querypb.BindVariable` (`go/vt/vtgate/engine/primitive.go` line 262) to the message
  `BindVariable` in `proto/query.proto` line 236, not to the generated Go struct. Go to
  Declaration of GoLand opens `query.proto` at line 236 too.
- **vitess: 2 `.proto` symbols in `find-symbol-PingTablet`.** The row gives 20 symbols: 15 Go,
  3 TypeScript and 2 methods `PingTablet` of `.proto` files (`proto/vtadmin.proto`,
  `proto/vtctlservice.proto`). Go to Symbol `PingTablet` shows the
  same 20. The two rows with a language filter give 15 and 3, so the `.proto` symbols are in
  neither of them.
- **vitess: the base usages of `Route.TryExecute`.** `usage-Route.TryExecute-base` gives 64
  usages, and 16 of them have `match` `BASE`: the calls through `Primitive.TryExecute`. Find
  Usages of GoLand also searches the interface method: it shows the notification "Looking for
  usages of the interface methods", and the Find tool window shows "Usages in Project Files 64
  results". See the approved deviation "Find usages: base declarations and marks" in
  [docs/ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose).
- **vitess: a TypeScript scope name two times.** One usage of `usage-fetchClusters-ts` has the
  `enclosingScope` `useClusters`, `useClusters`, `queryFn` (`web/vtadmin/src/hooks/api.ts`). The
  blessed rows of `rolldown` and `lychee` have the same form.
- **vitess: the callees of `Errorf` at level 2.** `hier-callee-Errorf-d2` gives functions of the
  Go SDK at level 2 (`runtime.Callers`, `fmt.newPrinter`). The SDK is the toolchain that
  `go.mod` names (Go 1.26.7, see [notes.md](../../_setup/vitess/notes.md)), so the row changes
  with a new pin.
- **vitess: 10 of 55 candidates.** `usage-TryExecute-bysymbol` gives "55 matches, the first 10
  are listed": the 54 implementations of `Primitive.TryExecute` and the interface method. The
  plugin sorts the candidates before the cut (`SymbolAnchorResolver`), so the row is `exact`.
- **vitess: parked rows.** Each of these rows shows an open defect (see "Parked rows" in
  `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `find-file-vtadmin.d.ts-giant` | #271 | the tool matches the query only against the file name; Go to File also matches a part of the query against the directory path, and it also gives `web/vtadmin/src/vite-env.d.ts` through the folder name `vtadmin` |
  | `search-text-allowPartial` | #309 | the tool drops a word that comes directly after an escape such as `\f` in a Go string; Find in Files with Match case and Words gives 19 matches, the tool 17 |
  | `search-text-allowPartial-strings` | #309 | the same defect: the 2 occurrences after `\f` in the strings of the file descriptors are not in the result |
