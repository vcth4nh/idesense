# Live MCP Test Harness

Snapshot-based regression suite for the IdeSense plugin. Drives real
HTTP POST requests against running JetBrains IDEs and diffs the responses
against committed `fixtures/_snapshots/<lang>/expected/<tool>.jsonl` files.

Run after every plugin version bump.

A second suite runs the same tools on pinned real products. See "Real products" below.

> Maintaining or extending this suite? See `CLAUDE.md` in this directory
> for conventions (id naming, snapshot format, bless safety rules,
> captured-ground-truth quirks, fixture-edit safety).

## Requirements

- Python 3.10+ (stdlib only — no third-party deps)
- The dev plugin installed in each IDE you intend to test against (see below).
- The corresponding fixture project open in that IDE, fully indexed.

## Per-IDE fixture setup

The fixture projects are in `live-test/fixtures/`.

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
`live-test/fixtures/_snapshots/<lang>/`, deliberately **outside** the fixture
project roots: snapshot text mentions every fixture symbol, and past
IntelliJ's 10-file text-occurrence threshold the unused-symbol inspection
silently stops reporting — which would change diagnostics snapshots.

## Quick start

```bash
./run.py                                 # runs every language, fails on diff
./run.py --bless                         # rewrite fixtures/_snapshots/<lang>/expected/<tool>.jsonl from server output
./run.py --bless --bless-errors          # allow blessing tool errors / non-error→error transitions (rare)
./run.py --bless --prune                 # allow bless to drop orphan expected ids
./run.py --language python               # one language only
./run.py --tool ide_find_definition      # one tool across all languages
./run.py --url http://127.0.0.1:29170/mcp/streamable-http   # override URL
./run.py --check-fixtures                # validate input/expected files offline (no IDE calls)
```

Each run writes `live-test/fixtures/_snapshots/<lang>/output.jsonl` (gitignored) with the raw
normalized response per entry. Useful for inspecting current responses
without re-blessing.

Per-language anchor maps live at `fixtures/_snapshots/<lang>/ANCHORS.md` — a generated
index mapping every probe id to the fixture line it anchors (regenerate with
`./run.py --write-anchors`; `--check-fixtures` fails while the map is stale).

## Real products

The fixtures prove each tool on small code. A real product shows the behaviour at scale:
page limits, caps, dependencies, and names that many declarations share. Each product is a
git submodule at a pinned release.

### Layout

```
live-test/real-products/
  products.json                          # product table: folder, IDE, repository, pin, license, tier, timeouts
  <folder>/                              # git submodule at the pin: test data, never edited
  _setup/<folder>/bootstrap.sh           # prepares a checkout for its IDE; changes no tracked file
  _setup/<folder>/notes.md               # pin, setup facts, measured times, project-model facts
  _snapshots/<folder>/inputs/<tool>.jsonl
  _snapshots/<folder>/expected/<tool>.jsonl
  _snapshots/<folder>/ANCHORS.md         # anchor map: positions and identifiers, no source lines
  _snapshots/<folder>/output.jsonl       # run artifact, gitignored
```

### Get a checkout

```bash
git submodule update --init --depth 1 live-test/real-products/<folder>
live-test/real-products/_setup/<folder>/bootstrap.sh
```

The fixture suite needs no product checkout. A product with no checkout is `SKIPPED` in a
run of `--suite all`, and it fails a run that names it with `--product`.

### Commands

```bash
./run.py --product caddy                          # one product (restarts its IDE)
./run.py --suite real-products                    # every product
./run.py --suite all                              # the fixtures, then every product
./run.py --open-product caddy                     # open one product next to its fixtures, then exit
./run.py --close-products                         # leave only the fixtures open in every IDE
./run.py --check-fixtures --product caddy         # offline check of one product
./run.py --write-anchors --product caddy          # regenerate its ANCHORS.md
./run.py --product caddy --bless --bless-canary   # bless, canary rows included (needs permission)
```

The plain `./run.py` is the fixture suite. It never restarts an IDE.

### One product per IDE

An IDE always has its fixture projects open, and at most one product next to them. Before
the rows of a product run, the harness makes that product the one open product of its IDE:
it stops the IDE, marks the projects in `recentProjects.xml`, and starts the IDE again.
After the last product of an IDE it closes the product in the same way. So each product
costs one IDE restart, and the close costs one more. A product that was open before the run
stays open. `--open-product` uses this for a session with many runs.

The IDEs are shared. A fixture run of another session fails on an IDE while it restarts, so
check for an active run before a product run.

Measured for `caddy` (GoLand 2026.2, 2026-11-10):

| Step | Time |
|---|---|
| Project switch (stop, mark, start, both projects listed) | 11 s |
| Ready after a switch, product indexed before | 0 to 5 s |
| First indexing (16,329 files with the dependencies) | 34 s |
| 63 rows, product open before | 11 to 16 s |
| 63 rows with the switch | 33 s |

### Add a product

1. **Submodule and pin.** `git submodule add -f --depth 1 <url> live-test/real-products/<folder>`,
   check out the release tag, and set `shallow = true` and `ignore = dirty` for the entry in
   `.gitmodules`. The `-f` is necessary because `live-test/real-products/.gitignore` ignores
   the product folders.
2. **Table entry** in `products.json`: folder, IDE, repository, pin, license, tier, timeouts.
3. **Search hygiene.** From the repository root, search for one identifier of the product
   with `rg` and with `grep -r`. The search must find nothing in the checkout.
4. **Bootstrap.** Write `_setup/<folder>/bootstrap.sh`. It is idempotent and changes no
   tracked file. It gets the dependencies and writes the IDE project files that the product
   needs: GoLand restores a project at its start only when the folder has an `.idea` folder
   with a module file. PhpStorm and RustRover also need a trust entry for the product path.
5. **Import check.** `--open-product <folder>`, then compare some tool calls with the IDE
   itself. Record the times and the memory in `_setup/<folder>/notes.md`.
6. **Canary rows.** 2 or 3 rows with the id prefix `canary-` that pin the project model.
7. **Sweep.** Draft the probe rows, run them, and give each row a class: OK, EMPTY, ERROR or
   SUSPECT. Check each EMPTY row and each SUSPECT row against the source or the IDE.
8. **Stability check.** Run the rows three times, and one more time after a project switch.
   A row that differs between two runs becomes a `shape` row or goes out.
9. **Agent task.** Three bugs that were fixed after the pin, one fresh agent for each bug.
10. **Triage.** One outcome for each finding: an issue, a decision of the maintainer, a
    setup correction, or a ground-truth note.
11. **Bless, with permission.** Park the rows that show an open defect. Then
    `--bless --bless-canary`, `--write-anchors`, `--check-fixtures`, and two verify runs.
12. **Notes.** Complete `notes.md` and the ground-truth notes in `CLAUDE.md`.

### Change a pin

1. Check out the new commit in the submodule and stage the submodule entry.
2. Run the `bootstrap.sh` of the product again.
3. `./run.py --product <folder>`. Read each difference.
4. Re-bless with permission. Then `--write-anchors` and `--check-fixtures`.

### Rules

- Never initialize the submodules of a product.
- No file or folder below `_setup/` or `_snapshots/` may have the name `build`, `bin`, `tmp`,
  `cache`, `logs` or `.idea`, or end in `.log`. The root `.gitignore` ignores these names.
- A product checkout is test data. Change no tracked file in it, and never copy a plugin zip
  into it. Use a fixture project for `ide_install_plugin`.

## Version-bump workflow

1. Bump `pluginVersion` in `gradle.properties`.
2. `./gradlew buildPlugin` and install the resulting ZIP into each IDE
   (Settings → Plugins → ⚙ → Install Plugin from Disk…).
3. Restart each IDE. (The plugin is not dynamically reloadable — a full restart is required after reinstall.)
4. Re-open every fixture; wait for indexing to finish.
5. Run both suites, the fixtures and the real products:

   ```bash
   ./live-test/run.py --suite all
   ```

   The product part restarts the IDE of each product. A product with no checkout is
   `SKIPPED`.

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
>
> `ide_install_plugin` only accepts a zip **inside the open project** (out-of-root paths are
> rejected), and the fixture projects are not the plugin repo — so first copy the built zip
> into each fixture root (`cp build/distributions/*.zip live-test/fixtures/<lang>/`) and pass that
> in-project path. The copies are gitignored (`live-test/fixtures/*/*.zip`); delete them afterwards.

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
- **`[<product>] MISCONFIGURED: canary row … differs`** — the project model of the
  product is not the one that its canary rows pin (dependencies not resolved, another
  SDK, index not complete). The other rows of the product did not run. Run the
  `bootstrap.sh` of the product, look at the IDE, and run again. Never bless in this state.
- **`[<product>] SKIPPED (checkout is missing: …)`** — run the printed
  `git submodule update` command, then the `bootstrap.sh` of the product.
- **`[<product>] FAIL pin mismatch: …` or `FAIL modified: …`** — the checkout is not at
  the pinned commit, or a tracked file of it changed. Put the checkout back to the pin.
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
