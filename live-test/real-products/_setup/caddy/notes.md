# caddy

- Repository: https://github.com/caddyserver/caddy
- Pin: tag `v2.11.7`, commit `72dd0fb067f6d7826c7f79907670ba4a713bfe37`, committed 2026-10-03
- License: Apache-2.0
- IDE: GoLand (port 29174)
- Language level: `go 1.26.0` in `go.mod`

## Setup

Run `bootstrap.sh`. It checks the Go version, downloads the modules, and writes
`.idea/workspace.xml` with the GOROOT when that file is absent. There is no lockfile
to create: `go.sum` is committed.

## Measured
