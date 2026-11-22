# Agent benchmark

The agent benchmark runs a coding agent (Claude Code in print mode) in a container on closed
questions about the code of a pinned product, with and without the plugin, and scores each answer
against a key. A batch runs the questions, arms and models of a plan, and reports numbers. The
method (the questions, the arms, one run, the score, the statistics, the controls and what a
result can claim) is in [METHOD.md](../METHOD.md), section 5. The keys come from
[keygen/README.md](../keygen/README.md).

This file also holds the parts that the audit shares with the benchmark: the settings, the data
root, the setup from zero and the plugin build under test.

The commands run from the root of the repository. `B` is the data root:

```bash
B="${BENCH_ROOT:-$HOME/dev/idesense-bench}"
```

## Files

| Path | Content |
|---|---|
| `questions/<name>.md`, `keys/<name>.json` | The tracked questions and their keys (format: [questions/README.md](questions/README.md)) |
| `score.py` | The score of one answer against one key; standard library only |
| `qfiles.py` | Export, check and rescore of the questions and keys |
| `sets.py` | The set makers: challenge sets of key records, chosen by fixed rules and a seed |
| `plans/<name>.json`, `planfile.py` | The tracked batch plans, and their check |
| `runner.py` | One run, a batch of runs, the connection check |
| `claude_code.py` | The code that is specific to Claude Code: arguments, transcript parser, secret, MCP configuration |
| `proxy.py` | The filter proxy between a run container and a benchmark IDE |
| `images.py`, `image/Dockerfile`, `image/entry.sh` | The product images, their build and their gate |
| `build.py`, `ide/bench-ide.sh` | The plugin build under test, and the start, stop and status of a benchmark IDE |
| `triage.py`, `ledger/` | The report of a batch, and one tracked summary for each batch |
| `notes.json` | The note texts of arm `PFN`: for each language, a text for each tool |
| `tests/` | The unit tests and their transcript fixtures |

The module text at the top of each Python file gives each option, each file format and each exit
code.

## Settings and the data root

The settings come from environment variables. No tracked file holds a value of one machine.

| Variable | Content | Default |
|---|---|---|
| `BENCH_ROOT` | The data root | `~/dev/idesense-bench` |
| `BENCH_SLOTS` | The slots root | `~/dev/ws` |
| `BENCH_APPS` | The Toolbox apps folder, with the IDE installs | `~/.local/share/JetBrains/Toolbox/apps` |
| `BENCH_SECRET_FILE` | The file of the secret of the login: one line | No default |
| `BENCH_LOGIN` | `api-key` (the secret goes to `ANTHROPIC_API_KEY`) or `subscription` (the token of `claude setup-token`, to `CLAUDE_CODE_OAUTH_TOKEN`). No container run with `subscription` is verified yet. | `api-key` |
| `BENCH_PLUGIN_ZIP` | `bench-ide.sh start`: the plugin zip to install. `bench build -start` sets it. | |
| `BENCH_IDE_XMX` | `bench-ide.sh start`: the heap of a benchmark IDE | `4096m` |
| `BENCH_TRACE_OUT` | The trace file of a copy of `gokeys trace` | |

A path must be absolute. The data root and the slots root are used as real paths: a symbolic link
in them is resolved. No message shows the value of `BENCH_SECRET_FILE` or of `BENCH_LOGIN`. The
runner sets `BENCH_SLOT` and `BENCH_AID` in a container. `BENCH_PORT` and `BENCH_INIT` are for the
tests only.

The data root is outside the repository: it is large, the worktrees share it, and it holds product
source.

```
<data root>/
  trees/<tree>/  <tree>.manifest  slots.json   the master trees, their manifests, the slots
  keys/<tree>/                    the full key files and the calls files
  plugin/                         the plugin zips under test (bench build)
  ide/<goland|pycharm>/           the folders of the benchmark IDEs (bench-ide.sh)
  images/<product>.json           the records of the product images
  proxy/routes.json  proxy/log/   the routes of the proxy and its request logs
  audit/<build>/                  the audit results (audit verdict run)
  runs/<batch>/  runs/<batch>.triage/   the run records of a batch, and its report
  additions.json                  the rows of the arms PFR and PFL
  state/lock                      the lock of the benchmark IDEs
  scratch/                        the build context of an image, the gate logs, the gokeys binary
```

A slot is a copy of a master tree at a neutral path, `<slots root>/<slot id>/<product>`. The slot
id comes from the name of the tree. The agent in the container and the benchmark IDE see the same
slot path.

**The lock.** One user of the benchmark IDEs at a time: `runner batch`, a single `runner run`,
`runner handshake`, each command of the audit that calls an IDE (see
[audit/README.md](../audit/README.md)) and `bench build -start` hold the lock
`<data root>/state/lock`. A second user stops at once with a message that names the holder. A
machine has one data root: two data roots give two locks for the same IDE ports.

## Setup from zero

Requirements:

- Linux with Docker, Python 3.10 or later, git, Go, uv, `curl`, `unzip` and `ss`.
- A JDK for the Gradle build of the plugin (`jvmToolchain` in `build.gradle.kts`; see "Build and
  run" in [CONTRIBUTING.md](../../docs/CONTRIBUTING.md#build-and-run)).
- GoLand and PyCharm from the Toolbox app. The benchmark IDEs use these installs with folders of
  their own. Start each IDE one time and activate it: at its first start, a benchmark IDE copies
  the config folder and the plugins of the installed IDE.
- A data root with a short path: the path of each folder of a benchmark IDE (`$B/ide/<ide>/...`)
  has 60 characters or fewer, else `bench-ide.sh` refuses it.
- The checkouts of caddy and beets in `live-test/real-products/` (see "Get a checkout" in
  [README.md](../README.md#get-a-checkout)).

1. **Product trees.** Make the tree of each product: "Trees" in
   [keygen/README.md](../keygen/README.md#trees).
2. **Compiler key of caddy.** Build `$B/scratch/gokeys-bin` and write
   `$B/keys/caddy/symbols.jsonl`: the first two commands of "Go keys" in
   [keygen/README.md](../keygen/README.md#go-keys), for the tree caddy. A Go plant needs both.
3. **Planted trees.** Make the planted trees: "Trees" in
   [keygen/README.md](../keygen/README.md#trees). `./live-test/run.py common trees digests` prints
   `ok` for each tree.
4. **Keys.** Make the other key files of each tree: "The key files" in
   [keygen/README.md](../keygen/README.md#the-key-files).
   `./live-test/run.py bench qfiles check -data` prints `0 problems`.
5. **Slots.** Make the slot of each tree of `keygen/trees.json`:

   ```bash
   for t in $(python3 -c 'import json; print(*json.load(open("live-test/keygen/trees.json")))'); do
     ./live-test/run.py common trees slot "$t"
   done
   ```
6. **Images.** Build the image of each product, and check it:

   ```bash
   ./live-test/run.py bench images build caddy
   ./live-test/run.py bench images gate caddy
   ./live-test/run.py bench images build beets
   ./live-test/run.py bench images gate beets
   ```

   The build reads the pins of [`live-test/manifest.json`](../manifest.json) and stops when the
   file or a pin is absent. `gate` prints one line with PASS or FAIL for each check, and exits 0
   only when each check passes.
7. **Benchmark IDEs.** Build the plugin and start the benchmark IDEs with it:
   `./live-test/run.py bench build -start` (see "The plugin build under test").
8. **Proxy.** Start the proxy in a terminal of its own, then check the connection of each image:

   ```bash
   ./live-test/run.py bench proxy serve -routes "$B/proxy/routes.json" -log-dir "$B/proxy/log"
   ./live-test/run.py bench runner handshake -product caddy
   ./live-test/run.py bench runner handshake -product beets
   ```

   The proxy listens on `172.17.0.1:29380`, the address of the bridge `docker0`. `handshake` needs
   no secret, and exits 0 when Claude Code in the image reached the IDE through the proxy.

A run also needs the secret: write it into a file outside the repository, and set
`BENCH_SECRET_FILE` to its path.

## The plugin build under test

```bash
./live-test/run.py bench build           # build the plugin of HEAD, and copy the zip to the data root
./live-test/run.py bench build -start    # also stop each benchmark IDE and start it with the zip
```

The version of the build is `<pluginVersion of gradle.properties>-bench.<the first 7 hex digits
of HEAD>`, so the `serverInfo.version` of a benchmark IDE names the commit of the plugin code. The
command refuses to build when a file outside `live-test/` and `docs/` has a change, or when such a
file is untracked and not ignored: commit the change first. The zip goes to
`$B/plugin/idesense-<version>.zip`. When that file exists, the command runs no Gradle. With
`-start`, it takes the lock, and stops and starts GoLand with the caddy slots and PyCharm with the
beets slots. After a failure, its last line is `build: <reason>`.

The benchmark IDEs are GoLand on port 29374 and PyCharm on port 29372, with their folders in
`$B/ide/<ide>/`. They never use a fleet port (29170 to 29178). When systemd can give one,
`bench-ide.sh start` runs a benchmark IDE in a systemd scope of its own (the header of
`ide/bench-ide.sh`). The scope is below the user manager: on a machine where the user has no
linger (`loginctl enable-linger`), the end of the last session of the user stops the IDE.

```bash
live-test/bench/ide/bench-ide.sh status goland     # serverInfo.version and the open projects
live-test/bench/ide/bench-ide.sh stop pycharm
```

`bench-ide.sh` takes no lock: change the build with `bench build -start`. Stop a benchmark IDE
only when no command holds the lock.

## Questions, keys and plans

The format of a question and of a key is in [questions/README.md](questions/README.md). The full
key records of the data root, and the fields `family` and `coupled` of a Go key record, are in
"Go keys" in [keygen/README.md](../keygen/README.md#go-keys).

```bash
./live-test/run.py bench qfiles check          # the pairs, names, fields, pins, answer lists, {root}, answer paragraph
./live-test/run.py bench qfiles check -data    # also: each answer equals a fresh view of the full key file
./live-test/run.py bench qfiles rescore "$B/runs"   # the stored runs, scored again with the present keys
```

A plan is `plans/<name>.json`:

```json
{"rule": "<one sentence: how the questions were chosen>",
 "questions": ["caddy-impls-validator"],
 "arms": [{"arm": "C"}, {"arm": "PS", "aid": "skill"}],
 "models": ["claude-haiku-5-5"],
 "runs": 1}
```

An arm entry has `arm`, and can have `aid` (`skill` or `rule`) and `variant` (`instructions`,
`no-tool-search` or `guide`). A batch runs each question with each model, each arm entry and each
run number. The tracked plans:

| Plan | Use |
|---|---|
| `smoke` | The first batch on a new build or a new image: it proves the chain at a low cost |
| `dev` | A batch during development |
| `release` | Each tracked question; the arms and the models are in the plan file |

The `rule` of each plan says how it chose its questions. `./live-test/run.py bench planfile check
smoke dev release` prints the run count of each plan, or its problems.

## Runs

```bash
./live-test/run.py bench runner run -question <name> -arm <arm> -model <model> -batch <batch> [options]
./live-test/run.py bench runner batch -plan <plan name or file> -batch <batch> [-jobs 2] [-seed 1] [-plugin-version <text>]
```

The arms and their meaning are in [METHOD.md](../METHOD.md), section 5.2. The options of `run`:

| Option | Effect |
|---|---|
| `-aid skill\|rule` | Arm `PS` only: the aid that the entry script installs |
| `-variant instructions\|no-tool-search\|guide` | Arms `P`, `PS` and `PF`: other server instructions, or no tool search |
| `-no-tools` | Arm `C` only: the agent has no tools (the memory probe) |
| `-stop-after-tools N` | Stop the container after the N-th tool call (the adoption probe) |
| `-env-scrub` | Claude Code removes the credentials from the environment of its shell |
| `-n N` | The run number (default 1) |
| `-plugin-version <text>` | The expected `serverInfo.version`; default: the version of the IDE at the start |
| `-dry-run` | Print the docker command as a JSON list, and do nothing else |

A plugin arm needs the proxy. A run that is not a dry run needs the secret file. A batch reads its
plan, refuses a batch folder that holds another plan, and skips a run that has a record: a batch
that stopped continues at its next start. Use a new batch name for a new plan. Before its first
run, a batch reads the plugin version of the IDE of each product with a run to do, also with
`-plugin-version`. It stops with exit 2, before any write, when an IDE gives no version, when the
version is not the option, or when the plugin version or the image of a product differs from the
`manifest.json` of an earlier start of the batch: use a new batch name for a new build or a new
image.

```
<data root>/runs/<batch>/
  plan.json                 the plan of the batch
  manifest.json             the recorded manifest of the last start with a run to do
  <run id>/                 run.json  transcript.jsonl  stderr.txt  proxy.jsonl
  <run id>.invalid-<k>/     a try that the batch set aside (also .api-error-<k>)
```

A run id is `<question>__<arm label>__<model>__<n>`. The arm label holds the arm and its options,
for example `PS-skill` or `C-no-tools`. `run.json` comes last: a folder with `run.json` holds a
finished run.

| Fields of `run.json` | Content |
|---|---|
| `id`, `question`, `question_sha256`, `key_sha256` | The run, its question, and the SHA-256 of its question file and its key file |
| `arm`, `aid`, `variant`, `no_tools`, `stop_after_tools`, `env_scrub`, `login`, `model`, `n` | The options of the run |
| `image_id`, `started`, `seconds`, `plugin_version_start`, `plugin_version_end` | The image, the start time, the duration, the plugin version at the start and at the end |
| `outcome`, `reason`, `exit_code` | The outcome (below) and its reason |
| `cost_usd`, `turns`, `usage`, `model_usage` | The cost and the tokens |
| `tools`, `first_tools`, `mcp_calls`, `mcp_status` | The tool calls, the first five tool names, the IDE calls, the MCP servers of the agent |
| `answer`, `invalid`, `score` | The answer lines, the entries that cannot be read, the score |
| `leak_words` | The count of each word that can name the benchmark in the transcript |

The outcomes: `ok`; `no_answer`, `budget`, `timeout` and `error` (no usable answer); `stopped`
(`-stop-after-tools`); `invalid`, `api_error` and `key_leak` (no measurement). The module text of
`runner.py` gives the rule of each outcome.

| Exit code | `run` | `batch` |
|---|---|---|
| 0 | `run.json` is written, also for `invalid` | The runs are done |
| 1 | The outcome `error` | |
| 2 | No run starts | A run could not start; no new run starts |
| 3 | The API refused or failed; no measurement | Two API errors in one run; no new run starts |
| 9 | A key leak: the files of the run are deleted | A key leak; no new run starts |

The arms `PFR` and `PFL` read their rows from `$B/additions.json` (format in the module text of
`runner.py`). A run of these arms with no entry for its question does not start.

## Triage and the ledger

```bash
./live-test/run.py bench triage report -batch <batch>   # runs.jsonl and summary.md in $B/runs/<batch>.triage/
./live-test/run.py bench triage table -batch <batch>    # one line for each run
./live-test/run.py bench triage ledger -batch <batch>   # the tracked summary live-test/bench/ledger/<date>-<batch>.md
```

`summary.md` has the tables "Batch", "By question, model and arm", "Paired differences",
"Adoption" and "Flags". The ledger summary holds the plan, the recorded versions (with the agent
version of each image), the plugin versions and the image ids of the run records, and these
tables, and no path and no transcript text. A maintainer compares two batches by reading their
summaries: [METHOD.md](../METHOD.md), section 6, says what must be equal.

## Procedures

### A development batch

1. Commit the change, then `./live-test/run.py bench build -start`.
2. Start the proxy if it does not run (step 8 of "Setup from zero").
3. `./live-test/run.py bench runner batch -plan smoke -batch <batch>-smoke`. Read the transcript of
   one plugin run (`transcript.jsonl` in its run folder): the agent called the IDE, and the answer
   has a score.
4. `./live-test/run.py bench runner batch -plan dev -batch <batch> -jobs 2`.
5. `./live-test/run.py bench triage report -batch <batch>`. Read `summary.md`, and each flag.
6. `./live-test/run.py bench triage ledger -batch <batch>`, and commit the summary.

### A release batch

1. Check out the release commit. Run the audit first (see "After a change of a usage,
   implementation or caller tool" in [audit/README.md](../audit/README.md)).
2. `./live-test/run.py bench planfile check release` prints the run count. The batch costs money
   for each run.
3. Run the plan `smoke`, then the plan `release`:
   `./live-test/run.py bench runner batch -plan release -batch <batch> -jobs 2`.
4. Write the report and the ledger summary as for a development batch, and commit the summary.
5. To compare with an earlier release, read the two summaries as [METHOD.md](../METHOD.md),
   section 6, says.

### A new question

1. Make or update the key file of the tree (see [keygen/README.md](../keygen/README.md)).
2. Write a challenge set: a set maker of `sets.py` with `-out "$B/challenges/<set>.jsonl"`, or a
   JSONL file of challenge records (format in the module text of `sets.py`). The `note` of a
   record says how it was chosen.
3. `./live-test/run.py bench sets show -set "$B/challenges/<set>.jsonl"` prints the line counts and
   the prompt of each challenge.
4. `./live-test/run.py bench qfiles export "$B/challenges/<set>.jsonl"` writes a question and a key
   for each challenge (one for each group of challenges with the same text and answer). Then read
   `git status --short live-test/bench/questions live-test/bench/keys`. The command writes over a
   file with the same name, so a changed file of an earlier question needs a review.
5. `./live-test/run.py bench qfiles check` and `./live-test/run.py bench qfiles check -data`: both
   print `0 problems`.
6. Run the memory probe of the question for each model of the plans (arm `C` with `-no-tools`),
   and apply the rule of [METHOD.md](../METHOD.md), section 5.6.
7. Add the name to a plan, and run `./live-test/run.py bench planfile check <plan>`.

## Tests

The unit tests of the benchmark run with the other unit tests of `live-test/`: see
"Requirements" in [README.md](../README.md#requirements).
