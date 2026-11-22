# Live MCP Test Harness

Snapshot-based regression suite for the IdeSense plugin. Drives real
HTTP POST requests against running JetBrains IDEs and diffs the responses
against committed `fixtures/_snapshots/<lang>/expected/<tool>.jsonl` files.

## The four instruments

`live-test/` has four instruments. The two suites compare the output of a tool with a blessed
snapshot. The audit and the agent batch compare answers with keys that no IDE made. The method of
each instrument, its limits and what a result can claim are in [METHOD.md](METHOD.md).

| Instrument | Compares | Truth | Result | Cost | Command |
|---|---|---|---|---|---|
| Fixture suite | The output of each tool on small projects, one for each language | Snapshot | Pass or fail for each row | No money; the fleet IDEs | `./live-test/run.py` |
| Product suite | The output of each tool on the products of `real-products/products.json` | Snapshot | Pass or fail for each row | No money; one IDE restart for each product | `./live-test/run.py --suite real-products` |
| Audit ([audit/README.md](audit/README.md)) | The answers of the tools for each symbol of a key file, with no agent | Key | `pass`, `fail` or `wait` | No money; the benchmark IDEs | `./live-test/run.py audit verdict run ...` |
| Agent batch ([bench/README.md](bench/README.md)) | The answers of a coding agent with and without the plugin | Key | Numbers for each arm, and the differences between the arms | Money for each run (the batch `main` had 468 runs and cost 23.09 USD: `bench/ledger/2026-11-18-main.md`) | `./live-test/run.py bench runner batch -plan <plan> -batch <name>` |

The key makers are in [keygen/README.md](keygen/README.md). A person who wants to score an agent
on the questions of the benchmark, with no harness, reads
[bench/questions/README.md](bench/questions/README.md). The suites use the fleet IDEs. The audit
and the batch use two benchmark IDEs with their own folders and ports, and never call a fleet IDE.
`./live-test/run.py <package> <module> [args]` runs a command of the packages `audit`, `bench`,
`keygen` and `common` from any folder. With no module, `./live-test/run.py <package>` prints one
line with the modules of the package.

A second suite runs the same tools on pinned real products. See "Real products" below.

Run both suites after each change of tool behavior and before a release (see "Run the suites
against a new build").

> Maintaining or extending this suite? See [CONVENTIONS.md](CONVENTIONS.md) for the
> conventions (id naming, snapshot format, bless safety, fixture-edit safety). A result that
> looks wrong on purpose has a note in the `GROUND-TRUTH.md` next to its snapshot folder.
> An agent reads [AGENTS.md](AGENTS.md) first.

## Requirements

- Python 3.10+ (stdlib only — no third-party deps)
- The dev plugin installed in each IDE you intend to test against (see below).
- The corresponding fixture project open in that IDE, fully indexed.
- For the real-product suite also: Linux (the harness reads `/proc`), the programs `git` and
  `setsid`, and a checkout of each product (see "Real products").

The harness has unit tests that need no IDE and no product checkout:

```bash
python3 -B -m unittest discover -s live-test -t live-test -p "test_*_unit.py"
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

**Python: mark `test/` as a test root.** PyCharm 2026.2 re-imports the fixture from
`pyproject.toml` as `.idea/live-test-python.iml` (and rewrites the tracked `modules.xml`) with
`test/` as a plain source root. Then `hier-caller-target-production` gains the test caller and
`hier-caller-target-test` loses it. Stop PyCharm, set `isTestSource="true"` on the `test`
source folder in that `.iml`, and restart. The `.iml` is gitignored, so a fresh checkout needs
the same edit. Issue #228 tracks the untracked module file.

In this document, **the fleet** is the set of these IDEs: each one runs on its default port
and has its fixture projects open. **The fleet checkout** is the checkout of this repository
whose fixture folders the fleet has open.

Snapshots (`inputs/`, `expected/`, `output.jsonl`) live under
`live-test/fixtures/_snapshots/<lang>/`, outside the fixture project roots (the reason is in
"Snapshot file format" in [CONVENTIONS.md](CONVENTIONS.md)).

## Quick start

```bash
./run.py                                 # runs every language, fails on diff
./run.py --bless                         # rewrite fixtures/_snapshots/<lang>/expected/<tool>.jsonl from server output
./run.py --language <lang> --tool <tool> --bless --bless-errors   # bless the error rows of one tool file (see "Bless safety" in CONVENTIONS.md)
./run.py --bless --prune                 # allow bless to drop orphan expected ids
./run.py --language python               # one language only
./run.py --tool ide_find_definition      # one tool across all languages
./run.py --language java --url http://127.0.0.1:29170/mcp/streamable-http   # override URL
./run.py --check-fixtures                # validate input/expected files offline (no IDE calls)
```

Each run writes `live-test/fixtures/_snapshots/<lang>/output.jsonl` (gitignored) with the raw
normalized response per entry. Useful for inspecting current responses
without re-blessing.

Each language has an anchor map, `fixtures/_snapshots/<lang>/ANCHORS.md`, that
`./run.py --write-anchors` generates (see "Fixture comment standard" in CONVENTIONS.md).

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

Some products ship their own `AGENTS.md` or `CLAUDE.md`: product content, and no instruction
for work on this repository (see [AGENTS.md](AGENTS.md)). Claude Code loads such a file when
it reads a file in that checkout. To keep these files out, add this key to the Claude Code
user settings (`~/.claude/settings.json`). This repository ignores `.claude/`, so a project
settings file stays in one checkout, and a git worktree does not get it.

```json
"claudeMdExcludes": ["**/live-test/real-products/**/CLAUDE.md", "**/live-test/real-products/**/AGENTS.md"]
```

### Commands

```bash
./run.py --product caddy                          # one product (restarts its IDE)
./run.py --suite real-products                    # every product
./run.py --suite all                              # the fixtures, then every product
./run.py --open-product caddy                     # open one product next to its fixtures, then exit
./run.py --close-products                         # leave only the fixtures open in every IDE
./run.py --check-fixtures --product caddy         # offline check of one product
./run.py --write-anchors --product caddy          # regenerate its ANCHORS.md
./run.py --product caddy --bless --bless-canary   # bless, canary rows included (see the bless rule in AGENTS.md)
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

The measured times of each product are in `_setup/<folder>/notes.md`.

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
   `requestTimeoutSeconds` is the time limit of one request. `readyTimeoutSeconds` is the
   readiness time of the product: how long the harness waits until the product is open and
   indexed (default 900).
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
   is down. For a JavaScript product use `npm ci --ignore-scripts`: it runs no script of the
   product and no install script of a package.
5. **Import check.** `--open-product <folder>`, then compare some tool calls with the IDE
   itself. Record the times and the memory in `_setup/<folder>/notes.md`. A product that the
   IDE imports with Gradle needs one restart with `ide_restart` after its first sync: see
   "Kotlin rows fail after an IDE restart with empty results" in "Troubleshooting".
6. **Canary rows.** Add the rows with the id prefix `canary-` that pin the project model (see
   "Canary rows" in CONVENTIONS.md).
7. **Sweep.** Draft the probe rows, run them, and give each row a class: OK, EMPTY, ERROR or
   SUSPECT. Check each EMPTY row and each SUSPECT row against the source or the IDE.
8. **Stability check.** Run the rows three times, and one more time after a project switch.
   A row that differs between two runs goes out, or becomes a `shape` row when its result is
   cut. If the difference shows a defect, see "A row that differs between two equal runs" in
   CONVENTIONS.md. No row may resolve into a `.phar` file or count a result in one (see the
   phpunit [GROUND-TRUTH.md](real-products/_snapshots/phpunit/GROUND-TRUTH.md)).
9. **Triage.** One outcome for each finding: an issue, a decision of the owner of the
   repository, a setup correction, or a ground-truth note.
10. **Bless, under the bless rule of `AGENTS.md`.** Park the rows that show an open defect. Then
    run these commands with `--product <folder>`: `--bless --bless-canary`, `--write-anchors`,
    `--check-fixtures`, and two verify runs. For a row that pins an expected error, see "Rows
    that pin an expected error" in CONVENTIONS.md.
11. **Notes.** Complete `notes.md` and the ground-truth notes in
    `_snapshots/<folder>/GROUND-TRUTH.md`.

### Change a pin

1. Fetch the new tag by name (a shallow clone has no tags), check it out in the submodule, and
   stage the submodule entry:

   ```bash
   P=live-test/real-products/<folder>
   git -C $P fetch --depth 1 origin tag <tag>
   git -C $P checkout --detach <tag>
   git add $P
   ```
2. Change `pin` in `products.json` and the "Pin" line of `_setup/<folder>/notes.md`.
3. Run the `bootstrap.sh` of the product again.
4. `./run.py --product <folder>`. Read each difference.
5. Check the canary results by hand. Then re-bless under the bless rule of `AGENTS.md` with
   `./run.py --product <folder> --bless --bless-canary`. A plain `--bless` does not rewrite the
   canary rows. Then run `--write-anchors` and `--check-fixtures`.

### Rules

- No file or folder below `_setup/` or `_snapshots/` may have the name `build`, `bin`, `tmp`,
  `cache`, `logs` or `.idea`, or end in `.log` or `.iml`. The root `.gitignore` and
  `live-test/.gitignore` ignore these names.
- The rules for product rows and product checkouts are in [AGENTS.md](AGENTS.md), sections
  "Shared IDEs" and "Product checkouts".

## Operate the IDEs

The six IDEs of the table in "Per-IDE fixture setup" run with no window (`serverMode`), and
other sessions use them at the same time. Before you stop or restart an IDE, look for an
active harness run with `pgrep -af '[l]ive-test/run\.py'`. Run it as a command of its own: a
shell line that also holds the text `live-test/run.py` finds its own shell.

The folders are the Linux defaults. `<Product><version>` is the paths selector of the IDE, for
example `GoLand2026.2` (also `IntelliJIdea`, `PyCharm`, `WebStorm`, `PhpStorm`, `RustRover`).

| Placeholder | Holds | Linux default |
|---|---|---|
| `<config dir>` | settings (`options/`) | `~/.config/JetBrains/<Product><version>/` |
| `<system dir>` | caches, indexes, `log/idea.log` | `~/.cache/JetBrains/<Product><version>/` |
| `<plugins dir>` | custom plugins | `~/.local/share/JetBrains/<Product><version>/` |

### Send a request to an IDE

Each IDE serves MCP at `http://127.0.0.1:<port>/mcp/streamable-http`. A request is one HTTP
POST with a JSON-RPC body, and the answer is one plain JSON object, not an event stream. The
server does not read the `Accept` header: the harness sends only `Content-Type`.

```bash
curl -s http://127.0.0.1:<port>/mcp/streamable-http -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25"}}'
```

- `initialize` gives the build that runs in `result.serverInfo.version`. `tools/call` gives
  the tool result as a JSON text in `result.content[0].text`.
- `tools/list` (`"method":"tools/list"`) gives only the enabled tools. A call of a disabled
  tool gets the JSON-RPC error `-32601`, `Tool disabled by user settings: <name>. …`.
- A call with a `project_path` that the IDE does not have open lists the open projects in
  `available_projects`. An entry with a `workspace` key is a module folder, not a project.
- A call needs `project_path` when the IDE has more than one project open (IntelliJ IDEA,
  WebStorm, each IDE with a product open), else it gets `multiple_projects_open`.
  `ide_index_status` is the exception: with no arguments it answers for each open project.

### Deploy a build to the IDEs

This procedure installs a build in each IDE through its MCP port, with no window.

1. **Build** with a new version on the command line:
   `./gradlew buildPlugin -PpluginVersion=<version>-dev.NN`. The reason and the rules for
   `<version>` and `NN` are in [CONTRIBUTING.md](../docs/CONTRIBUTING.md#dev-builds), "Dev
   builds".
2. **Check the tools.** `tools/list` of each IDE must give `ide_install_plugin` and
   `ide_restart`, which are off by default. To turn them on, see "Change a plugin setting".
3. **Copy the zip** (`build/distributions/idesense-<version>-dev.NN.zip`) into one fixture
   root of each IDE: `java`, `python`, `javascript`, `go`, `php`, `rust`. `ide_install_plugin`
   accepts only a zip inside the project that `project_path` names. From a worktree, use the
   folder of `LIVE_TEST_FLEET_FIXTURES`. Git ignores these copies
   (`live-test/fixtures/*/*.zip`). Never copy a zip into a product checkout.
4. **Install, then restart** each IDE. `path` is relative to the project root:

   ```
   {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ide_install_plugin","arguments":{"path":"idesense-<version>-dev.NN.zip","project_path":"<fixture root>"}}}
   {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ide_restart","arguments":{"project_path":"<fixture root>"}}}
   ```

   The install result has `"installed": true` and the `pluginVersion` of the zip. The tool
   unpacks the zip at once into `<plugins dir>` and replaces the old plugin folder, so remove
   the copy now. The restart starts `delaySeconds` (default 2) after its answer, and the IDE
   opens its projects again.
5. **Wait for the new build.** Call `initialize` every few seconds until `serverInfo.version`
   is the new version. An answer in the first seconds after `ide_restart` comes from the old
   process: only the version is a proof. Seen: one restart takes 30 to 40 s.
6. **Wait for the index.** Call `ide_index_status` with no arguments until `isDumbMode` is
   `false`.

**Fallback when `ide_install_plugin` is off.** Stop the IDE (see "Start an IDE with no
display"). Replace the folder `<plugins dir>/idesense` with the content of the zip (one top
folder, `idesense/`), and write the settings file that turns on the two tools. Start the IDE.

### Prove which build runs

Several sessions deploy to the same IDEs, and the last install wins. Each IDE restart loads
the build on the disk, also the restart of a project switch. So an earlier check proves
nothing about the build that runs now.

- **The build that runs:** `serverInfo.version` in the `initialize` answer. The plugin reads
  it from its loaded plugin descriptor.
- **The build on the disk:** `<plugins dir>/idesense/lib/idesense-<version>.jar`. The next
  restart loads it.
- **What ran when:** at each start the IDE writes the line `Loaded custom plugins: …,
  IdeSense - IDE MCP Server (<version>)` to `idea.log`. Find it with
  `grep 'Loaded custom plugins' <system dir>/log/idea*.log` (older entries are in
  `idea.1.log` and the next files).

### Start an IDE with no display

The IDEs of the harness are `serverMode` instances: remote-development hosts that need no
display. The harness starts an IDE with the launcher, the environment and the working folder
of the process before: `setsid --fork <ide launcher> serverMode`. `<ide launcher>` is
`<app>/bin/<ide>.sh` (`idea.sh`, `pycharm.sh`, `webstorm.sh`, `goland.sh`, `phpstorm.sh`,
`rustrover.sh`). `setsid --fork` makes the IDE independent of the shell.
On a machine with systemd, start it through a scope of its own:
`systemd-run --user --scope --quiet --collect -- setsid --fork <ide launcher> serverMode`.
`setsid` does not leave the cgroup of the shell. If systemd-oomd kills the unit of the
shell, the IDE dies with it. The scope takes the IDE out of that unit. The harness does
this itself when it restarts an IDE.

- **Projects.** A bare `serverMode` start opens each project that has `opened="true"` in
  `<config dir>/options/recentProjects.xml`. To change the set, stop the IDE, change the
  marks, and start it. `--open-product` and `--close-products` do this for a product. At a
  start with no instance up, a project path after `serverMode` opens only that project and
  restores no other project, and a second path is ignored (seen with GoLand in the setup of
  caddy). For this reason the harness always starts a bare `serverMode`. A `serverMode` IDE
  checks the trust of a project: the harness writes a trust entry for each product to
  `<config dir>/options/trusted-paths.xml` while the IDE is down.
- **The fleet process** of an IDE is the JVM (`<app>/jbr/bin/java`) whose command line has
  `-Didea.paths.selector=<Product><version>` and `serverMode`, and no `-Didea.config.path=`.
  Find it with a pattern that does not match your own shell, for example
  `pgrep -af 'paths\.selector=[G]oLand'`.
- **Stop.** Send SIGTERM to the JVM, and wait until the process is gone (the harness waits
  90 s). Never use SIGKILL: the IDE saves its state at the shutdown.
- **Trap: the launcher is not the JVM.** A stop of the launcher can leave the JVM alive (seen
  on WebStorm 2026.2 with `bin/webstorm`). A start after that only gives its arguments to the
  running instance and opens nothing. Stop the JVM first.
- **Trap: a project path for a running instance.** A start while an instance runs hands the
  project path to that instance. It logged `Opening existing project` and then stalled (seen
  on WebStorm 2026.2). Change the open projects only while the IDE is down.
- **Exit with no client.** An instance that an agent started, with no client connected, ended
  cleanly about 9 minutes after its start (seen on a 2026.1 IDE). The cause is not confirmed.
  When an IDE that you started is gone, read the end of its `idea.log` first.

### Change a plugin setting

The plugin keeps its settings for the whole IDE in `<config dir>/options/mcp-plugin.xml`
(Settings → Tools → IdeSense in a window). The option names are the fields of
`McpSettings.State` (`settings/McpSettings.kt` of the plugin code). An absent option takes its
default, and the IDE writes no file while all options have their defaults (seen on WebStorm).
This file turns on each tool except `ide_read_file` and pins the port. Its `disabledTools`
set is the full set:

```xml
<application><component name="McpPluginSettings">
  <option name="disabledTools"><set><option value="ide_read_file" /></set></option>
  <option name="serverPort" value="29174" />
</component></application>
```

The defaults turn off `ide_install_plugin`, `ide_restart`, `ide_read_file`,
`ide_refactor_rename` and `ide_move_file`. Keep `responseFormat` at its default `JSON`: the
harness reads each result text as JSON, so a `TOON` text fails each row.

**Write the file only while the IDE is down.** The IDE keeps its settings in memory and writes
them at its shutdown. So an edit while the IDE runs is lost, also before an `ide_restart`: the
shutdown writes the old state over it. This sequence works:

1. Back up the file.
2. Stop the IDE, and wait until the JVM is gone. The shutdown save is then complete.
3. Write the new file with an atomic replace: a temporary file in the same folder, then a
   rename over `mcp-plugin.xml` (`os.replace` in Python).
4. Start the IDE.

`suite/fleet.py` uses this sequence for `recentProjects.xml` and `trusted-paths.xml`. Do not write
at a fixed time after `ide_restart`: the new process can read its settings some seconds after
the old one ends (seen on GoLand 2026.2: the new server started 7 s after the shutdown line).

**The log is the proof of a bind setting**, not the file and not a fast reconnect. Each server
start writes `Starting MCP Server on <host>:<port>` to `idea.log`. A refused host shows before
it as `Refusing non-loopback bind to '<host>' (not acknowledged in settings); falling back to
127.0.0.1`. `ss -ltn` shows the address that the kernel bound. A non-loopback bind
(`serverHost` with `allowNonLoopbackBind`) gives each enabled tool to each machine that
reaches the port, with no authentication. So test with an address that only the host can
reach (for example the address of the bridge `docker0`), never a LAN address. After the test,
write the backup back with the same sequence, and check for `Starting MCP Server on
127.0.0.1:<port>`.

### Throwaway IDE

A throwaway IDE is a second instance of an installed IDE with its own config, system, plugins
and log folders. Use it for a probe that can harm an IDE, for a check of the first-run
defaults, and for a look at an IDE window. A process with its own `-Didea.config.path` is no
fleet process, so the harness never restarts it. Run rows against it with `--url`.

1. **Root.** Use a root folder with a short absolute path, `<throwaway root>`. The IDE opens a
   unix socket below its folders, and Linux limits a socket path to about 108 bytes.
2. **VM options.** Write `<throwaway root>/ide.vmoptions` with four lines:
   `-Didea.config.path=<throwaway root>/config`, and the same for `idea.system.path`
   (`system`), `idea.plugins.path` (`plugins`) and `idea.log.path` (`log`). The launcher adds
   the file that `<PRODUCT>_VM_OPTIONS` names to `<app>/bin/<ide>64.vmoptions`. Read the
   variable name with `grep -o '\$[A-Z_]*_VM_OPTIONS' <app>/bin/<ide>.sh`. In 2026.2 it is
   `IDEA_VM_OPTIONS` (IntelliJ IDEA), `WEBIDE_VM_OPTIONS` (WebStorm), and the product name for
   the others (`GOLAND_VM_OPTIONS`). A `<PRODUCT>_PROPERTIES` file did not set these paths
   (seen on GoLand 2026.1).
3. **Config.** `cp -a <config dir> <throwaway root>/config`. The copy keeps the trust
   settings and the keymap of the fleet IDE. In the copy:
   - Remove `.lock`.
   - Remove `options/recentProjects.xml`, else the throwaway IDE opens the fleet projects.
   - Add the throwaway project to `options/trusted-paths.xml` (the format of
     `trust_project_paths` in `suite/fleet.py`).
   - Change `serverPort` in `options/mcp-plugin.xml` to a free port, for example 29199. With
     the fleet port the throwaway server cannot bind, and each call goes to the fleet IDE. To
     check the first-run defaults, keep only the `serverPort` option.
4. **Plugins.** Unzip the zip under test into `<throwaway root>/plugins`. The bundled plugins
   come from the IDE install. Another custom plugin loads only when you copy it too.
5. **Project.** Use a copy of a fixture or a small new project, outside `<throwaway root>`.
   Never open a folder that another IDE has open: two IDEs then write its `.idea/`. A copy of
   the Python fixture needs `live-test-python.iml`, `misc.xml` and `modules.xml` from `.idea/`
   of the fleet checkout (git tracks only `modules.xml`). Without them PyCharm has no
   interpreter, and the usage types differ (seen on PyCharm 2026.2).
6. **Start:** `<PRODUCT>_VM_OPTIONS=<throwaway root>/ide.vmoptions setsid --fork
   <ide launcher> serverMode <project>`.
7. **Prove it before the probe.** `pgrep -af 'idea.config.path=<throwaway root>/[c]onfig'`
   must find the new JVM, and `<throwaway root>/log/idea.log` must exist; else stop the new
   process at once. `initialize` on the new port must give the build under test, and a call
   with an unknown `project_path` must list only the throwaway project. Probe only that port.
8. **Stop and clean.** Find the JVM by its config path, never by the product name: the fleet
   instance has the same name. Send SIGTERM, wait until the process is gone, and delete
   `<throwaway root>`. Do not use `pkill -f` with a pattern that your own shell line holds: it
   can stop that shell.

**With no path override, the fleet IDE gets the project.** A wrong variable name or an
unreadable VM options file leaves the default folders. The new process then finds the fleet
instance and hands the project to it. The fleet IDE opens the throwaway project or stalls on
it, and the new process waits or keeps a CPU core busy (seen on GoLand 2026.1 and WebStorm
2026.2). To repair, stop the new process (SIGKILL is safe: it has no state), delete the
throwaway project folder, and restart the fleet IDE: the restart drops the missing project.

#### Throwaway IDE with a display

A throwaway IDE with a display shows the IDE windows (Find Usages, Call Hierarchy, Structure)
next to the tool result of the same instance. Use it to establish what the IDE shows (the
rule "Mimic the IDE" in the root [AGENTS.md](../AGENTS.md)).

- **Display.** Start a virtual X server (for example Xvfb) on a display number of your own:
  on a shared display your keys can go into the windows of another session. Start the IDE as
  above, with `DISPLAY` set and with no `serverMode`: `<ide launcher> <project>`. Check
  `DISPLAY` in `/proc/<pid>/environ` of the new JVM.
- **Keyboard.** Drive the IDE by keyboard (for example `xdotool`), and focus its window first.
  Swing widgets are no X windows: click by pixel only from a screenshot that you read. Open
  the file (`ctrl+shift+n`), then Go to Line (`ctrl+g`): type `line:column` of the tool call,
  Return. Then start the action, for example Call Hierarchy (`ctrl+alt+h`) or Structure
  (`alt+7`).
- **Shortcuts differ** with the IDE and the copied keymap. Seen in 2026.2: Find Usages was
  `alt+F7` in IntelliJ IDEA, `alt+shift+7` in RustRover and WebStorm, and either key in
  different starts of GoLand and PyCharm. For most actions, Find Action (`ctrl+shift+a`) with
  the action name and Return is a safe way.
- **Read the window.** Take a screenshot (for example with `xwd`), crop the tool window, scale
  the crop 2x, and read the image. For a whole tree, click one row, then expand all
  (`ctrl+KP_Add`). The Find tool window can write its tree as text (Export to Text File,
  `alt+o`, seen in 2026.2): for a comparison of line sets, the text is better. By default
  the window shows two usages on one line as one row (seen on WebStorm 2026.2).
- **Questions.** Some IDEs ask a question before a search, for example if Find Usages must
  search the base method (seen on WebStorm, PyCharm and RustRover 2026.2; not on IntelliJ IDEA
  for a Java or Kotlin override). Record the answer with the result. A copy of a Cargo
  workspace asks to attach the Cargo projects, and it stays in dumb mode until the question
  has an answer (seen on RustRover 2026.2).
- **The same instance.** Compare a tool result only with a window of the same instance. A
  window start can load other features than a `serverMode` start (seen on PyCharm 2026.2:
  `Disabled plugins: JetBrains Ultimate` in `idea.log` of the window start). For a case that
  the fixtures do not have, add probe files to the fixture copy: no fixture change, no bless.
- **Dialogs.** A license, agreement or trial dialog is for the owner to answer. Do not
  click it: stop the throwaway IDE, and ask the owner.

## Run the suites against a new build

1. Build the plugin and install it into each IDE. With no window: see "Deploy a build to the
   IDEs". In an IDE with a window: Settings → Plugins → ⚙ → Install Plugin from Disk…, then
   restart the IDE (the plugin is not dynamically reloadable). A dev build gets its version on
   the command line, and a release build has the version of `gradle.properties`: see "Dev
   builds" and "Release" in [CONTRIBUTING.md](../docs/CONTRIBUTING.md).
2. Check that each IDE runs the new version (`serverInfo.version`) and that its fixtures are
   open and indexed.
3. Run both suites, the fixtures and the real products:

   ```bash
   ./live-test/run.py --suite all
   ```

   The product part restarts the IDE of each product. A product with no checkout is
   `SKIPPED`.

   A run passes when its last line is `ALL: <n> passed, 0 failed` and its line `real-products:`
   has `0 skipped`. A `PARKED` row is no failure: it shows an open issue. A release has the
   same pass rule (see "Release" in [CONTRIBUTING.md](../docs/CONTRIBUTING.md#release)).

4. If failures appear:
   - Read each diff carefully. Is the change intentional (it matches the CHANGELOG entry of
     the change) or a regression?
   - Intentional: bless under the bless rule of [AGENTS.md](AGENTS.md)
     (`./live-test/run.py --language <lang> --tool <tool> --bless`; for a product:
     `./live-test/run.py --product <folder> --tool <tool> --bless`; see "Check a bless" in
     CONVENTIONS.md), and commit the changed snapshots with the change. When the change also
     alters a canary row, see `MISCONFIGURED` in "Troubleshooting".
   - Regression: file an issue or revert the change.
5. After a bless, run both suites two times. These runs look for a row whose result differs
   between two equal runs. For such a product row, see "A row that differs between two equal
   runs" in [CONVENTIONS.md](CONVENTIONS.md). For such a fixture row, see "Bless safety" in that
   file.

## Troubleshooting

- **`PRECHECK: cannot reach …`** — the IDE's MCP server isn't running on
  the expected port. Check that the dev plugin is installed and enabled,
  and that the IDE is open. Override the port with `--url` and `--language` if you've
  configured a non-default value in Settings → Tools → IdeSense.
- **`PRECHECK: project is in dumb mode`** — wait for indexing to finish
  in the IDE, then retry.
- **`MISSING (no expected entry for this id)`** — the tool's
  `expected/<tool>.jsonl` doesn't have an entry for this input id. Likely
  you added a new input row and haven't blessed yet. Run `--bless` with `--language` (or
  `--product`) and `--tool` to add it.
- **`ORPHAN expected id …`** — an expected entry whose id is no longer in
  any `inputs/<tool>.jsonl`. Either restore the input row or run
  `--bless --prune` to drop the orphan.
- **`[<product>] MISCONFIGURED: canary row … differs`** — a canary row differs from its
  expected row, and the other rows of the product did not run. The gate and its retry times
  are in "Canary rows" in CONVENTIONS.md. Two causes are possible, and the printed difference
  shows which one:
  - The project model is wrong (dependencies not resolved, another SDK, index not
    complete). Run the `bootstrap.sh` of the product, look at the IDE, and run again.
    Never bless in this state.
  - The plugin changed the output of the tool of that canary row, and the fixture suite
    shows the same change. Then run `--product <folder> --bless --bless-canary` under the
    bless rule of `AGENTS.md`, and read the `git diff` of the expected files before the commit.
- **`MISCONFIGURED` after the first open of a product** — at its first open an IDE can stop
  before it adds a library root (for example the dependency folder of a JavaScript product).
  Then the canary row that resolves into a dependency differs: the gate tries again for the
  readiness time and prints `MISCONFIGURED`. Close the product with `--close-products`, open
  it again, and run again.
- **`<id> met dumb mode: waited <n> s, the row runs again`** — the IDE went to dumb mode
  again after the canary rows matched (a build tool sync, then a refresh). The row waited
  until the IDE was ready and then ran one more time. All waits of a product run share the
  readiness time of the product. When no time is left, a row runs one time only.
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
- **Many rows differ after an update of the IDE** — an update can change names and texts of
  the platform, for example the qualified name of a Python builtin (seen at the update from
  2026.1 to 2026.2). A line shift in a JDK or SDK file changes no row: the harness drops the
  line and the column of each library file ("Path normalization" in CONVENTIONS.md). Read each
  difference, and re-bless under the bless rule of `AGENTS.md`.
- **Kotlin rows fail after an IDE restart, and `ide_diagnostics` on a Kotlin fixture file
  shows unresolved standard library calls** (for example `Unresolved reference 'listOf'` in
  `src/main/kotlin/demo/Normal.kt`) — the Gradle cache (`~/.gradle/caches/modules-2`) lost the
  jars of the fixture. The fixture pins Kotlin 2.0.0 (`fixtures/kotlin/build.gradle.kts`);
  its Gradle wrapper is local and git-ignored. Only the IDE uses these jars, so Gradle can
  clean them out, and the IDE sees the loss at its next start. Resolve the compile classpath
  of the fixture again (`dependencies` gets only the metadata, not the jars):

  ```bash
  echo 'allprojects { tasks.register("resolveCompileClasspath") { doLast { println(configurations.getByName("compileClasspath").resolve()) } } }' > <scratch>/resolve.init.gradle.kts
  cd <fleet checkout>/live-test/fixtures/kotlin && ./gradlew --no-daemon -q --no-configuration-cache -I <scratch>/resolve.init.gradle.kts resolveCompileClasspath
  ```

  Seen on IntelliJ IDEA 2026.2: the IDE used the jars again about 20 s later, with no restart.
- **Kotlin rows fail after an IDE restart with empty results (`"classes": []`,
  `"qualifiedName": null`), and `idea.log` has `Initial load of project-level (project=kotlin)
  libraries. There are 0 libraries to load.`** — the Kotlin fixture lost its Gradle model. The
  IDE keeps the modules of a Gradle sync in its workspace model. It writes them to
  `<system dir>/projects/kotlin.<hash>/external_build_system/modules/` only at a save of the
  project after the model commit. In `serverMode` such a save does not come by itself. Seen on
  IntelliJ IDEA 2026.3 with the product `exposed`: the only project save after a sync came 1 to
  5 s before `External system: commit model`, and `idea.log` had no other save of that project
  in the next 10 and 14 minutes. A stop with SIGTERM, which the harness uses for a project
  switch, saves no project: `idea.log` goes from `Index dispose started` to `IDE SHUTDOWN` in
  less than 0.2 s. A graceful exit saves each project: `ide_restart` goes through
  `ApplicationImpl.exit`, which calls `saveAndCloseProjectsOnExit`
  (`lib/intellij.platform.ide.impl.jar`, IU-263.7307.200), and the module files got the time of
  that restart. Seen on IntelliJ IDEA 2026.3 after the update from 2026.2: the first start with
  the new system folder ran the sync, and the harness stopped the IDE four minutes later,
  before these files existed. The log of the next start has the model of the cache (`There are
  2 libraries to load`) and then `Apply JPS storage (iml files)`. Each later start has `There
  are 0 libraries to load` and no new sync, and 74 of the 119 Kotlin rows failed. To repair:

  1. Stop the IDE. Move `external_build_system`, `project-model-cache` and `cache-state.xml`
     out of `<system dir>/projects/kotlin.<hash>/`, and start the IDE. It runs the sync again:
     `idea.log` has `Gradle (kotlin): Execution RESOLVE_PROJECT:<n> is finished`.
  2. When the sync has ended, restart the IDE one time with `ide_restart` (a deploy also does
     it). Then check that the folder `external_build_system/modules/` exists. Do not wait for a
     save in `serverMode`: two observations saw these files 2 seconds and 5 minutes after a
     sync, but with the product `exposed` no save came in 10 and 14 minutes.

  The same holds for a product that the IDE imports with Gradle, and after each move to a new
  version of the IDE, because the new version has a new system folder. For such a product, the
  restart of step 2 must come after its first sync and before the first project switch
  (#276). The setup step is in the `notes.md` of the product (for example
  `real-products/_setup/exposed/notes.md`).
- **Java or Kotlin rows differ after an edit of fixture files from outside the IDE** — the
  IDE has not seen the change (seen on IntelliJ IDEA). Before the run, call `ide_sync_files`
  with only `project_path` for each project, `java` and `kotlin`.
- **The output of a harness run looks stopped when it goes to a file** — Python buffers it.
  Use `python3 -u live-test/run.py … > <log file>`. A run in the background starts in the
  current folder of the shell, so `./run.py` fails with exit code 127 outside `live-test/`.
- **A defect that no row shows** — some defects show only in `idea.log`. After a live run,
  read `idea.log` of each IDE for `WARN` and `SEVERE` entries with a stack frame of the
  package `com.github.vcth4nh.idesense` or the text `Plugin to blame`. Each such entry is a
  defect of the plugin. This is also true when the tool result is correct. Write an issue for
  it. An entry continues up to the next time stamp. Group the entries by message and by the
  first plugin frame. The plugin writes no log line for each tool call, so match an entry to a
  call by its time.
- **An old commit in the checkout whose fixtures the IDEs have open** — never check out a
  commit from before the move of the fixtures to `live-test/fixtures/` (#138) there. Git
  moves only the tracked files back; the files of the IDEs and tools (`.idea/`, `.venv`,
  `gradlew`, `vendor/`) stay behind. A commit has the move when
  `git merge-base --is-ancestor 9c89a6a <commit>` succeeds. Rebase an older branch first.
- **Result that looks wrong but the IDE consistently returns it** — see
  the `GROUND-TRUTH.md` of that language or product. Some IDE quirks are blessed on
  purpose; don't try to "fix" them by changing the probe.

## Why not in CI?

The harness POSTs to live IDE-hosted servers, so it requires running
IDEs. CI runners don't carry a desktop IDE. Headless IDE execution
(`./gradlew runIde`) plus a fixture-loading script could enable this in
the future.
