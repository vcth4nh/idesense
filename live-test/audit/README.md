# Audit

The audit calls the tools of the plugin for the symbols of a key file, with no agent, and
compares each answer with its key. A tracked list of accepted disagreements turns the result into
a verdict: `pass`, `fail` or `wait`. The method (the audits, the views, the marks, the verdict rule
and the limits) is in [METHOD.md](../METHOD.md), section 4.

The audit runs on the benchmark IDEs: GoLand on port 29374 for caddy, and PyCharm on port 29372
for beets. Each IDE has the slots of the trees of its product open. The audit needs steps 1 to 5
and step 7 of "Setup from zero" in [bench/README.md](../bench/README.md#setup-from-zero): the
trees, the keys, the slots, and the benchmark IDEs with a plugin build. It needs no image, no
proxy and no secret. The commands run from the root of the repository. `B` is the data root:

```bash
B="${BENCH_ROOT:-$HOME/dev/idesense-bench}"
```

**The lock.** The commands of the audit that call an IDE hold the lock of the benchmark IDEs
(`<data root>/state/lock`) while they run: `verdict run`, `symbols run`, `callers callers` and
`callers dyn`. When another command holds the lock, they print its holder and exit 2. `verdict
check`, `verdict propose` and `symbols disagreements` call no IDE.

## Files

| Path | Content |
|---|---|
| `audits.json` | The audits of a full run: name, tree, kind, key file, calls file and options |
| `accepted/causes.json` | The causes of the accepted disagreements, and the permission of each cause |
| `accepted/<product>.jsonl` | The accepted disagreements of a product. `propose` writes it. A file that does not exist is an empty list. |
| `symbols.py` | The audit of `ide_find_usages`, `ide_find_implementations` and `ide_find_definition` |
| `callers.py` | The caller audit: `ide_call_hierarchy`, and `ide_find_usages` for the kind `dyn` |
| `verdict.py` | The verdict: `run` for all audits, `check` and `propose` for one audit |
| `tests/` | The unit tests |

The module text of each file gives the record formats and the exit codes. The product of an audit
is the product of its tree: the lines of `caddy-plant-1` go to `accepted/caddy.jsonl`.

## Run all audits

```bash
./live-test/run.py audit verdict run -url-goland http://127.0.0.1:29374/mcp/streamable-http \
  -url-pycharm http://127.0.0.1:29372/mcp/streamable-http -out "$B/audit/<build>"
```

`<build>` names the plugin build, for example the seven hex digits of its commit. The command runs
each audit of `audits.json` on the IDE of its product, at the slot path of its tree. It holds the
lock of the benchmark IDEs while the audits run. It refuses an `-out` folder that exists, a port
of a fleet IDE (29170 to 29178; the fleet is the set of the IDEs of the two suites, see
[live-test/README.md](../README.md)), and an input that is absent. Before it makes the `-out` folder, it reads the plugin version
of each IDE: when an IDE that an audit uses gives no version, it stops at once and makes no
folder. Then it prints one verdict line for each audit and one total line:

```
<audit>: <result> | lines <n>, new <n>, gone <n>, not audited <n>, no cause <n>, no permission: <causes>
  new  <disagreement line>
  gone <accepted line>
  not audited <accepted line>
total: <result> | audits <n>: pass <n>, fail <n>, wait <n>
```

A `gone` line is an accepted line of a symbol that the result audited, and the result does not
have the line now. A `not audited` line is an accepted line of a symbol that the result did not
audit, for example a symbol that a sample run did not pick. A `not audited` line gives `wait`,
never `pass`. When the IDE was not ready (dumb mode) for a call of a `symbols` audit, that audit
gets `wait` and one line `<audit>: wait | <result folder>: the IDE was not ready for <n> calls;
run the audit again`.

| Path in `-out` | Content |
|---|---|
| `manifest.json` | The recorded manifest: the pins, the IDEs of the machine, the commit, the plugin version of each IDE, the SHA-256 of each key file and calls file |
| `<audit>/results.jsonl`, `<audit>/summary.md` | The result of a `symbols` audit |
| `<audit>.jsonl` | The result of a `callers` or `dyn` audit |
| `verdict.json` | `{"result": <total>, "audits": [{"name", "verdict": {"result", "new", "gone", "not_audited", "no_cause", "no_permission"}}, ...]}`. The verdict of a `symbols` audit in which the IDE was not ready also has `reason`. |

A stored result does not hold each part of an answer of the IDE. A `dyn` row has no node kinds. A
`callers` row has the counts of the node kinds and the missed and false lines, but not the nodes
themselves: no position, kind or children of a node. A `symbols` result has no column of a row.
When a decision needs such a part, call the tool again.

| Exit code | Meaning |
|---|---|
| 0 | `pass` |
| 1 | `fail` |
| 3 | `wait` |
| 2 | No audit ran or no verdict: another holder has the lock, `-out` exists, an input is absent, an IDE that an audit uses gives no plugin version, or a result, the accepted list or the causes file cannot be read |
| 4 | An audit stopped before its end: the IDE stayed in dumb mode at the start, or the server version changed. No verdict. |

## One audit

`check` prints the verdict of one result, and `propose` writes the found lines of one result into
the accepted list. `-name` is a name of `audits.json`. The input is the result of the same kind:

```bash
./live-test/run.py audit verdict check -name <audit> -symbols "$B/audit/<build>/<audit>" -keys "$B/keys/<key file>"
./live-test/run.py audit verdict check -name <audit> -callers "$B/audit/<build>/<audit>.jsonl"
./live-test/run.py audit verdict check -name <audit> -dyn "$B/audit/<build>/<audit>.jsonl"
./live-test/run.py audit verdict propose -name <audit> -symbols "$B/audit/<build>/<audit>" -keys "$B/keys/<key file>"
```

`check` exits as `run` does (0, 1, 3, or 2 for a bad input). `propose` keeps the lines of the other
audits, and the lines of each symbol that the result did not audit, with their causes. A line that
stays keeps its cause, a new line gets the cause null, and a line of an audited symbol that the
result no longer has goes out. Both refuse (exit 2, one line) a result with no record, a result
whose server version changed during the run, a `symbols` result in which the IDE was not ready for
a call, and an input of another form, for example a `dyn` file as `-callers`.

The audits can also run one at a time, with no verdict. `symbols run`, `callers callers` and
`callers dyn` hold the lock, print the warnings of the manifest, and write a recorded manifest
next to their result. An absent key file, calls file or `-ids` file, and a fleet port, give one
line and exit 2. `-project` is the slot path of the tree (`$B/trees/slots.json`).

```bash
./live-test/run.py audit symbols run -keys <key file> -url <mcp url> -project <slot path> -n 200 -seed 1 -repeats 3 -out <folder>
./live-test/run.py audit symbols disagreements -results <folder> -keys <key file>
./live-test/run.py audit callers callers -url <mcp url> -project <slot path> -keys <callers.jsonl> -calls <calls.jsonl> -out <file.jsonl> -n 40 -seed 1
./live-test/run.py audit callers dyn -url <mcp url> -project <slot path> -keys <dyncallers.jsonl> -calls <calls.jsonl> -out <file.jsonl>
```

`symbols run` takes a seeded sample of `-n` records and asks each tool `-repeats` times.
`disagreements` writes `disagreements.jsonl` and `disagreements.md` into the result folder.
`callers callers` takes `-ids <file>` (one key id for each line) or a seeded sample of `-n`
records. `callers dyn` takes `-ids <file>`, or each record with a caller that the run-time trace
proves.

## File formats

**A disagreement line** is one symbol and one tool for which the answer of the IDE differs from the
key. Each list is sorted and always present:

```json
{"audit": "caddy-symbols", "tool": "ide_find_usages", "symbol": "<key id>", "miss": [["f.go", 3]], "fp": [], "marked": [], "errors": []}
```

| Field | Content |
|---|---|
| `miss` | The required lines that the answer does not have, as `[file, line]` |
| `fp` | The false lines of the answer |
| `marked` | The marked false lines of a usages answer (a row with `match`); empty for a caller audit |
| `errors` | The texts of the tool errors |

**An accepted line** is a disagreement line with one more field, `cause`: the name of an entry of
`causes.json`, or null. The lines are sorted by `audit`, `tool` and `symbol`. The verdict compares
the whole line without `cause`.

**A cause** in `causes.json`:

```
{"<name>": {"text": "<text>", "issue": <number or null>, "permitted": "<YYYY-MM-DD>" or null}}
```

Each cause has the three fields. `text` has one or more characters. `issue` is the number of an
open issue, or null. `permitted` is the date on which the owner of the repository permitted the
cause, or null. Another value makes `check` and `run` stop with exit 2. An accepted line with no
`audit`, `tool` or `symbol`, or with a `cause` that is no name and not null, makes `check`,
`propose` and `run` stop with exit 2.

## Accept a disagreement

A new cause needs the permission of the owner of the repository, as a bless of a deviation from
the IDE does. While a cause has no date in `permitted`, an audit with a line of that cause ends in
`wait` (or in `fail`, when it also has a new line). The first accepted list of a product comes
from a run on a present build.

No cause of `causes.json` has a permission yet, so `wait` is the expected verdict of a build with
no regression. An audit with no accepted line gives `fail` when it finds a disagreement, because
each found line is new. Write the first list of the audit with the steps below before you read
a `fail` as a regression. A result that did not audit each symbol of the list, for example a
single `symbols run` with a small `-n`, gives `not audited` lines and `wait`. `propose` keeps a
`not audited` line with its cause. When an audit no longer asks about a symbol (after a change
of `n`, `seed` or `ids` in `audits.json`, or after a new key file), remove the lines of that
symbol from the list by hand.

1. Run all audits (see "Run all audits"). Read each `new` line.
2. Decide for each new line: a defect of the plugin (write an issue), or a behaviour that the IDE
   also shows (find the evidence: the rule "Mimic the IDE" in the root
   [AGENTS.md](../../AGENTS.md)).
3. Run `propose` for the audit. It writes each found line into `accepted/<product>.jsonl`, and
   each new line has the cause null. Remove from the list each line that you do not accept, for
   example a defect with no issue. That line stays new, and the audit fails.
4. Give each new line the name of its cause (see "Name the cause of a line"). For a new cause,
   add an entry to `causes.json` with its text, its issue and `"permitted": null`.
5. Ask the owner of the repository to permit each new cause. The owner writes the date into
   `permitted`.
6. Run `check` for the audit. With each cause permitted, the result is `pass`. Commit the
   accepted list and `causes.json`.

### Name the cause of a line

The sites of a line are the lines of `miss` and of `fp`, and the sites of the texts of `errors`.
A line gets the name of a cause only when each of its sites meets each item of the evidence of
that cause. The evidence comes from the key files of the tree (`$B/keys/<tree>/`), the source of
the tree and the stored result of the audit (see "Run all audits" for what a result does not
hold). A line whose sites have different mechanisms keeps the cause null, also when a cause
explains some of its sites. A line with no such evidence keeps the cause null too.

The evidence of each cause of `causes.json`:

- `interface-calls-option-off`: a `dyn` line of `ide_call_hierarchy`. Each missed caller has a
  site with the `proof` `trace` in `dyncallers.jsonl` (`hierarchy.miss_proof` of the row counts
  only `trace`). In `calls.jsonl`, the missed caller holds no use of the method (no `in` of a use
  is its `decl`). In `symbols.jsonl`, the record of the method has a site with `rel` `super` and
  `why` `use` in the missed caller. The row has no `hierarchy_error`, `hierarchy.fp_sites` is
  empty, and no missed caller is in `usages.miss_sites`: Find Usages lists it.
- `closure-node`: a `callers` line of a Go function. Each missed line is a caller of level 2
  (`mapped.miss_sites` of the row is `[file, line, level, lit, configs]`). It calls a function of
  level 1 whose site in `callers.jsonl` has `lit` true: that function calls the target only inside
  a function literal.
  The row has `CLOSURE` in `kinds`, and `raw.fp_sites` has one line for each `CLOSURE` node, at
  the first line of a function literal in the source. `mapped.fp_sites` is empty.
- `other-build-configuration`: a `symbols` line of `ide_find_usages` on a Go declaration. The site
  with `why` `decl` in `symbols.jsonl` has `configs` without `linux` (the benchmark IDEs run on
  Linux), and the file has a build constraint or a file name that excludes Linux. The answer is
  empty: in `results.jsonl`, `extra.rows` is 0, `extra.notes` is absent and `error` is null. A
  result with rows does not fit.
- `other-build-configuration-use`: a `symbols` line of `ide_find_definition`. Each missed line is
  a use in such a file (its site in `symbols.jsonl` has `configs` without `linux`), and its text
  in `errors` ends with `Could not resolve symbol definition`. The line has no other error and no
  `fp` line.
- `python-property-callers`: a `callers` line of a Python method. The record in `callers.jsonl`
  has `property` true, and the source has the decorator `property` or `cached_property`. Each use
  of the method in `calls.jsonl` has `read` true. The row has no `error`, and its `kinds` is empty:
  the tree has no node. The `ide_find_usages` result of the same id in a `symbols` audit is exact
  (`score.exact` in `results.jsonl`).
- `receiver-type-does-not-declare`: a line of `ide_find_usages` or `ide_call_hierarchy` on a
  Python method. The use behind each missed line is an attribute reference `<receiver>.<name>`.
  The source gives the receiver a type (an annotation, a constructor call, a return annotation, a
  class attribute or a `Mock`), and that class and its bases do not declare the name. The answer
  has no note and no warning: no `extra.notes` and no `extra.warnings` in `results.jsonl`, or
  null `notes` and `warnings` in a `callers` row. When a `symbols` audit also asked
  `ide_find_definition` at the use, its answer is an error: a use that resolves does not fit. A
  receiver of the type `Any`, a receiver with no type in the source and a class that declares the
  name do not fit.

## After a change of a usage, implementation or caller tool

1. Commit the change. Build the plugin and start the benchmark IDEs with it:
   `./live-test/run.py bench build -start` (see "The plugin build under test" in
   [bench/README.md](../bench/README.md#the-plugin-build-under-test)).
2. Run all audits into a new folder `"$B/audit/<build>"`.
3. Read the verdict. A `fail` shows a new or a changed disagreement: a regression, or a correction
   that the accepted list does not know yet. A `gone` line shows a disagreement that the change
   removed: `propose` takes it out of the list. Run `propose` only after you make a decision for
   each new line of that audit (see "Accept a disagreement").
4. For a new line that the change makes correct, follow "Accept a disagreement".

## Tests

The unit tests of the audit run with the other unit tests of `live-test/`: see "Requirements" in
[README.md](../README.md#requirements).
