# Live MCP Test Harness

Snapshot-based regression suite for the IdeSense plugin. Drives real
HTTP POST requests against running JetBrains IDEs and diffs the responses
against committed `_snapshots/<lang>/expected/<tool>.jsonl` files.

Run after every plugin version bump.

> Maintaining or extending this suite? See `CLAUDE.md` in this directory
> for conventions (id naming, snapshot format, bless safety rules,
> captured-ground-truth quirks, fixture-edit safety).

## Requirements

- Python 3.10+ (stdlib only — no third-party deps)
- The dev plugin installed in each IDE you intend to test against (see below).
- The corresponding fixture project open in that IDE, fully indexed.

## Per-IDE fixture setup

| Language fixture | Open in | Default port |
|---|---|---|
| `python/` | PyCharm | 29172 |
| `java/`, `kotlin/` | IntelliJ IDEA | 29170 |
| `javascript/`, `typescript/` | WebStorm | 29173 |
| `go/` | GoLand | 29174 |
| `php/` | PhpStorm | 29175 |
| `rust/` | RustRover | 29178 |

Each fixture is a real IDE-openable project. Open it, wait for indexing,
then run the harness.

Snapshots (`inputs/`, `expected/`, `output.jsonl`) live under
`live-test/_snapshots/<lang>/`, deliberately **outside** the fixture
project roots: snapshot text mentions every fixture symbol, and past
IntelliJ's 10-file text-occurrence threshold the unused-symbol inspection
silently stops reporting — which would change diagnostics snapshots.

## Quick start

```bash
./run.py                                 # runs every language, fails on diff
./run.py --bless                         # rewrite _snapshots/<lang>/expected/<tool>.jsonl from server output
./run.py --bless --bless-errors          # allow blessing rows that returned tool errors (rare)
./run.py --bless --prune                 # allow bless to drop orphan expected ids
./run.py --language python               # one language only
./run.py --tool ide_find_definition      # one tool across all languages
./run.py --url http://127.0.0.1:29170/mcp/streamable-http   # override URL
./run.py --check-fixtures                # validate input/expected files offline (no IDE calls)
```

Each run writes `live-test/_snapshots/<lang>/output.jsonl` (gitignored) with the raw
normalized response per entry. Useful for inspecting current responses
without re-blessing.

## Version-bump workflow

1. Bump `pluginVersion` in `gradle.properties`.
2. `./gradlew buildPlugin` and install the resulting ZIP into each IDE
   (Settings → Plugins → ⚙ → Install Plugin from Disk…).
3. Restart each IDE. (The plugin is not dynamically reloadable — a full restart is required after reinstall.)
4. Re-open every fixture; wait for indexing to finish.
5. Run the harness:

   ```bash
   ./live-test/run.py
   ```

6. If failures appear:
   - Read each diff carefully. Is the change intentional (matches the
     CHANGELOG entry for the new version) or a regression?
   - Intentional: `./live-test/run.py --bless` and commit alongside the
     version bump.
   - Regression: file an issue or revert the change.

> **Automating install/restart across IDEs.** Steps 2–3 above can be driven headlessly
> instead of clicking through Settings → Install from Disk: enable the `ide_install_plugin`
> and `ide_restart` tools (both off by default), then POST `tools/call` for them to each
> IDE's port (see the table above). Pass a `project_path` argument when an IDE has multiple
> fixtures open — IntelliJ IDEA (`java` + `kotlin`) and WebStorm (`javascript` +
> `typescript`) — otherwise the call fails with `multiple_projects_open`.

## Troubleshooting

- **`PRECHECK: cannot reach …`** — the IDE's MCP server isn't running on
  the expected port. Check that the dev plugin is installed and enabled,
  and that the IDE is open. Override the port with `--url` if you've
  configured a non-default value in Settings → Tools → IdeSense.
- **`PRECHECK: project is in dumb mode`** — wait for indexing to finish
  in the IDE, then retry.
- **`MISSING (no expected entry for this id)`** — the tool's
  `expected/<tool>.jsonl` doesn't have an entry for this input id. Likely
  you added a new input row and haven't blessed yet. Run `--bless` to add it.
- **`ORPHAN expected id …`** — an expected entry whose id is no longer in
  any `inputs/<tool>.jsonl`. Either restore the input row or run
  `--bless --prune` to drop the orphan.
- **All entries `FAIL` after a JDK / language toolchain update** — the
  toolchain change shifted JDK source line numbers. Re-bless once
  intentionally.
- **Result that looks wrong but the IDE consistently returns it** — see
  "Captured ground truth" in `CLAUDE.md`. Some IDE quirks are blessed on
  purpose; don't try to "fix" them by changing the probe.

## Why not in CI?

The harness POSTs to live IDE-hosted servers, so it requires running
IDEs. CI runners don't carry a desktop IDE. Headless IDE execution
(`./gradlew runIde`) plus a fixture-loading script could enable this in
the future; deferred for v1.
