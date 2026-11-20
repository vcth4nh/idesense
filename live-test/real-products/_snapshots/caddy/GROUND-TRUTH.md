# Captured ground truth: caddy

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **No caller through an interface.** `ide_call_hierarchy` shows no caller for a Go method
  that is called only through an interface value (`hier-caller-App.Provision`). The Hierarchy
  window of GoLand shows the same in its default state: its toggle "Respecting Interface
  Calls" is off by default, and the tool has no parameter for it (#218).
- **Build constraints.** A declaration in a file that the build constraints exclude has no
  usage (`usage-FastAbs-decl-windows`, a `_windows.go` file on a Linux host). GoLand says
  "Nothing found" and shows a banner about the OS mismatch. The row depends on the OS of the
  IDE host.
- **One match for each line.** `ide_search_text` returns one match for a line that has the
  word two times.
- **`CODE` in a file that is no program source.** `search-text-tailscale-code` has matches in
  `go.mod`, `go.sum` and an HTML file. The label of a match that is not in a comment and not
  in a string literal is `CODE`, and the `context` filter keeps the matches by this label.
- **More types than methods.** `impls-Validator` has 24 types and `impls-Validator.Validate`
  has 21 methods. Three types get the method from an embedded type, and that method is
  already in the list. With the library scope the two anchors gave 1,947 types and 1,933
  methods at v2.11.7; the `shape` rows pin only the first pages.
- **Library supertypes.** The supertypes of a Go struct include library interfaces that it
  satisfies by structure (`hier-super-caddyhttp.App-byname`).
- **Usage scopes in Go.** `ide_find_usages` with `project_production_files` or
  `project_test_files` gives `scope_matches_no_files`: a Go project has no source roots, and
  the Find Usages dialog of GoLand has no such scope. The Go fixture pins the same
  (`usage-Circle-struct-production-scope` in
  `live-test/fixtures/_snapshots/go/expected/ide_find_usages.jsonl`). The hierarchy tools
  accept the scope `test` through the Go test file names, and their scope `production` is
  empty. On `Module`, `canary-hier-sub-Module-test-scope` gives 8 subtypes and
  `hier-sub-Module-production-scope` gives none.
- **Qualified method name.** `ide_find_symbol` finds nothing for `package.Type.Method`
  (`find-symbol-caddyhttp.App.Provision-qualified`). The Go to Symbol popup of GoLand finds
  nothing too. `Type.Method` works.
- **Structure of a Go file.** The result covers the package (see the note "Go `file_structure`
  is package-scoped" in `live-test/fixtures/_snapshots/go/GROUND-TRUTH.md`).
  This is the default of the Structure tool window. The File Structure popup lists only the
  file.
- **Go SDK methods.** `super-responseRecorder.Write` lists interface methods of the Go SDK.
  The row depends on the SDK version of the IDE host.
- **caddy: the usages of `APIError.Error` are the calls of `error.Error`.**
  `usage-APIError.Error-library-base` gives 89 usages, all with `match` `BASE`. The base
  declaration is `builtin.error.Error` of the Go SDK (`builtin.go, library` in the note). Each
  usage is a call of `Error()` on a value of the type `error`. The 3 text matches that are no
  usage: `admin.go:1396` (a comment), `caddyconfig/configadapters.go:74` and
  `modules/caddyhttp/vars_test.go:170` (calls on a type with its own `Error` method).
- **caddy: 3 literal keys are no usages of the interface `CA` (#213).**
  `usage-caddytls.CA-field-keys` (`modules/caddytls/capools.go:37:6`) gives 36 usages: 18
  code usages and 18 `COMMENT` usages. The search of GoLand also returns 3 composite literal
  keys `CA:`, at `modules/caddytls/acmeissuer.go:256:3`, `acmeissuer_test.go:19:3` and
  `automation.go:484:4`. Each key names a struct field `CA`: `ide_find_definition` at the
  first position gives the field `CA` of `certmagic.ACMEIssuer`, not the interface. The tool
  leaves the 3 keys out, and the `notes` entry gives the count 3 (see the note on #213 in
  `live-test/fixtures/_snapshots/go/GROUND-TRUTH.md`).
  The interface `caddyhttp.Handler` (`modules/caddyhttp/caddyhttp.go:65:6`, no row) has 2
  such keys: `Handler:` in an `http.Server` literal and in an `http3.Server` literal.
