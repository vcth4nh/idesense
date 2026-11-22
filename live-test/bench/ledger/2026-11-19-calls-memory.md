# Batch `calls-memory`

The summary of the benchmark batch `calls-memory`. The command `python3 -m bench.triage ledger -batch calls-memory` (run from `live-test`) wrote it from the run folders of the batch. The run folders stay in the data root, outside the repository. The tables are the tables of `summary.md` of `python3 -m bench.triage report`. The module text of `bench/triage.py` defines each table, column and flag. The first run of the batch started on 2026-11-19 (UTC).

## Plan

The batch has no stored plan (`plan.json`).

## Versions

The batch has no recorded manifest (`manifest.json`). The values of the run records:

| item | value |
|---|---|
| plugin version (beets) | 2.1.1-bench.f4ff0a2 |
| plugin version (caddy) | 2.1.1-bench.f4ff0a2 |
| models | claude-haiku-5-5, claude-opus-5-5 |
| image (beets) | sha256:17516d77757800d2db5436bce0ce1f1c49e07162dbf6ec79ae42707f59945b02 |
| image (caddy) | sha256:140ad023887c00ac1b0c3ae3a42eff97cbf800af18c9093f16c0d442896bf438 |

## Batch

| outcome | runs |
|---|---|
| no_answer | 2 |
| ok | 38 |
| runs | 40 |
| set aside | 0 |
| unfinished | 0 |
| total cost (USD) | 0.6136 |

## By question, model and arm

| question | model | arm | runs | outcomes | f1 | precision | recall | exact | USD | seconds | turns | tool calls | IDE calls | tokens | adoption | excluded |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `beets-callers-_is_same_path_or_child` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0006 | 10.2 | 4.0 | 2.0 | 0.0 | 13941 | - | 0 |
| `beets-callers-_is_same_path_or_child` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0133 | 11.4 | 2.0 | 0.0 | 0.0 | 3839 | - | 0 |
| `beets-callers-baseserver._notification_done` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0010 | 11.0 | 4.0 | 2.0 | 0.0 | 13914 | - | 0 |
| `beets-callers-baseserver._notification_done` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0441 | 20.2 | 2.0 | 0.0 | 0.0 | 4762 | - | 0 |
| `beets-callers-changerepresentation.print_layout` | claude-haiku-5-5 | C-no-tools | 1 | no_answer 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0016 | 15.8 | 5.0 | 3.0 | 0.0 | 21393 | - | 0 |
| `beets-callers-changerepresentation.print_layout` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0338 | 20.9 | 2.0 | 0.0 | 0.0 | 4866 | - | 0 |
| `beets-callers-importaddedplugin.write_file_mtime` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0006 | 10.5 | 4.0 | 2.0 | 0.0 | 9585 | - | 0 |
| `beets-callers-importaddedplugin.write_file_mtime` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.250 | 0.250 | 0.250 | 0.000 | 0.0385 | 20.7 | 2.0 | 0.0 | 0.0 | 5102 | - | 0 |
| `beets-callers-match.disambig_string` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 7.1 | 2.0 | 0.0 | 0.0 | 4206 | - | 0 |
| `beets-callers-match.disambig_string` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0155 | 12.7 | 2.0 | 0.0 | 0.0 | 3945 | - | 0 |
| `beets-callers-mpcclient.serialise_command` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 6.9 | 2.0 | 0.0 | 0.0 | 4226 | - | 0 |
| `beets-callers-mpcclient.serialise_command` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0221 | 15.2 | 2.0 | 0.0 | 0.0 | 4278 | - | 0 |
| `beets-callers-mpdstats.update_rating` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0006 | 10.6 | 4.0 | 2.0 | 0.0 | 9515 | - | 0 |
| `beets-callers-mpdstats.update_rating` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0549 | 28.1 | 2.0 | 0.0 | 0.0 | 5916 | - | 0 |
| `beets-plant1-callers-discogsplugin.select_cover_art` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0004 | 6.8 | 2.0 | 0.0 | 0.0 | 4226 | - | 0 |
| `beets-plant1-callers-discogsplugin.select_cover_art` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0253 | 13.4 | 2.0 | 0.0 | 0.0 | 4089 | - | 0 |
| `beets-plant2-callers-lastgenreplugin.apply_changes` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0004 | 7.2 | 2.0 | 0.0 | 0.0 | 4220 | - | 0 |
| `beets-plant2-callers-lastgenreplugin.apply_changes` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0258 | 13.9 | 2.0 | 0.0 | 0.0 | 4111 | - | 0 |
| `beets-plant3-callers-database.merge_values` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0009 | 10.9 | 4.0 | 2.0 | 0.0 | 14007 | - | 0 |
| `beets-plant3-callers-database.merge_values` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0219 | 13.6 | 2.0 | 0.0 | 0.0 | 3912 | - | 0 |
| `caddy-callers-celmatcherstringlistmacroexpander` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0008 | 10.0 | 4.0 | 2.0 | 0.0 | 14410 | - | 0 |
| `caddy-callers-celmatcherstringlistmacroexpander` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0302 | 16.3 | 2.0 | 0.0 | 0.0 | 4709 | - | 0 |
| `caddy-callers-instanceid` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0004 | 4.7 | 2.0 | 0.0 | 0.0 | 4235 | - | 0 |
| `caddy-callers-instanceid` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0271 | 12.2 | 2.0 | 0.0 | 0.0 | 4172 | - | 0 |
| `caddy-callers-logging.openlogs` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 5.0 | 2.0 | 0.0 | 0.0 | 4245 | - | 0 |
| `caddy-callers-logging.openlogs` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0256 | 15.1 | 2.0 | 0.0 | 0.0 | 4457 | - | 0 |
| `caddy-callers-newcontextwithcause` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0008 | 9.6 | 5.0 | 3.0 | 0.0 | 19152 | - | 0 |
| `caddy-callers-newcontextwithcause` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0251 | 14.2 | 2.0 | 0.0 | 0.0 | 4432 | - | 0 |
| `caddy-callers-newsharedquicstate` | claude-haiku-5-5 | C-no-tools | 1 | no_answer 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0013 | 13.9 | 5.0 | 3.0 | 0.0 | 25682 | - | 0 |
| `caddy-callers-newsharedquicstate` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0302 | 15.8 | 2.0 | 0.0 | 0.0 | 4689 | - | 0 |
| `caddy-callers-newtester` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 5.3 | 2.0 | 0.0 | 0.0 | 4266 | - | 0 |
| `caddy-callers-newtester` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0121 | 9.0 | 2.0 | 0.0 | 0.0 | 3785 | - | 0 |
| `caddy-callers-provider.rotatekeys` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0006 | 8.4 | 4.0 | 2.0 | 0.0 | 13944 | - | 0 |
| `caddy-callers-provider.rotatekeys` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0653 | 30.9 | 2.0 | 0.0 | 0.0 | 6457 | - | 0 |
| `caddy-plant2-callers-replacer.resolve` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0005 | 5.2 | 2.0 | 0.0 | 0.0 | 4300 | - | 0 |
| `caddy-plant2-callers-replacer.resolve` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0235 | 11.3 | 2.0 | 0.0 | 0.0 | 3998 | - | 0 |
| `caddy-plant2-callers-tls.getautomationpolicyforname` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0002 | 5.2 | 2.0 | 0.0 | 0.0 | 4312 | - | 0 |
| `caddy-plant2-callers-tls.getautomationpolicyforname` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0258 | 15.3 | 2.0 | 0.0 | 0.0 | 4486 | - | 0 |
| `caddy-plant3-callers-upstream.refreshstate` | claude-haiku-5-5 | C-no-tools | 1 | ok 1 | 0.000 | - | 0.000 | 0.000 | 0.0005 | 4.8 | 2.0 | 0.0 | 0.0 | 4292 | - | 0 |
| `caddy-plant3-callers-upstream.refreshstate` | claude-opus-5-5 | C-no-tools | 1 | ok 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.0415 | 19.2 | 2.0 | 0.0 | 0.0 | 4909 | - | 0 |

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
| runs of the batch | 40 | 0.6136 |
