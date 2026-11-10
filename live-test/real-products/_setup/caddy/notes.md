# caddy

- Repository: https://github.com/caddyserver/caddy
- Pin: tag `v2.11.7`, commit `72dd0fb067f6d7826c7f79907670ba4a713bfe37`, committed 2026-10-03
- License: Apache-2.0
- IDE: GoLand (port 29174)
- Language level: `go 1.26.0` in `go.mod`

## Setup

Run `bootstrap.sh`. It checks the Go version, downloads the modules, and writes three
IDE project files when they are absent: `.idea/workspace.xml` (GOROOT), `.idea/modules.xml`
and `.idea/caddy.iml`. There is no lockfile to create: `go.sum` is committed.

The IDE files are necessary. At its start GoLand opens only a marked project that has an
`.idea` folder, and it gives such a project no module by itself. Without the module file
the project opens with an empty model: 311 files scanned, no Go module, no class found.

## Measured

GoLand 2026.2 (262.8665), `-Xmx2048m`, 2026-11-10. The harness polls every 5 seconds, so
the switch time has that resolution.

| Item | Value |
|---|---|
| Switch: stop GoLand, mark the projects, start, both projects listed | 11 s |
| Stop of GoLand after SIGTERM | 2 s |
| Ready after the switch, product indexed before | 0 to 5 s |
| First indexing: 690 project files, then 16,329 files with the dependencies | 34 s from project open to smart mode |
| `go list -m -json all` at each open, module cache warm | 0.1 to 0.25 s |
| Module dependencies that GoLand reports | 595 |
| Go fixture rows while `caddy` is open | 99 passed |
| Go fixture rows directly after a close | 99 passed |
| Resident memory of GoLand, fixture plus `caddy`, directly after the open | 2160 MB |
| Resident memory after the import check | 2421 MB |
| Used heap after a full collection | 218 MB after the open, 281 MB after the import check |

The used heap stays far below 1200 MB (60% of the limit), so GoLand keeps `-Xmx2048m`.

Facts about the switch:

- GoLand accepts a minimal entry in `recentProjects.xml`
  (`<RecentProjectMetaInfo opened="true" />`) and opens that project at its start.
- GoLand does not write `recentProjects.xml` at its start or at an exit after SIGTERM. The
  marks stay as the harness wrote them.
- `go list` runs again at each open. The module registry comes from the project-model cache
  of the IDE, and the indexes are used again: a second open scans 24,749 files and indexes none.
- During the first indexing GoLand reports smart mode two times for about 3 seconds before
  the dependencies are indexed. The index status alone is not a safe readiness signal for a
  first open; the canary rows are.
- `goland.sh serverMode <path>` opens only that one project and restores no other project.
  A second path argument is ignored. So the harness always starts a bare `serverMode`.

## Import check

Done on 2026-11-10 with plugin 2.1.1-dev.05. The product is accepted.

| Call | Result |
|---|---|
| `ide_find_class`, query `Module` | the interface `Module`, `modules.go:54` |
| `ide_find_definition`, `caddy.go:758:51` | `logger.go:41` of `go.uber.org/zap@v1.28.0`, outside the project |
| `ide_find_usages`, `modules.go:54:6`, `pageSize` 100 | 100 usages, `hasMore` true, `totalCollected` 187 |
| `ide_type_hierarchy`, `modules.go:54:6` | 144 subtypes |
| `ide_file_structure`, `caddy.go` | a structure of 29 KB |

Comparison with GoLand itself. A second GoLand with a window opened a copy of the pin that
had no IDE files, so that GoLand made the project model by itself:

- The tools give the same results on that import and on the fleet project with the three
  written IDE files: usages (187), type hierarchy (144), class search, file structure and
  symbol search (104). The written files are a correct model.
- Type hierarchy: the IDE shows "144 implementations" at the interface, and all 23 subtypes
  on the first screen of its Hierarchy window are in the tool result.
- Find Usages: the IDE lists 200 results, the tool 187. The 13 others are the IDE group
  "Usage in comments" (`context.go` 561 and 661, `modules.go` 29 and 91,
  `internal/testmocks/dummyverifier.go` 22, and 8 lines of `modules/caddytls/capools.go`).
  The option "Text occurrences" was off. This is a finding about the tool, not about the
  import.

Project model facts that the probe rows rely on:

- A Go project has no source roots in GoLand. `project_production_files` and
  `project_test_files` give the error `scope_matches_no_files`, and the Find Usages dialog
  of GoLand offers no production scope and no test scope. The Go fixture pins the same.
- The hierarchy scope `test` is different: it follows the Go test file names. On `Module`
  it gives 8 subtypes, and the scope `production` gives none.
