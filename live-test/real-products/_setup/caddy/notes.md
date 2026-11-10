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
