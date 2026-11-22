# lazygit

- Repository: https://github.com/jesseduffield/lazygit
- Pin: tag `v0.64.0`, commit `aee0e40ec1235476e9328678f0f3e2462576b9ae`, committed 2026-08-04
- License: MIT
- IDE: GoLand (port 29174)
- Language level: `go 1.25.0` in `go.mod`

## Setup

Run `bootstrap.sh`. It checks the Go version against `go.mod`, checks that `vendor/` agrees
with `go.mod`, fills the module cache with the `go.mod` files of the module graph, and writes
three IDE project files when they are absent: `.idea/workspace.xml` (GOROOT),
`.idea/modules.xml` and `.idea/lazygit.iml`. There is no lockfile to create: `go.sum` and
`vendor/modules.txt` are committed.

The dependencies are committed. `vendor/` holds 864 of the 1,918 Go files and 74% of the Go
lines (390,255 of 528,882). `vendor/modules.txt` lists 64 modules. The canary row
`canary-def-logrus.Entry-into-vendor` resolves into `vendor/github.com/sirupsen/logrus`. The pin
commits that folder, and `vendor/modules.txt` and `go.sum` pin its version.

Facts about the project model, seen on GoLand 2026.3 (263.7307.211):

- **Vendor mode.** GoLand resolves imports into `vendor/`. It is the default: the project
  setting `VgoProject` has `autoVendoringMode` and `integrationEnabled` set to true, and a
  first open writes no such setting (`com.goide.vgo.configuration.VgoProjectSettings` in
  `plugins/go-plugin/lib/modules/intellij.go.impl.jar`). Go to Declaration on `logrus.Entry`
  opens `vendor/github.com/sirupsen/logrus/entry.go`, also when the module cache holds the
  same version of the module.
- **No module source.** At each open GoLand runs
  `go list -modfile=<copy of go.mod> -m -json -mod=mod all`. This command needs the `go.mod`
  file of each module of the graph (125 modules, the main module included). On a cold module
  cache it downloads these files and the checksum database tiles, but no module source.
  GoLand runs no `go mod download` for this product ("No new dependencies downloaded" in
  `idea.log`). The bootstrap runs the same command, so the open needs no network.
- **The module cache is not indexed.** GoLand puts each module of the graph that has a folder
  in the module cache into its model (`Summary for VgoDependencyEntity: ...
  fromGoModulesRoot=<n>` in `idea.log`), and External Libraries → Go Modules lists these
  modules. With a `vendor/` folder, GoLand marks each of these dependencies as internal
  (`VgoWorkspaceModelUpdater`: `VgoStandaloneModule.hasVendor` gives `setInternal(true)`), and
  `VgoDependencyWorkspaceFileIndexContributor` registers no file set for an internal
  dependency. The indexing diagnostics agree: a scan covers the module `lazygit`, `vendor/`
  and the Go SDK, and no folder of the module cache. So no search finds a declaration in the
  module cache, also not Go to Super. A module that another product puts into the shared
  module cache cannot change a row. With all 124 modules of the graph in the module cache,
  each row gave the same result as with fewer.
- **`vendor/` is outside the project scope of a search.** Go to Class and Go to File with the
  scope "Project Files" show no vendored type and no vendored file. The tools give the same.
- **IDE files.** GoLand 2026.3 wrote a module file with the component `Go` and no component
  `GoModuleSettings`, and no vendoring setting. The bootstrap writes the same files.

The rows depend on the Go SDK of the fleet GoLand (the GOROOT that `go env GOROOT` gives at
the bootstrap), as the rows of `caddy` do. `hier-callee-computeMigratedConfig-d2` names
functions of the package `reflect`.

## Measured

GoLand 2026.3 (263.7307.211), `-Xmx2048m`, plugin 2.1.1-dev.23, 2026-11-22. The harness polls
every 5 seconds, so the switch time has that resolution.

| Item | Value |
|---|---|
| Switch to `lazygit`: stop GoLand, mark the projects, start | 12 to 24 s |
| Ready after the switch | 0 s |
| First indexing: 10,050 files scanned, 2,319 indexed | 21 s from project open to smart mode |
| `go list -m -json all` at each open, module cache filled by the bootstrap | 0.2 to 0.3 s |
| End of the Go model (last registration of `vendor/`) after the first smart mode | 0.3 s at the first open; 7 to 13 s at three of four later opens |
| Go fixture rows while `lazygit` is open | 106 passed (after the first open, and again after three switches); 108 passed with plugin 2.1.1-dev.24 |
| Resident memory of GoLand, fixture only | 2075 MB |
| Resident memory, fixture plus `lazygit`, after the open | 2984 MB |
| Used heap after a full collection | 283 MB |
| Size of the checkout with `vendor/` | 29 MB |
| Module cache data that the bootstrap adds (`go.mod` files and checksum tiles) | about 0.8 MB |
| Run of the 63 rows, product open before | 6 to 10 s |
| Run of the rows directly after a switch | 47 s (63 rows), 19 s (64 rows) |

The used heap stays far below 1200 MB (60% of the limit), so GoLand keeps `-Xmx2048m`.

Facts about the open:

- At the first open GoLand registers `vendor/` (`GoVendorWorkspaceFileIndexContributor`)
  0.3 s after the last smart mode. At a later open it registers `vendor/` once before the
  first smart mode and once more 7 to 13 s after it, with `go list` and a short second dumb
  mode. One definition into `vendor/` between the two failed with "Could not resolve symbol
  definition", while `ide_index_status` reported smart mode; 10 s later the same call
  resolved. The index status alone is thus no safe readiness signal; the canary row
  `canary-def-logrus.Entry-into-vendor` is.
- A later open scans 10,051 files and indexes none (four opens).

## Import check

Done on 2026-11-22 with plugin 2.1.1-dev.23. The product is accepted.

| Call | Result |
|---|---|
| `ide_find_class`, query `IController` | the interface `IController`, `pkg/gui/types/context.go:271` |
| `ide_find_definition`, `pkg/common/common.go:14:21` | `vendor/github.com/sirupsen/logrus/entry.go:46` |
| `ide_find_usages`, `pkg/integration/components/test.go:119:6`, `pageSize` 100 | 100 usages, `hasMore` true, `totalCollected` 500 (the collection limit) |
| `ide_type_hierarchy`, `pkg/gui/types/context.go:271:6` | 45 subtypes (`IBaseContext`: 33) |
| `ide_file_structure`, `pkg/gui/controllers/branches_controller.go` | a structure of 82 KB: the package `controllers` |

Comparison with GoLand itself. A second GoLand with a window opened a copy of the pin that had
no IDE files, so that GoLand made the project model by itself. The bootstrap writes the IDE
files that this GoLand wrote.

- Go to Declaration on `logrus.Entry` (`common.go:14`) opens
  `vendor/github.com/sirupsen/logrus/entry.go` at line 46, as the tool.
- Go to Implementation on `IController`: "Type 'IController' Implemented in 45 Types". The
  tool gives the same 45 types.
- Find Usages on the vendored `logrus.Entry`: "Usages in Project Files 29 results". The tool
  gives 29 usages.
- Go to Class `Entry` with "Project Files" shows no vendored type, and the tool gives none.

The notes on the results of the rows are in
[../../_snapshots/lazygit/GROUND-TRUTH.md](../../_snapshots/lazygit/GROUND-TRUTH.md).
