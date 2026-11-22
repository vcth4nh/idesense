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
| `callkeys.py` | Caller keys of two levels (`pycalls`, `make`), their trace proof (`targets`, `tracecheck`), and caller keys through an interface value (`dynmake`) |
| `plant.py` | Planted trees: one shared name for four methods, and the key from the state before the rename |
| `pytest_plugin/trace_plugin.py` | A pytest plugin that logs the callers of target functions |
| `trees.json` | The recipe and the digest of each benchmark tree |
| `tests/` | The unit tests, and a small Python package for them |

The module text at the top of each file gives each option, each file format and each exit code.
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
tree of the product (see "Go keys"), or for Python `-modules beets,beetsplug`.

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
| `unique.jsonl` | beets, its planted trees | `pykeys unique` | A second scan and a trace ([METHOD.md](../METHOD.md), section 3) |
| `unique-used.jsonl` | beets | `pykeys unique -min-required 1` | As `unique.jsonl` |
| `hierarchy.jsonl` | beets | `pykeys hierarchy` | Two runs give equal files |
| `plant.jsonl` | the planted trees | `plant make` | Go: `gokeys extract` on the planted tree; Python: a trace of the test suite |
| `calls.jsonl` | each tree | `gokeys calls` (Go), `callkeys pycalls` (Python) | No key |
| `callers.jsonl` | each tree | `callkeys make` | Go: `gokeys calls -check`; Python: `callkeys targets`, a trace, `callkeys tracecheck` |
| `dyncallers.jsonl` | caddy | `gokeys trace`, a test run, `callkeys dynmake` | the rule of `dynmake` |

`callers.jsonl` and `dyncallers.jsonl` hold the keys of the functions that are targets. A
`calls.jsonl` file is no key: it holds the uses of each function declaration, and the caller keys
and the caller audit read it.

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
Its inputs are the static calls, the call sites of the interface methods and a run-time trace:

```bash
"$B/scratch/gokeys-bin" trace -tree "$B/trees/caddy" -targets <targets.json> -dst <copy>
(cd <copy> && BENCH_TRACE_OUT=<trace.jsonl> go test -count=1 ./...)
./live-test/run.py keygen callkeys dynmake -calls "$B/keys/caddy/calls.jsonl" \
  -symbols "$B/keys/caddy/symbols.jsonl" -targets <targets.json> -trace <trace.jsonl> \
  -root <copy> -out "$B/keys/caddy/dyncallers.jsonl"
```

The targets file is a JSON list of `{"id", "file", "line"}`, with the line of the `decl` of a
record of `calls.jsonl`. No command of the harness writes it: it lists the methods whose open
causes (`callkeys.open_causes`) are exactly `interface`. In the copy of `gokeys trace`, each target
logs its call stack, and no line of a file moves. `-count=1` makes Go run each test: a cached test
result runs no code and logs no call. `dynmake` exits 1 when a traced caller breaks its rule, after
it wrote the other records.

## Tests

```bash
python3 -B -m unittest discover -s live-test -t live-test -p "test_*_unit.py"
(cd live-test/keygen/gokeys && go test ./...)
```

The first command runs the unit tests of each package of `live-test/`.
