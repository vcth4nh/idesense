# vitess

- Repository: https://github.com/vitessio/vitess
- Pin: tag `v24.0.3`, commit `33f1e705bbfa51ece6e62c8439ddd5db2dc1752e`, committed 2026-09-03
- License: Apache-2.0
- IDE: GoLand (port 29174)
- Language level: `go 1.26.7` in `go.mod`

## Setup

Run `bootstrap.sh`. It gets the Go toolchain of `go.mod`, downloads each module of the module
graphs of the six `go.mod` files, and writes three IDE project files when they are absent:
`.idea/workspace.xml` (GOROOT), `.idea/modules.xml` and `.idea/vitess.iml`. There is no
lockfile to create: each `go.mod` has its `go.sum`. When no module is absent, the bootstrap
needs no network and prints nothing about the module cache.

The libraries of the project. At each open GoLand runs
`go list -modfile=<copy of go.mod> -m -json -mod=mod all` in the folder of each `go.mod`, and
`go mod download -json -x` there (`GoExecutor` lines in `idea.log`). It makes a library for
each module of the graph and gives it the folder of the field `Dir` as its root
(`GoListOutputParser.readDependency`, `VgoDependencyImpl`, in
`plugins/go-plugin/lib/modules/intellij.go.impl.jar`, GoLand 263.7307.211). `go list` gives a
`Dir` only for a module that has a folder in the module cache. `go mod download` with no
argument downloads only the requirements of `go.mod`. So the External Libraries node also
shows each module of the graph that another checkout downloaded: on a throwaway GoLand,
`Go Modules <vitess.io/vitess>` lists `github.com/agnivade/levenshtein v1.2.1`, which is not
in `go.mod` or `go.sum` of vitess, and its folder came from an earlier checkout. The bootstrap
runs `go mod download all` for each `go.mod`, so that the libraries come from vitess only.

At the pin the six graphs have 1,203 modules together (the root module 865). The bootstrap
also checks that after the download no module of a graph has no folder.

The bootstrap does not install the Node packages of `web/vtadmin`. No row needs them: the
TypeScript rows resolve relative imports and `src/proto/vtadmin.d.ts`, and these need no
package.

Facts of the checkout at the pin:

- 3,157 Go files with 1,505,697 lines. 95 files with 375,055 lines (25%) have the header
  `// Code generated ... DO NOT EDIT.`. 1,186 test files have 464,248 lines.
- No `vendor/` and no `go.work`. Six `go.mod` files: the root module and five tool modules
  (`tools/gofumpt`, `tools/goimports`, `tools/golangci-lint`, `tools/gotestsum`,
  `tools/goyacc`). A tool module has only `go.mod` and `go.sum`, and no Go file.
- The root `go.mod` has 267 requirements. The tool modules have 236 requirements together.
- `web/vtadmin` is a TypeScript part with its own `package.json` and `package-lock.json`: 168
  TypeScript files. 19,552 lines are hand-written, and `src/proto/vtadmin.d.ts` has 83,723
  lines.
- Four files are above 2.5 MB: `web/vtadmin/src/proto/vtadmin.js` (9.5 MB),
  `go/mysql/collations/vindex/collate/tables.go` (4.9 MB),
  `web/vtadmin/src/proto/vtadmin.d.ts` (3.6 MB) and
  `go/mysql/collations/colldata/mysqlucadata.bin` (2.5 MB). GoLand 2026.3 still parses and
  indexes `tables.go` and `vtadmin.d.ts`: above `idea.max.intellisense.filesize` (2500 KB) the
  editor shows a notice and runs no inspection, but Go to Declaration goes into both files.
- The interface `Primitive` (`go/vt/vtgate/engine/primitive.go:258`) has an unexported method,
  so only types of the package `engine` implement it. 50 files of that package that are no test
  files implement `TryExecute`.

The Go toolchain. `go.mod` needs Go 1.26.7. The bootstrap runs `go env GOROOT` with
`GOTOOLCHAIN=go1.26.7`: the go command downloads the toolchain module
`golang.org/toolchain@v0.0.1-go1.26.7.linux-amd64` into the module cache and checks it against
the checksum database. On the disk the toolchain is the folder
`$(go env GOMODCACHE)/golang.org/toolchain@v0.0.1-go1.26.7.linux-amd64`. The bootstrap sets
`GOTOOLCHAIN` only in its own environment and does not run `go env -w`, so no global Go setting
changes: the default Go of the host stays, and the rows of `caddy` and `lazygit` keep their
SDK. The IDE project file `.idea/workspace.xml` names that toolchain folder as the GOROOT of the
project (`<component name="GOROOT" url="file://...">`).

## Measured

GoLand 2026.3 (263.7307.211), `-Xmx2048m`, plugin 2.1.1-dev.31, 2026-11-22. The harness
polls every 5 seconds, so the switch time has that resolution.

| Item | Value |
|---|---|
| Switch to `vitess`: stop GoLand, mark the projects, start | 16 s (first open), 11 s (second open) |
| Ready after the switch, as the harness reports it | 0 s, but see the first open below |
| First indexing: 12,789 files scanned (12,413 indexed), then 90,462 scanned (81,667 indexed) for the 1,298 module roots | 121 s from the project open to smart mode |
| Later open: 103,252 files scanned, 0 indexed | 4.6 s from the project open to smart mode |
| `go list -m -json all` of the root module at each open | 0.3 to 0.5 s |
| Module roots of the project (`Summary for VgoDependencyEntity` in `idea.log`) | `nullRoots=0, fromGoModulesRoot=1298` |
| Go fixture rows while `vitess` is open | 108 passed |
| Resident memory, fixture plus `vitess`, 22 s after smart mode | 4,328 MB, and 3,508 MB after a full collection |
| Used heap after a full collection | 244 MB 22 s after smart mode (first open); 619 MB (30%) after one run of the rows and six hand calls (second open) |
| Size of the checkout | 99 MB |
| Module cache data that the bootstrap added, 2026-11-22 | 1.71 GB in 137 s at the first run (the toolchain and the 198 absent requirements of the root `go.mod`); 0.34 GB for the requirements of the tool modules (GoLand downloaded them at the first open of a throwaway; the bootstrap now does it); 2.18 GB in 28 s for the 663 absent modules of the full graphs |
| Run of the 72 rows, product open before | 18 to 19 s |
| Run of the 72 rows directly after a switch | 46 s |
| `ide_file_structure` of `go/mysql/collations/vindex/collate/tables.go` (4.9 MB) | 1.2 to 3.2 s, 690 characters |
| `ide_file_structure` of `web/vtadmin/src/proto/vtadmin.d.ts` (3.6 MB), no row | 12.1 s, 1,326,594 characters |

The used heap stays far below 1200 MB (60% of the limit), so GoLand keeps `-Xmx2048m`.

Facts about the open:

- At the first open the harness reported "ready 0s" too early, a case of #308. `idea.log`
  shows `exit dumb mode [vitess]` 0.2 s after the project open, `enter dumb mode [vitess]`
  4.2 s later (the indexing of the project files and then of the 1,298 module roots), and the
  last `exit dumb mode [vitess]` 121 s after the project open. So after an open, wait for the
  last line `exit dumb mode [vitess]`, about 2 minutes at a first open, before a run of the
  rows. The check of the harness came in the gap of 4.2 s between the two dumb modes.
- At a later open GoLand scans the same files and indexes none. A dumb mode of 0.05 s follows
  4 s after the first smart mode.
- A module of a graph with no folder in the module cache gets no library root, and the log
  shows a `nullRoots` value above 0. After the bootstrap the log shows `nullRoots=0`.
- The file watcher of GoLand gets the checkout (1,199 folders without `.git`) and the module
  folders of the graphs as roots. The 1,298 module roots of the log are the modules of the six
  graphs (865, 382, 20, 13, 10 and 8), in 1,203 different folders with 30,432 folders below
  them. On Linux, inotify needs one watch for each folder.
