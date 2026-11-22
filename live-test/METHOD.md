# Method of the live tests

This file gives the method of the four instruments of `live-test/`: what each one measures, where
its truth comes from, and what a result can claim. The table of the instruments is in "The four
instruments" in [README.md](README.md). The commands and the file formats are in the README of
each instrument.

## 1. Two kinds of truth

- **Snapshot.** The blessed output of a tool: a bless (the option `--bless` of the suites) writes
  the output of a run as the expected result of a row. Before the bless, a person or an agent
  checks the output against the IDE. Its rule is "mirror the IDE" (the rule "Mimic the IDE" in the root
  [AGENTS.md](../AGENTS.md)). The fixture suite and the product suite use snapshots.
- **Key.** An answer that no IDE and no plugin made. It comes from the Go compiler library, from
  a Python scan, from reflection in the interpreter of the product, or from a run-time trace.
  Each key source has a proof by a second method (section 3). The audit and the agent batch use
  keys.

A snapshot shows each change of the output: a field, an error text, a page limit. It cannot show
an error that the IDE and the tool share. A key shows such an error, but it covers only the lines
of an answer: it cannot show a changed field or a changed error text. So the instruments stay
separate. They use the same products and the same product table,
`real-products/products.json`.

## 2. The suites

- **A row** is one tool call (a line of `inputs/<tool>.jsonl`) and its blessed result (a line of
  `expected/<tool>.jsonl`). A run passes when the result of each row equals its expected row.
- **The fixture suite** runs the rows on small projects whose files were written for the probes,
  one project for each language. **The product suite** runs the rows on real products at a pinned
  release.
- **The bless rule** decides when an output becomes the expected result: see "Bless" in
  [AGENTS.md](AGENTS.md#bless).
- **Compare modes.** A product row compares the whole result, the result in its order, or only
  the counts of a cut result: see "Compare modes" in
  [CONVENTIONS.md](CONVENTIONS.md#compare-modes).
- **Canary rows** pin the project model of a product. When one differs, the other rows of the
  product do not run (see "Canary rows" in [CONVENTIONS.md](CONVENTIONS.md#canary-rows)).

**Limit.** An error that the IDE and the tool share passes: the bless made it the expected
result. The keys of the audit and of the agent batch exist for this reason.

## 3. The keys

Rule: a key never comes from the plugin or from an IDE. Each key source has a proof, and the proof
uses a second method. The commands are in [keygen/README.md](keygen/README.md). A proof with no
tracked command is made by hand when the key is made.

| Key | Source | Proof |
|---|---|---|
| Go symbols: uses, families, implementers | The name resolution of the Go compiler library (`go/types`), one load for each build configuration (Linux, Windows, macOS), test code included | `gokeys accept` renames the key lines of each chosen record (`-ids` or `-sample`) in a copy of the tree, and each configuration must type-check. A unit test (`TestAcceptFailsWhenOneRequiredSiteIsAbsent`) shows that the check fails when one line is absent. |
| Python uses | A token scan, only for a function or a method whose name has one definition and no other meaning in the tree (the unique-name rules of `pykeys unique`) | A second scan with a different method, and a run-time trace of the test suite, give the same lines. Made by hand when the key was made; no tracked command. |
| Python subclasses | Reflection in the interpreter of the product | Two runs give equal files. Made by hand when the key was made; no tracked command. |
| Planted trees | A copy of a tree in which 4 methods with unique names, on 4 unrelated types, get one shared name. The key is the state before the rename. | Go: the key equals the compiler key of the planted tree. Python: the test suite gives the result of the base tree, and the call sites that a run-time trace logs are compared with the key. Both made by hand when the key was made; no tracked command. `plant make` checks only the rename. |
| Go callers | `gokeys calls`: each use of a function declaration, with the declaration that holds it and whether it is a call | `gokeys calls -check`: the static calls of the SSA form of the program (`go/ssa`) must give the same pairs of caller and callee in each configuration. |
| Python callers | `callkeys pycalls`: the uses of the unique-name keys, with the outermost `def` that holds each use (from the syntax tree) | `callkeys tracecheck`: each call site that a trace of the test suite logs for the target and for its direct callers must be in a function of the key. |
| Go callers through an interface value | `callkeys dynmake`: the static callers, and the callers that a run-time trace of the test suite logs (`gokeys trace` makes a copy of the tree in which each target logs its call stack; no line of a file moves) | Each traced caller must be a static caller, or it must hold a call site of an interface method that the target implements. A target that breaks this rule gets no key. |

A planted tree exists because a Python method with a common name has no key that a scan can prove.
The plant makes a common name whose key is known. In such a tree a text search finds the uses of
all four methods, and only the key knows which use belongs to which method.

### 3.1 Line classes

Each line of a key has one class:

- `required`: an exact answer has the line.
- `forbidden`: an exact answer does not have the line (for example a line with the same name that
  is a different symbol).
- `dnc` (the name in a tracked key of `bench/keys/` is `not_counted`): the key does not decide
  if an answer has the line, and the score does not count it.
  Examples: the declaration of the symbol itself, a comment, a use that a rename can change and
  need not change.

An answer line that the key does not hold is a false line, as a `forbidden` line is.

### 3.2 Caller keys are exact keys

A caller key holds the functions that call the target (level 1) and the functions that call these
callers (level 2). A target gets a key only when each call in the chain is certain:

- each use of the target, and of each level-1 caller, is a call inside a function;
- none of these functions is used as a value, implements an interface method (Go), or has another
  open cause of `callkeys make` (the module text of
  [`keygen/callkeys.py`](keygen/callkeys.py) lists them).

So such a caller key has no chain through an interface value, a function value or a call by a
computed name.

A call inside a function literal, a lambda or a nested function counts for the outermost function
declaration that holds it. The text of the question says so, and the caller audit maps a node of
the IDE to that function in the same way.

### 3.3 Caller keys through an interface value

A Go method that implements an interface method can get a call through an interface value. No
compiler fact names the callers. The key of such a method has three classes of callers:

- `required`: a function with a call that the compiler resolves to the method, and a function that
  the run-time trace shows as the direct caller of the method;
- `dnc`: a function with a call site of an interface method that the method implements, when no
  trace proves the call, and a function of the tree that reaches the method only through library
  code;
- each other function is a false line.

The trace is a lower limit: it proves only the calls that the test suite makes. So the questions
take methods with few callers that are not decided. The question asks for one level of callers.

## 4. The audit

The audit asks: what do the tools of the plugin answer for each symbol of a key file, with no
agent? It calls the tools on a benchmark IDE that has the tree open, and compares each answer with
the key. [audit/README.md](audit/README.md) has the commands. `audit/audits.json` lists the audits
of a full run.

| Kind | Tools | The answer lines |
|---|---|---|
| `symbols` | `ide_find_usages` at the declaration, all pages | the usage lines, against the usages view of the key (below) |
| | `ide_find_implementations` at an interface or a class | the declaration lines of the implementers |
| | `ide_find_definition` at up to 5 required sites | correct when the result is a declaration line of the family |
| `callers` | `ide_call_hierarchy`, callers, depth 2 | each node mapped to the outermost function that holds its line |
| `dyn` | `ide_call_hierarchy`, depth 1, and `ide_find_usages` | each node or row as the outermost function that holds its line |

**The usages view.** A key line of a symbols key has the meaning of a rename: each use of each
member of the family is `required`. Find Usages lists the uses of the symbol itself and, for a
method, the uses of the interface methods that it implements. So the usages view counts a required
line of another relation (a subtype, a sibling, an embedded field) as `dnc`, and the audit counts
these lines apart.

**Marks.** A usage row can have the field `match`: `BASE` (the row refers to a base declaration)
or `DYNAMIC` (only the name matches). An answer line whose rows all have `match` is marked. A
marked line that the key does not hold is no false line: the audit lists it apart (`marked`), and
it is in no precision.

**The verdict.** One disagreement line holds one symbol and one tool: the missed lines, the false
lines, the marked false lines and the error texts. A tool error is a disagreement, as a missed line
is. The accepted list of a product (`audit/accepted/<product>.jsonl`) holds the disagreements that
a maintainer accepts. Each accepted line names a cause of `audit/accepted/causes.json`: a known
reason, for example a behaviour that the IDE shows too, or an open defect with its issue. The
owner of the repository permits each cause. Then for each audit:

- `fail`: the audit found a line that the accepted list does not hold. A changed line is a new
  line.
- `wait`: no new line, but an accepted line that stays has no cause, or its cause has no
  permission, or an accepted line is of a symbol that the audit did not ask about (`not audited`,
  for example a symbol that a sample run did not pick).
- `pass`: each found line is on the list with a permitted cause, and the audit asked about each
  symbol of the list.

An accepted line of a symbol that the audit asked about, and that the audit no longer finds, is
reported as `gone`, and it does not change the result. The total of a full run is `fail` when an
audit fails, else `wait` when an audit waits, else `pass`. The verdict needs no earlier build: it
compares one build with the keys and the list.

When the IDE is not in smart mode at the start, the audit waits for it. When the IDE is not ready
for a call during a `symbols` audit, that audit gets `wait`, not `fail`: run it again. When the
server version differs between the start and the end of an audit, the audit gives no verdict:
another build ran in between.

**Limit.** The audit sees only the lines of an answer. A changed field, a changed note or a
changed error text that keeps the lines passes. The suites see these changes.

## 5. The agent batch

The batch asks: does a coding agent give a more correct answer about code when it has the tools
of the plugin? It runs the same agent on the same question with the tools and without them, and it
scores each answer against a key. [bench/README.md](bench/README.md) has the commands.

### 5.1 Questions

Each question is a closed list question about one symbol of a tree. The agent answers with the
JSON object `{"sites": ["<path>:<line>", ...]}`.

| Family | The answer lines |
|---|---|
| `refs` | Each line that calls or names the symbol |
| `impls` | The declaration line of each type that implements the interface, or of each subclass |
| `rename` | Each line that a rename of the method must change |
| `callers` | The declaration line of each function that calls the function, and of each function that calls one of these callers |
| `dyncallers` | The declaration line of each function that calls the method, directly or through an interface value |

A program chooses the questions by fixed rules and a seed (the set makers of
[`bench/sets.py`](bench/sets.py)). A question has a `hard`, `random` or `control` pick, and the
key holds the rule of its pick (`pick.rule`). A hard pick has a class, and its rule is written
before the first run. A random pick and a control pick are seeded choices among the records that
fit a size condition, and the rule gives the seed and the number of candidates. Examples of classes: types that get a method from an embedded type, many
lines with the same name, lines in a file that the build of the machine does not compile, a planted
name, a long list, a call inside a function literal, a property.

A plan (`bench/plans/<name>.json`) names the questions, the arms, the models and the runs of each
cell of a batch. It has a `rule` sentence of its own, which says how the questions of the plan
were chosen (it is not the `pick.rule` of a key).

### 5.2 Arms

| Arm | Content |
|---|---|
| `C` | No MCP server (the control) |
| `P` | The MCP server of the IDE of the product, through the filter proxy, with no hint |
| `PS` | `P`, plus an aid that the plugin can install: the skill or the rule file |
| `PF` | `P`, plus one sentence in the task that tells the agent to use the IDE tools |
| Test arms | `PF`, plus one change: a note in a tool result (`PFN`, `PFI`), more rows in a usage result (`PFR`, `PFL`), one more sentence in the task (`PFG`, `PFS`) |

The variants of `P`, `PS` and `PF` change the server instructions (`instructions`, `guide`) or
turn off the tool search of the agent (`no-tool-search`). The module text of
[`bench/runner.py`](bench/runner.py) gives each arm and each variant exactly. A test arm measures
the effect of a possible plugin change before the plugin changes.

`PF` against `C` measures the value of the tools when the agent uses them. `P` against `C`
measures the plugin as a user gets it, and that result depends on whether the agent calls the
tools at all.

### 5.3 One run

- **Isolation.** One container, one question, one new agent. The container has no mount, no host
  network mode and no Docker socket. No key file goes into an image or a container.
- **Tools.** The agent has each normal tool of Claude Code: the shell, the file tools and the
  search tools. No arm takes a tool away. Only the memory probe (section 5.6) runs with no tools.
- **Tree.** The tree is at a neutral path, the slot path. The path has no word that tells the
  agent of a benchmark. The benchmark IDE has the same tree open at the same path.
- **Proxy.** The container reaches the IDE only through a filter proxy. The proxy passes a fixed
  list of tools: no rename, no file move, no plugin install, no restart.
- **Limits.** A wall-clock limit and a cost limit for each run (`WALL_LIMIT` in `bench/runner.py`,
  `--max-budget-usd` in `bench/claude_code.py`). The agent version and the effort are fixed.
- **Record.** Each run keeps its transcript, the log of its IDE calls, its cost, its answer and its
  score, and the SHA-256 of its question file and its key file.

### 5.4 Score

- **Exact.** An answer is exact when it has each required line, no forbidden line and no false
  line. Lines of the class `dnc` are not counted.
- **Other measures.** Precision, recall and F1 over the lines, the cost, the time, the turns and
  the tool calls of the run. An answer line whose path is no file of the tree is not scored
  (`outside`). An entry that cannot be read counts as `invalid`.
- **A run with no usable answer** (a time-out, the cost limit, no answer, an error of the agent)
  has F1 0 and is not exact.

### 5.5 Statistics

- **Unit.** The unit is the question. Each question has some runs for each model and each arm.
  The value of a question is the mean of its runs.
- **Comparison.** The paired difference of two arms for each question: each plugin arm against
  `C`, and each test arm against `PF`. The batch gives the mean of the differences over the
  questions, with a 95 % bootstrap interval (`bootstrap` in [`bench/triage.py`](bench/triage.py)).
- **Adoption.** For each plugin arm, the share of the runs that call an IDE tool in their first
  five tool calls.
- **Excluded runs.** A run with the outcome `invalid`, `api_error` or `key_leak` is no
  measurement. It is counted, and it is in no mean.

### 5.6 Controls

- **Memory probe.** The question runs in arm `C` with no tools. A question for which a model gives
  more than half of the required lines from memory is replaced.
- **Audit.** The audit (section 4) shows what the IDE returns before an agent reads it, and each
  difference has a cause.
- **Smoke batch.** The plan `smoke` runs first. It proves the chain (image, proxy, IDE, agent,
  score) at a low cost. Read one of its transcripts before a larger batch.
- **Plugin version.** The runner reads the version of the plugin at the start and at the end of
  each run. A run whose version differs, or whose IDE left smart mode, is `invalid`.
- **MCP connection.** A plugin arm needs its server with the status connected, and arm `C` needs
  no server. Else the run is `invalid`.
- **Secret scan.** The runner searches each output file of a run for the secret of the login. A
  hit deletes the files of the run and stops the batch.
- **Leak words and repository access.** The runner counts the words that name the benchmark in
  the transcript. The triage flags a run whose shell or web tool names the folder `bench/keys` or
  this repository: such a run can read its key.
- **Invalid runs.** A run with the outcome `invalid` is set aside and runs again one time.

## 6. The manifest, and the comparison of two batches

**Tracked.** [`manifest.json`](manifest.json) holds the versions that a result depends on: the
IDE builds of the fleet (the benchmark IDEs use the same installs), the version of Claude Code,
the base image and the tool chains of the product images, and the models of the tracked plans. It
holds no plugin version: the plugin build is the input under test. The product pins are in
`real-products/products.json`.

**Check.** At its start, a live suite run, an audit and a batch compare the IDEs of the machine
with the manifest. A difference prints a line `manifest: ...`. The manifest is a reference: no
instrument stops for a difference.

**Recorded.** Each batch folder and each audit result gets a `manifest.json` with the real values:
the fields of the tracked file, the IDEs of the machine, the commit of the repository (and whether
a tracked file differed from it), and the plugin version. A batch also records the models of its
plan, the image ids, the slots root, the login kind, and the SHA-256 of the question file and the
key file of each question of its plan. The summary of a batch in `bench/ledger/` shows the
versions of this record: the plugin, the agent, the models, the image ids, the commit, the login
kind and the benchmark IDEs. The SHA-256 values of the questions and the keys stay in the batch
folder of the data root.

**The batch reports; it does not judge.** A batch gives numbers for its own arms: the measures of
each arm and the difference of each plugin arm from the control of the same batch. It makes no
judgement of improvement or regression, and it does not compare itself with an earlier batch.
This is a rule of the owner of the repository.

**A comparison of two batches** is the work of a maintainer, who reads their two summaries in
`bench/ledger/`. The comparison is fair when only the plugin build differs. These values must be
equal:

| Value | Where to read it |
|---|---|
| The plan: questions, arms, models, runs | the section "Plan" of the summary |
| The question files and the key files | `questions` (SHA-256 values) of `manifest.json` in the batch folder; the summary has a note when a stored score differs from the score with the present key |
| The models | the section "Versions" of the summary |
| The version of Claude Code | the section "Versions" of the summary |
| The product images | the image ids of the section "Versions" of the summary |
| The IDE builds | the section "Versions" of the summary |

When another value differs too, a difference of the numbers has more than one cause. No tool
decides whether two batches are comparable.

A key can change: a key maker that changes the answer of a question changes its key file in a
commit that a maintainer reviews, and the question keeps its name. The recorded SHA-256 values
then show that a later batch used another key. `bench qfiles rescore` scores the stored answers
again with the present keys.

## 7. Limits

- An arm with a sentence in the task (`PF`) does not measure adoption. The arm `P` does.
- The intervals are wide: a plan has few questions of each family, and a cell has few runs.
- The batch has a Go product (caddy) and a Python product (beets). A result for a language comes
  from one product.
- Each run is one closed question in print mode. The batch has no bug correction and no long task.
- A Python key covers only a unique name. A common name has a key only in a planted tree.
- A caller key covers only chains of calls that are certain (section 3.2), or one level of calls
  through an interface value that the tests run (section 3.3). A call through a function value or
  by a computed name has no key.
- The questions and the keys are public. A model can learn them. The keys are in git on purpose,
  so a person outside the project can score an agent. The memory probe and the flag `repo_access`
  are the controls.
- The suites pass an error that the IDE and the tool share (section 2). The audit passes a changed
  field or error text (section 4).

## 8. What a result can claim

- **A suite run that passes:** each row gives its blessed result. Under the bless rule, that
  result is what the IDE showed at the bless. The run claims no correctness beyond the IDE.
- **An audit with the verdict `pass`:** for the trees, the keys and the tools of
  `audit/audits.json`, each difference between a tool answer and the key is on the accepted list,
  with a cause that the owner of the repository permitted. It claims nothing about a symbol with
  no key, and nothing about the fields of a result other than its lines.
- **A batch:** the measures of each arm and the paired differences with their intervals, for the
  questions of its plan, its models and its recorded versions. A difference whose interval holds 0
  shows no difference. A result does not extend to other questions, other products or other
  agents.
- **A gain needs room.** When the control is already exact, a plugin arm cannot show a gain. In
  the batch `calls2` (`bench/ledger/2026-11-20-calls2.md`), arm `C` has the mean exact 1.000 for
  both models.
