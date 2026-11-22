# Questions of the agent benchmark

This folder holds the questions of the agent benchmark of IdeSense. A question asks a coding agent
for a closed list of source lines about one symbol of an open source product at a pinned release:
for example each implementer of an interface, or each caller of a function. Each question has a
key with the correct answer. You can score any agent on these questions with Python 3.10 or later
and git: you need no IDE, no container and no data of the maintainers.

## Files

| Path (below `live-test/bench/`) | Content |
|---|---|
| `questions/<name>.md` | The text of the task that the agent gets |
| `keys/<name>.json` | The key of the question: the product, its pin, and the answer lines by class |
| `score.py` | The score of one answer against one key |

A name is in lowercase. It holds the product (or the planted tree), the family and the symbol, for
example `caddy-impls-validator`. `<name>.md` and `<name>.json` belong together.

## A question

A question file holds the complete text of the task. `{root}` stands for the absolute path of the
checkout of the product. The last paragraph of the text gives the answer format. Each path of an
answer is relative to the root of the checkout, and each line number starts at 1.

## A key

| Field | Content |
|---|---|
| `question` | The name of the question |
| `old_ids` | The earlier ids of the question in the benchmark |
| `product` | The product |
| `pin` | The release tag of the product |
| `tree` | The tree of the question: the product name, or `<product>-plant-<n>` for a planted tree (see "Planted trees") |
| `family` | `refs`, `impls`, `rename`, `callers` or `dyncallers` |
| `lang` | `go` or `python` |
| `symbol` | The id of the symbol in the full key of the maintainers |
| `name` | The name of the symbol in the question |
| `answer` | Three lists of `<path>:<line>`: `required`, `forbidden` and `not_counted` |
| `pick` | `sample` (`hard`, `random` or `control`) and `rule`: how the question was chosen |
| `key_file`, `source` | The full key file in the data root of the maintainers, and how it was made |

The classes of `answer`:

- `required`: an exact answer has each of these lines.
- `forbidden`: an exact answer has none of these lines, for example a line with the same name that
  is another symbol.
- `not_counted`: the answer can have these lines or not. They do not change the score.

Each other line of an answer is a false line, as a `forbidden` line is. A key holds positions,
names and classes, and no source text of the product.

## Score an agent

1. **Check out the product at the pin.** The repository of each product is the field `repo` (a
   GitHub `<owner>/<name>`) of its entry in `live-test/real-products/products.json`.

   ```bash
   git clone --depth 1 --branch <pin> https://github.com/<repo> <checkout>
   ```

   The benchmark gives the agent a copy with no agent instruction file of the product:
   `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules` and `.github/copilot-instructions.md`,
   and the folders `.claude` and `.cursor`. Remove them from the checkout for a run that is
   comparable with the benchmark.
2. **Give the agent the question.** Replace `{root}` with the absolute path of the checkout, and
   give the text to the agent as its task, in the checkout:

   ```bash
   sed "s|{root}|$(cd <checkout> && pwd)|g" live-test/bench/questions/<name>.md
   ```

   The control arm of the benchmark gives this text and nothing more, and it gives Claude Code the
   JSON schema of the answer (option `--json-schema`). The keys are public, so an agent that can
   read this repository or the web can find the answer: read the transcript of a run for an
   access to `bench/keys`.
3. **Score the answer.** Write the answer of the agent into a file, for example `answer.json`,
   and run:

   ```bash
   python3 live-test/bench/score.py live-test/bench/keys/<name>.json answer.json --root <checkout>
   ```

## The answer format

The answer is the JSON object `{"sites": ["<path>:<line>", ...]}`.

- An entry is `path:line` or `path:line:column`. The script drops the column.
- A path is relative to the root of the checkout, or absolute below the path of `--root`. A
  leading `./` goes.
- An entry is invalid when it has no line, a line range, a line below 1, a path outside the root,
  or when it is not a string. With no `--root`, each absolute path is invalid.
- Each line counts one time: two entries on one line are one answer line.
- With `--root`, an answer line whose path is no file of the checkout (`git ls-files`) is not
  scored. It counts in `outside`.

## The output

The first line is

```
exact=<True|False> tp=<n> fp=<n> miss=<n> ignored=<n> outside=<n> invalid=<n>
```

Then the script prints one line `missed <path>:<line>` for each required line that the answer does
not have, and one line `false <path>:<line>` for each false line.

| Field | Meaning |
|---|---|
| `exact` | `True` when `miss` and `fp` are 0 |
| `tp` | The answer lines that are `required` |
| `fp` | The false answer lines: `forbidden`, or not in the key |
| `miss` | The `required` lines that the answer does not have |
| `ignored` | The answer lines that are `not_counted` |
| `outside` | The answer lines whose path is no file of the checkout |
| `invalid` | The entries that cannot be read |

The benchmark computes precision as `tp / (tp + fp)` and recall as `tp / (tp + miss)`. The exit
code is 0 for an exact answer, 1 for an answer that is not exact, and 2 for an error (for example
a file that cannot be read, or an answer with no list `sites`).

## Planted trees

A question whose `tree` is `<product>-plant-<n>` is about a planted tree: a copy of the product at
the pin in which four methods with unique names got one shared name. The `name` of the key is the
shared name. A checkout at the pin does not have this name, so an agent cannot answer the question
in it. The recipe of each planted tree (the four names and the shared name) is in
`live-test/keygen/trees.json`. To make a planted tree you need the harness of this repository and
more than Python: see "Trees" in [keygen/README.md](../../keygen/README.md#trees). The files of a
planted tree have the paths and the line numbers of the checkout at the pin.

## More

How the questions were chosen, what each family asks and how the benchmark scores a batch:
[METHOD.md](../../METHOD.md), section 5. The batches of the maintainers and their results:
`live-test/bench/ledger/`.
