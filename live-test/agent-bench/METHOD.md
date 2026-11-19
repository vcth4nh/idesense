# Method of the agent benchmark

This file gives the rules of the benchmark: what it measures, where each answer key comes from, how
a run is made, and how an answer gets its score. `README.md` has the commands and the file formats.
A report of a batch gives the numbers. It also names the commits of the products, the build of the
plugin, the version of the agent and the models.

## 1. The question

Does a coding agent give a more correct answer about code when it has the IDE tools of the plugin?

The benchmark runs the same agent on the same question with the tools and without them. It scores
each answer against a key that no IDE made.

## 2. Material

- **Products.** Real open source products at pinned commits. The first two are caddy (Go, GoLand)
  and beets (Python, PyCharm). A product tree has a manifest of its files, and each tool reads a
  copy of it.
- **Plugin.** One build of the plugin for all runs of a batch. The benchmark IDEs are separate from
  each other IDE of the machine.
- **Agent.** Claude Code in print mode, with a fixed effort, in a container. A batch uses a strong
  model and a small model.

## 3. Answer keys

Rule: a key never comes from the plugin or from an IDE. Each key source has a proof, and the proof
uses a second method.

| Key | Source | Proof |
|---|---|---|
| Go symbols: uses, families, implementers | The name resolution of the Go compiler library (`go/types`), one load for each build configuration (Linux, Windows, macOS), test code included | `gokeys accept` renames each key line in a copy of the tree, and each configuration must type-check. With one line removed, the check must fail. |
| Python uses | A token scan, only for a function or a method whose name has one definition and no other meaning in the tree (the unique-name rules of `benchlib/pykeys.py`) | A second scan with a different method, and a run-time trace of the test suite, give the same lines. |
| Python subclasses | Reflection in the interpreter of the product | Two runs give equal files, and each position is at a class name. |
| Planted trees | A copy of a tree where 4 methods with unique names, on 4 unrelated types, get one shared name. The key is the state before the rename. | Go: the key equals the compiler key of the planted tree. Python: the test suite gives the result of the base tree, and the call sites that a run-time trace logs are compared with the key. |
| Go callers | `gokeys calls`: each use of a function declaration, with the declaration that holds it and whether it is a call | `gokeys calls -check`: the static calls of the SSA form of the program (`go/ssa`) must give the same pairs of caller and callee in each configuration. |
| Python callers | `callkeys pycalls`: the uses of the unique-name keys, with the outermost `def` that holds each use (from the syntax tree) | `callkeys tracecheck`: each call site that a trace of the test suite logs for the target and for its direct callers must be in a function of the key. |

A planted tree exists because a Python method with a common name has no key that a scan can prove.
The plant makes a common name whose key is known. In such a tree a text search finds the uses of
all four methods, and only the key knows which use belongs to which method.

### 3.1 Line classes

Each line of a key has one class:

- `required`: an exact answer has the line.
- `forbidden`: an exact answer does not have the line (for example a line with the same name that
  is a different symbol).
- `dnc` (not decided): the line is not counted. Examples: the declaration of the symbol itself, a
  comment, a use that a rename can change and need not change.

An answer line that the key does not hold is a false line.

### 3.2 Caller keys are exact keys

A caller key holds the functions that call the target (level 1) and the functions that call these
callers (level 2). A target gets a key only when each call in the chain is certain:

- each use of the target, and of each level-1 caller, is a call inside a function;
- none of these functions is used as a value, implements an interface method (Go), or has another
  of the open causes that `README.md` lists.

So a caller key has no chain through an interface value, a function value or a call by a computed
name. Such a chain needs a key from a run-time trace. That key source is not a part of the
benchmark yet.

A call inside a function literal, a lambda or a nested function counts for the outermost function
declaration that holds it. The text of the question says so.

## 4. Questions

Each question is a closed list question about one symbol. The agent answers with a JSON list of
`path:line` entries.

| Family | The answer lines |
|---|---|
| `refs` | Each line that calls or names the symbol |
| `impls` | The declaration line of each type that implements the interface, or of each subclass |
| `rename` | Each line that a rename of the method must change |
| `callers` | The declaration line of each function that calls the function, and of each function that calls one of these callers |

A program chooses the questions of a set by fixed rules and a seed (`pilot_set`, `main_set` and
`calls_set` in `benchlib/challenges.py`). A set has random picks and hard picks. Each hard pick has
a class, and its rule is written before the first run. Examples of classes: types that get a
method from an embedded type, many lines with the same name, lines in a file that the build of the
machine does not compile, a planted name, a long list, a call inside a function literal, a
property.

## 5. One run

- **Isolation.** One container, one question, one new agent. The container has no mount, no host
  network mode and no Docker socket. The key files never go into an image or a container.
- **Tools.** The agent has each normal tool of Claude Code: the shell, the file tools and the
  search tools. No arm takes a tool away. Only the memory probe (section 8) runs with no tools.
- **Tree.** The tree is at a neutral path. The path has no word that tells the agent of a
  benchmark. The IDE has the same tree open at the same path.
- **Proxy.** The container reaches the IDE only through a filter proxy. The proxy passes the
  read-only tools of the plugin and no tool that changes a file or the IDE.
- **Test arms.** The proxy can add a text to a tool result or to the server instructions. So the
  effect of a possible plugin change gets a test before the plugin changes.
- **Limits.** A wall-clock limit and a cost limit for each run.
- **Record.** Each run keeps its transcript, the log of its IDE calls, its cost and its score.

## 6. Arms

| Arm | Content |
|---|---|
| `C` | No IDE server (the control) |
| `P` | The IDE server of the plugin, with no hint |
| `PS` | `P`, plus an aid that the plugin can install (a skill or a rule file) |
| `PF` | `P`, plus one sentence in the task that tells the agent to use the IDE tools |
| Test arms | `PF`, plus one change: a text in a tool result, more rows in a result, one more sentence in the task, or a text as server instructions (see `README.md`) |

`PF` against `C` measures the value of the tools when the agent uses them. `P` against `C` measures
the plugin as a user gets it, and that result depends on whether the agent calls the tools at all.

## 7. Score and statistics

- **Exact.** An answer is exact when it has each required line and no forbidden line and no false
  line. Lines of the class `dnc` are not counted.
- **Other measures.** Precision, recall and F1 over the lines, the cost, the time and the tool
  calls of the run.
- **Unit.** The unit is the question. Each question has some runs for each model and each arm
  (3 in the batches so far). The value of a question is the mean of its runs.
- **Comparison.** The paired difference of two arms for each question, with a 95 % bootstrap
  interval over the questions.

## 8. Controls

- **Memory probe.** Each question runs with no tools. A question for which a model gives more than
  half of the required lines from memory is replaced.
- **Audit.** The tools of the plugin run against the keys with no agent. The audit shows what the
  IDE returns before an agent reads it, and each difference gets a cause.
- **Canary.** One run goes first in each batch, and its transcript is read.
- **Plugin version.** The runner reads the version of the plugin at the start and at the end of
  each run.
- **Secret scan.** The runner searches each output file of a run for the API key.
- **Invalid runs.** A run with an API error or a harness error is set aside and counted. It is in
  no mean.

## 9. Limits

- An arm with a sentence in the task (`PF`) does not measure adoption. The arm `P` does.
- The intervals are wide: a set has 20 to 30 questions, and a cell has few runs.
- The products and the languages are few. A result for Go comes from one product, and a result
  for Python from one product.
- Each run is one closed question in print mode. The benchmark has no bug correction and no long
  task.
- A Python key covers only a unique name. A common name has a key only in a planted tree.
- A caller key covers only chains of calls that are certain (section 3.2).
