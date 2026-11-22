# Key makers

The key makers write the answer keys of the audit and of the agent batch: the answer to a
question about a symbol of a pinned tree, made with no IDE and no plugin. The key sources, their
proofs and the line classes are in [METHOD.md](../METHOD.md), section 3. The data root, its
settings and the order of the setup are in [bench/README.md](../bench/README.md).

The commands run from the root of the repository. `B` is the data root (the variable
`BENCH_ROOT`; this is its default):

```bash
B="${BENCH_ROOT:-$HOME/dev/idesense-bench}"
```

## Files

| Path | Content |
|---|---|
| `gokeys/` | The Go command `gokeys`: Go keys from the Go compiler library (`extract`), their proof (`accept`), the calls file (`calls`), the occurrences of a name (`idents`), a copy of a tree for a run-time trace (`trace`) |
| `pykeys.py` | Python keys: the unique-name scan (`unique`) and the class hierarchy by reflection (`hierarchy`) |
| `callkeys.py` | Caller keys of two levels (`pycalls`, `make`), their trace proof (`targets`, `tracecheck`), and caller keys through an interface value (`dyntargets`, `dynmake`) |
| `plant.py` | Planted trees: one shared name for four methods, and the key from the state before the rename |
| `pytest_plugin/trace_plugin.py` | A pytest plugin that logs the callers of target functions |
| `trees.json` | The recipe and the digest of each benchmark tree |
| `tests/` | The unit tests, and a small Python package for them |

The module text at the top of each Python file gives each option, each file format and each exit
code. The Go command `gokeys` has no such text: `gokeys <command> -h` gives the options of a
command, and the exit code is 0 for success, 1 for a failure and 2 for a usage error. The
formats of its files are in the module texts of `common/keyrecord.py` (the key records of
`extract`) and `callkeys.py` (the calls file, the targets file and the trace file).
The key record format is in the module text of [`common/keyrecord.py`](../common/keyrecord.py).
A key holds positions, names and classes, and no source text of a product.

## Trees

A tree is a copy of a product at its pin: `$B/trees/<tree>/`, with a manifest
`$B/trees/<tree>.manifest` (one line `<sha256>  <path>` for each file) and a git repository with
one commit. The tree of a product has the name of the product. A planted tree has the name
`<product>-plant-<n>`. Each tree has an entry in `trees.json`:

| Field | Content |
|---|---|
| `product` | The product folder in `live-test/real-products/` |
| `manifest_sha256` | The SHA-256 of the manifest of the tree |
| `plant` | Null for the tree of a product. For a planted tree: `lang`, `names` and `shared`, the options `-lang`, `-names` (the list joined with commas) and `-shared` of `plant make` |

Make the tree of a product from its checkout (see "Get a checkout" in
[README.md](../README.md#get-a-checkout)). The command copies the tracked files of the checkout
and prepares the tree for its IDE: the `.idea` files and the dependencies.

```bash
./live-test/run.py common trees make caddy
./live-test/run.py common trees make beets
```

Make a planted tree from its recipe in `trees.json`. The command also writes the key of the plant.
The recipe does not hold these options: `-product`, and for Go `-keys`, the compiler key of the
tree of the product (see "Go keys"), or for Python `-modules beets,beetsplug`. Before a Go plant,
do the first two commands of "Go keys" for the tree caddy.

```bash
./live-test/run.py keygen plant make -lang go -product caddy -keys "$B/keys/caddy/symbols.jsonl" \
  -src "$B/trees/caddy" -dst "$B/trees/<tree>" -names <names> -shared <shared> \
  -out "$B/keys/<tree>/plant.jsonl"
./live-test/run.py keygen plant make -lang python -product beets -modules beets,beetsplug \
  -src "$B/trees/beets" -dst "$B/trees/<tree>" -names <names> -shared <shared> \
  -out "$B/keys/<tree>/plant.jsonl"
```

A Go plant calls the binary `$B/scratch/gokeys-bin` (option `-gokeys`). A Python plant uses the
interpreter `<src>/.venv/bin/python` (option `-python`). Then check each tree against its
tracked digest:

```bash
./live-test/run.py common trees digests        # one line for each tree: ok, different or absent
./live-test/run.py common trees verify <tree>  # each file of the manifest that is absent or changed
```

`digests` prints `ok` when a new tree equals the tree of the recipe. For a new planted tree,
`plant candidates -lang <go|python> -tree <tree> ...` lists the unique-name methods of a tree.
Add the entry of the new tree to `trees.json`, with the SHA-256 of its manifest
(`sha256sum "$B/trees/<tree>.manifest"`).

## The key files

The full key files are in `$B/keys/<tree>/`. They stay outside the repository. A question of the
benchmark holds only the lines of its answer (see
[bench/questions/README.md](../bench/questions/README.md)).

| File | Trees | Command | Proof |
|---|---|---|---|
| `symbols.jsonl` | caddy, its planted trees | `gokeys extract` | `gokeys accept` |
| `unique.jsonl` | beets, its planted trees | `pykeys unique` | By hand: a second scan and a trace (below) |
| `unique-used.jsonl` | beets | `pykeys unique -min-required 1` | As `unique.jsonl` |
| `hierarchy.jsonl` | beets | `pykeys hierarchy` | By hand: two runs give equal files (below) |
| `plant.jsonl` | the planted trees | `plant make` | By hand: Go, `gokeys extract` on the planted tree; Python, a trace of the test suite (below) |
| `calls.jsonl` | each tree | `gokeys calls` (Go), `callkeys pycalls` (Python) | No key |
| `callers.jsonl` | each tree | `callkeys make` | Go: `gokeys calls -check`; Python: `callkeys targets`, a trace, `callkeys tracecheck` |
| `dyncallers.jsonl` | caddy | `callkeys dyntargets`, `gokeys trace`, a test run, `callkeys dynmake` | the rule of `dynmake` |

`callers.jsonl` and `dyncallers.jsonl` hold the keys of the functions that are targets. A
`calls.jsonl` file is no key: it holds the uses of each function declaration, and the caller keys
and the caller audit read it.

A proof "by hand" has no tracked command: a maintainer makes it when the key is made.

- `unique.jsonl`: a second scan of the names with another method, and a run-time trace of the
  test suite, give the lines of the key.
- `hierarchy.jsonl`: run `pykeys hierarchy` two times into two files, and compare the files (for
  example with `cmp`).
- `plant.jsonl` of a Go plant: run `gokeys extract` on the planted tree (see "Go keys"), and
  compare its records of the shared name with the records of `plant.jsonl`.
- `plant.jsonl` of a Python plant: the test suite of the planted tree gives the result of the
  base tree, and the call sites that a run-time trace logs are compared with the key.

`plant make` itself checks only the rename: each occurrence of the shared name is a renamed
position, and no original name is left.

### Go keys

Build the binary, then write the compiler key of a tree:

```bash
(cd live-test/keygen/gokeys && go build -o "$B/scratch/gokeys-bin" .)
"$B/scratch/gokeys-bin" extract -tree "$B/trees/<tree>" -configs linux,windows,darwin \
  -out "$B/keys/<tree>/symbols.jsonl"
"$B/scratch/gokeys-bin" accept -tree "$B/trees/<tree>" -keys "$B/keys/<tree>/symbols.jsonl" \
  -sample <n> -configs linux,windows,darwin -scratch <folder> [-minimal]
```

`-configs` names the build configurations (`GOOS` values; `GOARCH` is amd64). `accept` renames
the sites of each chosen record in a copy of the tree and loads each configuration. It takes
`-ids <id,...|@file>` or `-sample <n> [-seed <s>]`. `gokeys idents -tree <tree> -name <name>`
prints each occurrence of a name. With no command, `gokeys` prints its usage.

A record of a method or an interface method has two families:

- `family` is the structural family: the closure through `types.Implements` over the module types
  and interfaces that have a method with this name.
- `coupled` is the part of `family` that a rename must change with the record. A link joins two
  methods with the same name when the module converts a value of a type to an interface type (an
  assignment, an argument, a return value, a composite literal element, a channel send, a
  comparison, an explicit conversion, a guard `var _ J = (*T)(nil)`), converts a value of one
  interface type to another one, or asserts an interface value to a type (`x.(U)`, a case of a
  type switch). `coupled` is the closure of the record over the links, cut to `family`.

A use of a family member outside `coupled` is `dnc` with `"optional": true`: a rename can change
it, and need not change it. The rename view uses the record as it is. The refs view and the audit
read the record through `structural_view` (`common/keyrecord.py`), where such a use is `required`
again. Limits of `coupled`: an assertion on a value of an empty interface (`any`) gives no link,
and a conversion with a type parameter on one side gives no link. The output of `extract` prints
the counts of the links, of the conversions with a type parameter, and of the records whose
`coupled` is smaller than `family`. The comments of `findLinks`, `linker.pair`, `linker.asserts`
and `viaAssertions` in `gokeys/extract.go` give the rules of a link.

### Python keys

```bash
./live-test/run.py keygen pykeys unique -root "$B/trees/<tree>" -python "$B/trees/<tree>/.venv/bin/python" \
  -modules <packages> -out "$B/keys/<tree>/unique.jsonl" [-min-required <n>]
./live-test/run.py keygen pykeys hierarchy -root "$B/trees/<tree>" -python "$B/trees/<tree>/.venv/bin/python" \
  -packages <packages> -out "$B/keys/<tree>/hierarchy.jsonl"
```

The work with the interpreter of the product runs in a child process of that interpreter; the
harness process needs only the standard library. The first record of a hierarchy key (`_meta`)
lists the modules that failed to import and the classes with no source position.

### Caller keys

```bash
"$B/scratch/gokeys-bin" calls -tree "$B/trees/<tree>" -configs linux,windows,darwin \
  -out "$B/keys/<tree>/calls.jsonl" -check
./live-test/run.py keygen callkeys pycalls -root "$B/trees/<tree>" -unique "$B/keys/<tree>/unique.jsonl" \
  [-plant "$B/keys/<tree>/plant.jsonl"] -out "$B/keys/<tree>/calls.jsonl"
./live-test/run.py keygen callkeys make -calls "$B/keys/<tree>/calls.jsonl" \
  [-symbols "$B/keys/<tree>/symbols.jsonl"] -out "$B/keys/<tree>/callers.jsonl"
```

`-symbols` is required for Go and refused for Python. The proof for Go is `gokeys calls -check`:
its exit code is 1 when a pair of a caller and a function is on one side only. The proof for
Python is a trace of the test suite of the product:

```bash
./live-test/run.py keygen callkeys targets -keys "$B/keys/<tree>/callers.jsonl" -ids <id,...|@file> -out <targets.json>
P="$PWD/live-test/keygen/pytest_plugin"
(cd <tree> && PYTHONPATH="$P" .venv/bin/pytest -p trace_plugin --trace-targets=<targets.json> --trace-out=<trace.jsonl>)
./live-test/run.py keygen callkeys tracecheck -keys "$B/keys/<tree>/callers.jsonl" \
  -calls "$B/keys/<tree>/calls.jsonl" -trace <trace.jsonl> -ids <id,...|@file>
```

Give each option of the pytest plugin and its value as one argument, with `=` (the module text of
`trace_plugin.py` gives the reason). `tracecheck` exits 1 when a traced call comes from a function
of the tree that is no caller in the key, or when a function with callers gets a call from outside
the tree.

### Caller keys through an interface value

`callkeys dynmake` gives a key of one level to a Go method whose only open cause is `interface`.
Its inputs are the static calls, the call sites of the interface methods and a run-time trace.
`R` is a new folder for the files of one run:

```bash
R="$B/scratch/calls/<run>"
mkdir -p "$R/xdg/config" "$R/xdg/data"
./live-test/run.py keygen callkeys dyntargets -calls "$B/keys/caddy/calls.jsonl" \
  -symbols "$B/keys/caddy/symbols.jsonl" -out "$R/targets.json"
"$B/scratch/gokeys-bin" trace -tree "$B/trees/caddy" -targets "$R/targets.json" -dst "$R/copy"
(cd "$R/copy" && go version && XDG_CONFIG_HOME="$R/xdg/config" XDG_DATA_HOME="$R/xdg/data" \
  BENCH_TRACE_OUT="$R/trace.jsonl" go test -count=1 ./...) > "$R/test.log" 2>&1
./live-test/run.py keygen callkeys dynmake -calls "$B/keys/caddy/calls.jsonl" \
  -symbols "$B/keys/caddy/symbols.jsonl" -targets "$R/targets.json" -trace "$R/trace.jsonl" \
  -root "$R/copy" -out "$R/dyncallers.jsonl"
```

`dyntargets` writes the targets file: a JSON list of `{"id", "file", "line"}`, one entry for each
record of kind `method` in `calls.jsonl` whose open causes (`callkeys.open_causes`, with the
symbols file) are exactly `interface`. The id is `<file>:<line>`, with the line of the `decl`. In
the copy of `gokeys trace`, each target logs its call stack, and no line of a file moves. `-depth`
of `gokeys trace` (default 6) is the maximum count of frames in one trace line. `dynmake` looks
for a library caller (`"why": "library"`) only in these frames, so `-depth` changes only these
`dnc` sites and their count in `dynamic`. The stored key used the default.

The test run has these conditions:

- `BENCH_TRACE_OUT` is an absolute path. `go test` runs each test binary in the folder of its
  package, so a relative path gives one trace file in each package folder.
- The trace file does not exist before the run: each test binary appends its lines to it.
- `-count=1` makes Go run each test: a cached test result runs no code and logs no call.
- `XDG_CONFIG_HOME` and `XDG_DATA_HOME` name new empty folders. The tests of caddy keep their
  state (a local CA, certificates, an ACME database, a saved configuration) in
  `$XDG_DATA_HOME/caddy` and `$XDG_CONFIG_HOME/caddy`. The default of these folders is below the
  home folder, and the state stays after the run. An old state changes some lines of the trace
  and can change the result of a test.
- `go test` can exit 1. A failed test of the product does not make the trace wrong: each traced
  call is a real call, and the trace is a lower limit ([METHOD.md](../METHOD.md), section 3.3).
  With a new state, the caddy test `TestReverseProxySNIPlaceHolder` can fail.

The traced calls can also depend on the timing of the tests: the count of CPUs (`GOMAXPROCS`) and
the option `-p` of `go test` can change them. The first line of `test.log` is the Go version.
`dynmake` exits 1 when a traced caller breaks its rule, after it wrote the other records.

The files of the run that made the stored key are in `$B/scratch/calls/`: `caddy-dyn-targets.json`
(the targets file), `caddy-trace/` (the copy), `caddy-trace.jsonl` (the trace) and
`caddy-trace-test.log` (the test output).

**Repeat check.** A second run does not always give a file that is equal byte for byte, so
compare the records. Each record is one line, in the order of `calls.jsonl`, so `diff` shows each
record that differs or that only one file has:

```bash
diff "$B/keys/caddy/dyncallers.jsonl" "$R/dyncallers.jsonl"
```

- No answer changes when only the `proof` of a caller changes between `static` and
  `static+trace`.
- A caller with the class `required` that only one file has changes an answer: it needs a
  decision. A record that only one file has holds such callers.

The new file goes to `$B/keys/caddy/dyncallers.jsonl` only after this decision. Then
`./live-test/run.py bench qfiles check -data` shows each tracked question whose answer differs
from the new file.

## Tests

The Python unit tests of the key makers run with the other unit tests of `live-test/`: see
"Requirements" in [README.md](../README.md#requirements). The Go tests of `gokeys`:

```bash
(cd live-test/keygen/gokeys && go test ./...)
```
