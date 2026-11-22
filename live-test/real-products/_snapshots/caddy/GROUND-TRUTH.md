# Captured ground truth: caddy

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **No caller through an interface.** `ide_call_hierarchy` shows no caller for a Go method
  that is called only through an interface value (`hier-caller-App.Provision`). The Hierarchy
  window of GoLand shows the same in its default state: its toggle "Respecting Interface
  Calls" is off by default, and the tool has no parameter for it (#218).
- **Build constraints.** The declaration `FastAbs` in a file that the build constraints
  exclude has no usage (`usage-FastAbs-decl-windows`, a `_windows.go` file on a Linux host).
  GoLand says "Nothing found" and shows a banner about the OS mismatch. The row depends on the
  OS of the IDE host.
- **Build constraints: usages of a declaration in an excluded file.** The result is not always
  empty. `listen.go` and `listen_test.go` have the constraint `!unix || solaris`, so a Linux
  host excludes both files. In GoLand 2026.3 (build 263.7307.211, Linux host, v2.11.7, seen
  2026-11-22), the editor of `listen.go` shows the banner "'listen.go' is ignored by the build
  tool because of the OS mismatch", and `listen_test.go` shows the same banner with its own
  name. The Find tool window has no such notice. Find Usages at `listen.go:118:6`
  (`fakeCloseListener`, no row) lists 3 usages, all in `listen.go`: line 107 (group "Struct
  initialization"), lines 128 and 177 (group "Receiver"). It does not list the uses at
  `listen_test.go:39` and `:45`. Find Usages at `listen.go:128:31` (its method `Accept`, no
  row) lists 9 calls in other files (group "Call"), the usages of the interface method
  `net.Listener.Accept`. It does not list the call at `listen_test.go:59`. In the audit run of
  2026-11-22 (a development build of the plugin code of main @ d63e284), `ide_find_usages` gave
  the same lines: `listen.go:107`, `:128` and `:177` for `fakeCloseListener`, and 9 rows for
  `Accept`, each with the mark `BASE`, none in `listen_test.go`. These results depend on the
  OS of the IDE host.
- **Implementations of an interface in an excluded file.** Go to Implementation(s) at
  `listen.go:124:6` (the interface `canSetKeepAliveConfig`, no row) in GoLand 2026.3 opens the
  popup "Choose Implementation of canSetKeepAliveConfig (5 found)". It lists `TCPConn`
  (`net/tcpsock.go`), `keepAliveConn`
  (`go.etcd.io/etcd/client/pkg/v3/transport/keepalive_listener.go`), `tcpConnWithoutReadFrom`
  and `tcpConnWithoutWriteTo` (`net/net.go`), and `testMockTCPConn`
  (`net/http/transport_test.go`): no type of the project. The key file of the audit has two
  implementers in files that Linux compiles:
  `modules/caddyhttp/reverseproxy/httptransport.go:936` and
  `modules/caddytls/matchers_test.go:305`. Each embeds `*net.TCPConn`. In the audit run of
  2026-11-22, `ide_find_implementations` with its default scope `project_files` gave an empty
  result.
- **Go to Declaration at a use in an excluded file.** In GoLand 2026.3, Go to Declaration or
  Usages at `listen_test.go:39:23` and `:45:24` (`fakeCloseListener`, no row) and at
  `service_windows.go:47:9` (`notify.SetGlobalStatus`, no row) shows the hint "Cannot find
  declaration to go to" and does not jump. Go to Declaration at `listen_test.go:45:24` shows
  the same hint. `SetGlobalStatus` has its only declaration in
  `notify/notify_windows.go:31`. Each of the two files shows the banner about the OS mismatch.
  In the audit run of 2026-11-22, `ide_find_definition` at these uses gave the error "Could
  not resolve symbol definition". The columns are those of a tool call: GoLand counts the tab
  of the indent as 4 columns (see "Columns" in
  [live-test/README.md](../../../README.md#throwaway-ide-with-a-display)).
- **`ide_search_text` rows.** The search-text rows pin the approved deviation
  "`ide_search_text`: one match for each line, and a label filter" (see "Where a tool differs
  from the IDE on purpose" in
  [docs/ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose)).
  `search-text-tailscale-code` has matches in `go.mod`, `go.sum` and an HTML file. The label
  of a match that is not in a comment and not in a string literal is `CODE`.
- **More types than methods.** `impls-Validator` has 24 types and `impls-Validator.Validate`
  has 21 methods. Three types get the method from an embedded type, and that method is
  already in the list. With the library scope the two anchors gave 1,947 types and 1,933
  methods at v2.11.7; the `shape` rows pin only the first pages.
- **Library supertypes.** The supertypes of a Go struct include each library interface that
  it satisfies by structure (`hier-super-caddyhttp.App-byname`). Go to Super of GoLand
  searches each module of the graph that has a folder in the module cache. This includes a
  module that no package of caddy imports, and the `testdata` folders of a module. GoLand
  excludes the `testdata` folders of the Go SDK (registry key
  `go.sdk.exclude.testdata.directories`, default true). At v2.11.7 the row has 11 supertypes: 5
  interfaces of caddy and 6 library interfaces. `ca.Stopper` declares only `Stop() error`, and
  each of the 5 others declares only `Validate() error`. The Go type checker
  (`types.Implements` on `*caddyhttp.App`) confirms each one. The row needs the full module
  graph in the module cache (see [notes.md](../../_setup/caddy/notes.md)).
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
  `usage-APIError.Error-library-base` gives 89 usages, all with `match` `BASE`. The note of
  the row names 3 base declarations: `builtin.error.Error` of the Go SDK (`builtin.go,
  library`), and two interfaces in the testdata of the module `github.com/uudashr/iface`
  (`i.MyError` in `i.go`, `j.error` in `j.go`). Each of the two declares only
  `Error() string`. Each usage is a call of `Error()` on a value of the type `error`. The row
  has the default scope `project_files`, so the result has no usage in a library. The 3 text
  matches that are no usage: `admin.go:1396` (a comment), `caddyconfig/configadapters.go:74`
  and `modules/caddyhttp/vars_test.go:170` (calls on a type with its own `Error` method).
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
- **caddy: GoLand and the tool list 3 keys of an embedded field as usages of `caddy.Context`
  (#321).** Find Usages at `context.go:46:6` (`caddy.Context`, no row) in GoLand 2026.3 lists
  345 results in 8 groups: "Field declaration" 18, "Parameter declaration" 165, "Receiver" 21,
  "Return type" 10, "Struct initialization" 118, "Unclassified" 6, "Usage in comments" 3 and
  "Variable declaration" 4. "Unclassified" lists `admin_test.go:993`, `admin_test.go:1220`
  and `context.go:673`. Each of the three lines is the key `Context:` of a `Context{...}`
  literal whose type name is on the line before. The key names the embedded field
  `context.Context` (`context.go:47`), a type of the Go SDK with the same name. The other 3
  rows of "Unclassified" are such keys on a line that also has the type name `Context{`.
  In the audit run of 2026-11-22, `ide_find_usages` gave 345 rows too, with the three lines
  and no mark on them. The key file of the audit comes from the Go type checker, which
  resolves each key to the embedded field, so the audit gives the three lines as false lines.
  The tool leaves out a key of a named field (see the bullet on #213 above), but a key of an
  embedded field stays, also when the field has another type with the same name. Two more
  types have such keys, and the audit gives these keys as false lines of the tool too. The
  window was not observed for them: `caddytls.Certificate`
  (`modules/caddytls/pemloader.go:83`, the embedded field `tls.Certificate`) and
  `caddyhttp.ResponseRecorder` (10 keys in `modules/caddyhttp/idletimeout_test.go`, the
  embedded field `*httptest.ResponseRecorder` of three test types).
