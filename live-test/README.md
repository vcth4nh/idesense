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
- For the real-product suite also: Linux (the harness reads `/proc`), the programs `git` and
  `setsid`, and a checkout of each product (see "Real products").

The harness has unit tests that need no IDE and no product checkout:

```bash
python3 -B -m unittest discover -s live-test -p "test_*_unit.py"
```

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

With `--url` the rows of a product run against that server, for example a throwaway IDE.
The harness restarts only a fleet IDE, so the product must be open at that server.

### One product per IDE

An IDE always has its fixture projects open, and at most one product next to them. Before
the rows of a product run, the harness makes that product the one open product of its IDE:
it stops the IDE, marks the projects in `recentProjects.xml`, and starts the IDE again.
After the last product of an IDE it closes the product in the same way. So each product
costs one IDE restart, and the close costs one more. A product that was open before the run
stays open. `--open-product` uses this for a session with many runs.

The IDEs are shared. A fixture run of another session fails on an IDE while it restarts, so
check for an active run before a product run. The switch has these safety rules:

- **Only a product is closed.** A switch closes only a folder directly below
  `real-products/` of the checkout that runs the command. When the IDE has another project
  open that the command does not want, the switch stops with `must not close: …` and
  restarts nothing. So a command from a git worktree or a second clone cannot take the
  fixture projects from the fleet. Such a checkout sets `LIVE_TEST_FLEET_FIXTURES` to the
  fixtures folder of the checkout that the fleet has open:

  ```bash
  LIVE_TEST_FLEET_FIXTURES=<fleet checkout>/live-test/fixtures ./live-test/run.py --product <folder>
  ```

  Then the switch keeps the fleet fixtures open and opens the product checkouts of the
  worktree next to them. A fixture run with the variable runs the snapshots of the worktree
  against the fleet fixtures, so the fixture sources of the two checkouts must be equal. A
  product of the fleet checkout still stops the switch: close it from that checkout.
- **The IDE comes back.** The harness proves the launcher before the stop. From the stop to
  the start it holds back Ctrl+C and SIGTERM, and it starts the IDE also after an error. An
  IDE that does not stop in 90 seconds gets no second signal: the error line gives the
  start command.
- **An interrupt closes the product.** After Ctrl+C in a product run the harness still
  closes the product that this run opened.

Measured for `caddy` (GoLand 2026.2, 2026-11-11; the first indexing on 2026-11-10):

| Step | Time |
|---|---|
| Project switch (stop, mark, start, both projects listed) | 11 s |
| Ready after a switch, product indexed before | 0 to 5 s |
| First indexing (16,329 files with the dependencies) | 34 s |
| 69 rows, product open before | 11 to 20 s |
| 69 rows with the switch | 38 s |

### Add a product

1. **Submodule and pin.** The `-f` is necessary because
   `live-test/real-products/.gitignore` ignores the product folders. A shallow clone has no
   tags, so fetch the release tag by name:

   ```bash
   P=live-test/real-products/<folder>
   git submodule add -f --depth 1 <url> $P
   git -C $P fetch --depth 1 origin tag <tag>
   git -C $P checkout --detach <tag>
   git config -f .gitmodules submodule.$P.shallow true
   git config -f .gitmodules submodule.$P.ignore dirty
   git add .gitmodules $P
   ```
2. **Table entry** in `products.json`: folder, IDE, repository, pin, license, tier, timeouts.
3. **Search hygiene.** From the repository root, search for one identifier of the product
   with `rg` and with `git grep`. The search must find nothing in the checkout. The `grep`
   of an agent shell (ugrep with `--ignore-files`) also skips the checkout. GNU `grep -r`
   reads no ignore file and does search it.
4. **Bootstrap.** Write `_setup/<folder>/bootstrap.sh`. It is idempotent and changes no
   tracked file. It gets the dependencies and writes the IDE project files that the product
   needs: GoLand restores a project at its start only when the folder has an `.idea` folder
   with a module file. The module file holds the source folders that the IDE itself writes at
   a first open: at a later open RustRover applies the module file after the Cargo sync, and a
   module file with no source folder removes all roots. The bootstrap writes no trust entry:
   a `serverMode` IDE checks the trust of a project, so the switch that opens a product adds
   a trust entry for the product path to `options/trusted-paths.xml` of the IDE while the IDE
   is down.
5. **Import check.** `--open-product <folder>`, then compare some tool calls with the IDE
   itself. Record the times and the memory in `_setup/<folder>/notes.md`.
6. **Canary rows.** 2 or 3 rows with the id prefix `canary-` that pin the project model.
7. **Sweep.** Draft the probe rows, run them, and give each row a class: OK, EMPTY, ERROR or
   SUSPECT. Check each EMPTY row and each SUSPECT row against the source or the IDE.
8. **Stability check.** Run the rows three times, and one more time after a project switch.
   A row that differs between two runs becomes a `shape` row or goes out. PhpStorm indexes
   the content of a `.phar` file, and after a restart this content can be absent: no row may
   resolve into a phar or count a result in one.
9. **Agent task.** Three bugs that were fixed after the pin, one fresh agent for each bug.
10. **Triage.** One outcome for each finding: an issue, a decision of the maintainer, a
    setup correction, or a ground-truth note.
11. **Bless, with permission.** Park the rows that show an open defect. Then
    `--bless --bless-canary`, `--write-anchors`, `--check-fixtures`, and two verify runs.
    A row that pins an expected error stops this bless: the error gates refuse a new error
    row. Bless the file of that tool first, with
    `--tool <tool> --bless --bless-canary --bless-errors`, and read the new expected file.
    Then bless all rows with no `--bless-errors`. Never use `--bless-errors` for all rows:
    it switches off both error gates, and a timeout becomes an expected row.
12. **Notes.** Complete `notes.md` and the ground-truth notes in `CLAUDE.md`.

### Change a pin

1. Check out the new commit in the submodule and stage the submodule entry.
2. Run the `bootstrap.sh` of the product again.
3. `./run.py --product <folder>`. Read each difference.
4. Re-bless with permission. Then `--write-anchors` and `--check-fixtures`.

### Rules

- Never initialize the submodules of a product.
- No file or folder below `_setup/` or `_snapshots/` may have the name `build`, `bin`, `tmp`,
  `cache`, `logs` or `.idea`, or end in `.log` or `.iml`. The root `.gitignore` and
  `live-test/.gitignore` ignore these names.
- A product row uses a read-only tool. No row calls `ide_refactor_rename`, `ide_move_file`,
  `ide_install_plugin`, `ide_restart` or `ide_sync_files` on a product.
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
     version bump. For a product: `./live-test/run.py --product <folder> --bless`. When the
     change also alters a canary row, see `MISCONFIGURED` in "Troubleshooting".
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
- **`[<product>] MISCONFIGURED: canary row … differs`** — a canary row differs from its
  expected row, and the other rows of the product did not run. The first try prints the
  difference. After a project switch the harness tries again for the readiness time of the
  product, because the build tool can still be at work. With no switch it tries for
  60 seconds. Two causes are possible, and the printed difference shows which one:
  - The project model is wrong (dependencies not resolved, another SDK, index not
    complete). Run the `bootstrap.sh` of the product, look at the IDE, and run again.
    Never bless in this state.
  - The plugin changed the output of the tool of that canary row, and the fixture suite
    shows the same change. Then run `--product <folder> --bless --bless-canary` with
    permission, and read the `git diff` of the expected files before the commit.
- **Some rows of a fixture fail in the first seconds after an IDE restart** — the IDE
  lists its projects and reports smart mode, but it still loads the SDK or the build
  model. Seen one time in three restarts of GoLand: 2 of 99 Go rows. Run the fixture again.
- **`… has projects open that this command must not close: …`** — the IDE has a project
  open that is no product of this checkout, and the command does not want it. Run the
  command from the checkout whose fixtures the IDE has open, or close that project by hand.
  From a git worktree or a second clone, set `LIVE_TEST_FLEET_FIXTURES` to the fixtures
  folder of that checkout. Then the harness opens the product checkouts of the worktree next
  to the fleet fixtures. For a fixture run the fixture sources of the two checkouts must be
  equal. When the project is a product of the other checkout, close it from that checkout.
- **`… is not the fleet server of …`** — `--url` names another server. The harness
  restarts only a fleet IDE. Open the product at that server by hand.
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
