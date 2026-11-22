# Batch `calls2-memory`

The summary of the benchmark batch `calls2-memory`. The command `python3 -m bench.triage ledger -batch calls2-memory` (run from `live-test`) wrote it from the run folders of the batch. The run folders stay in the data root, outside the repository. The tables are the tables of `summary.md` of `python3 -m bench.triage report`. The module text of `bench/triage.py` defines each table, column and flag. The first run of the batch started on 2026-11-20 (UTC).

## Plan

The batch has no stored plan (`plan.json`).

## Versions

The batch has no recorded manifest (`manifest.json`). The values of the run records:

| item | value |
|---|---|
| plugin version (caddy) | 2.1.1-bench.f4ff0a2 |
| models | claude-haiku-5-5, claude-opus-5-5 |
| image (caddy) | sha256:140ad023887c00ac1b0c3ae3a42eff97cbf800af18c9093f16c0d442896bf438 |

## Batch

| outcome | runs |
|---|---|
| no_answer | 1 |
| ok | 19 |
| runs | 20 |
| set aside | 0 |
| unfinished | 0 |
| total cost (USD) | 0.3079 |

## By question, model and arm

| question | model | arm | runs | outcomes | f1 | precision | recall | exact | USD | seconds | turns | tool calls | IDE calls | tokens | adoption | excluded |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `caddy-dyncallers-app.cleanup` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0006 | 5.1 | 2.0 | 0.0 | 0.0 | 4281 | - | 0 |
| `caddy-dyncallers-app.cleanup` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0465 | 19.4 | 2.0 | 0.0 | 0.0 | 4913 | - | 0 |
| `caddy-dyncallers-app.emit` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0006 | 5.0 | 2.0 | 0.0 | 0.0 | 4286 | - | 0 |
| `caddy-dyncallers-app.emit` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0288 | 17.1 | 2.0 | 0.0 | 0.0 | 4640 | - | 0 |
| `caddy-dyncallers-baserespwriter.written` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 4.9 | 2.0 | 0.0 | 0.0 | 4313 | - | 0 |
| `caddy-dyncallers-baserespwriter.written` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.500 | 0.500 | 0.500 | 0.000 | 0.0654 | 28.0 | 2.0 | 0.0 | 0.0 | 6480 | - | 0 |
| `caddy-dyncallers-firstselection.select` | claude-haiku-5-5 | C-no-tools | 1 | no_answer 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0010 | 11.5 | 3.0 | 1.0 | 0.0 | 15269 | - | 0 |
| `caddy-dyncallers-firstselection.select` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0209 | 12.3 | 2.0 | 0.0 | 0.0 | 4258 | - | 0 |
| `caddy-dyncallers-matchquery.cellibrary` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 5.5 | 2.0 | 0.0 | 0.0 | 4292 | - | 0 |
| `caddy-dyncallers-matchquery.cellibrary` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0218 | 13.5 | 2.0 | 0.0 | 0.0 | 4303 | - | 0 |
| `caddy-dyncallers-mockrouter.routes` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0006 | 8.4 | 4.0 | 2.0 | 0.0 | 9580 | - | 0 |
| `caddy-dyncallers-mockrouter.routes` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0260 | 14.8 | 2.0 | 0.0 | 0.0 | 4499 | - | 0 |
| `caddy-dyncallers-responserecorder.writeresponse` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 5.2 | 2.0 | 0.0 | 0.0 | 4292 | - | 0 |
| `caddy-dyncallers-responserecorder.writeresponse` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0259 | 14.5 | 2.0 | 0.0 | 0.0 | 4511 | - | 0 |
| `caddy-dyncallers-staticiprange.getipranges` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 5.2 | 2.0 | 0.0 | 0.0 | 4294 | - | 0 |
| `caddy-dyncallers-staticiprange.getipranges` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0246 | 13.5 | 2.0 | 0.0 | 0.0 | 4445 | - | 0 |
| `caddy-dyncallers-stdoutwriter.openwriter` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 5.2 | 2.0 | 0.0 | 0.0 | 4278 | - | 0 |
| `caddy-dyncallers-stdoutwriter.openwriter` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0246 | 13.7 | 2.0 | 0.0 | 0.0 | 4435 | - | 0 |
| `caddy-dyncallers-testclientcertificateverifier.verifyclientcertificate` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0007 | 8.5 | 5.0 | 3.0 | 0.0 | 14653 | - | 0 |
| `caddy-dyncallers-testclientcertificateverifier.verifyclientcertificate` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0189 | 11.3 | 2.0 | 0.0 | 0.0 | 4173 | - | 0 |

## Paired differences

Arm - base, for each question of a model, an arm and a base. The base is C for each plugin arm, and also PF for PFN, PFR, PFL, PFG, PFI and PFS. The line `all`: the means over the questions; each difference with its bootstrap mean and 95 % interval over the questions.

| model | arm | base | question | f1 arm | f1 base | f1 diff | exact arm | exact base | exact diff | USD arm | USD base | USD diff | seconds arm | seconds base | seconds diff | tool calls arm | tool calls base | tool calls diff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Adoption

| arm | model | runs | IDE tool in first_tools | share |
|---|---|---|---|---|

## Flags

| flag | runs | ids (at most 10) |
|---|---|---|
| no_plugin_call | 0 | - |
| ide_calls | 0 | - |
| ide_tools | 0 | - |
| ide_error | 0 | - |
| anchor_error | 0 | - |
| ide_error_texts | 0 | - |
| has_more_no_cursor | 0 | - |
| ide_forbidden_lines | 0 | - |
| answer_repeats_ide_forbidden | 0 | - |
| ide_missed_required | 0 | - |
| answer_miss_not_in_ide | 0 | - |
| text_after_ide | 0 | - |
| edit_then_ide_no_sync | 0 | - |
| repo_access | 0 | - |
| plugin_wrong_control_right | 0 | - |

## Total cost

| part | count | USD |
|---|---|---|
| runs of the batch | 20 | 0.3079 |
