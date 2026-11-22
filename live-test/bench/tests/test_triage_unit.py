"""Unit tests of bench/triage.py.

The batch folders, the tracked key and the slots file are in a temporary folder. The transcripts are
hand-written (tests/fixtures/triage/ and the builders below) with made-up paths and names. No test reads BENCH.
"""
import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from bench import qfiles, runner, triage
from common import settings

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "triage")
ROOT = "/work/s1/proj"
SERVER = "demo-ide"
OPUS, HAIKU = "claude-opus-5-5", "claude-haiku-5-5"
CH = {"id": "demo-refs-Widget", "product": "demo", "tree": "demo", "family": "refs", "keys": "demo/symbols.jsonl",
      "key_id": "go:example.com/demo/pkg.Widget", "sample": "hard", "note": "test"}
QUESTION = "demo-refs-widget"  # the tracked question of CH (qfiles.name_of)


def site(path, line, cls="required", why="use"):
    return {"file": path, "line": line, "col": 1, "class": cls, "why": why}


# The key of the fixture transcript: the IDE results list pkg/a.go:3 (required), pkg/c.go:12 (forbidden), pkg/b.go:8
# (no key site) and /work/s1/proj/pkg/e.go:2 (required, absolute); no IDE result lists pkg/d.go:20 (required).
FIXTURE_SITES = [site("pkg/a.go", 3), site("pkg/c.go", 12, "forbidden", "comment"), site("pkg/d.go", 20),
                 site("pkg/e.go", 2), site("pkg/f.go", 1, "dnc", "unproven")]


def key_record(sites):
    return {"id": CH["key_id"], "lang": "go", "kind": "type", "name": "Widget", "container": "",
            "decl": {"file": "pkg/a.go", "line": 1, "col": 6}, "family": [CH["key_id"]], "sites": list(sites),
            "implementers": [], "source": "scan"}


def key_of(sites):
    """The tracked key of CH for the key sites."""
    return qfiles.key_of(CH, key_record(sites), "v0")


def score(tp, fp, miss):
    return {"tp": tp, "fp": fp, "miss": miss, "ignored": 0, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + miss) if tp + miss else None, "exact": fp == 0 and miss == 0, "invalid": 0,
            "outside": 0, "listed": tp + fp}


def run(arm="C", outcome="ok", model=OPUS, n=1, question=QUESTION, aid=None, variant=None, no_tools=False,
        stop=None, sc=None, tools=None, first_tools=None, answer=(), cost=0.1, seconds=10.0, turns=3, usage=None):
    """A record of run.json (runner.RUN_FIELDS that the triage reads)."""
    args = argparse.Namespace(question=question, arm=arm, aid=aid, variant=variant, no_tools=no_tools,
                              stop_after_tools=stop, env_scrub=False, model=model, n=n)
    tools = {"Bash": 2, "StructuredOutput": 1} if tools is None else tools
    return {"id": runner.run_id_of(args), "question": question, "arm": arm, "aid": aid, "variant": variant,
            "no_tools": no_tools, "stop_after_tools": stop, "env_scrub": False, "model": model, "n": n,
            "outcome": outcome, "reason": None, "cost_usd": cost, "seconds": seconds, "turns": turns, "usage": usage,
            "tools": tools, "first_tools": list(tools)[:5] if first_tools is None else first_tools,
            "answer": list(answer), "invalid": [], "score": sc}


def ide(tool):
    return f"mcp__{SERVER}__{tool}"


def use(uid, name, inp=None):
    block = {"type": "tool_use", "id": uid, "name": name, "input": {} if inp is None else inp}
    return json.dumps({"type": "assistant", "message": {"content": [block]}})


def result(uid, content, is_error=None):
    block = {"type": "tool_result", "tool_use_id": uid, "content": content}
    if is_error is not None:
        block["is_error"] = is_error
    return json.dumps({"type": "user", "message": {"content": [block]}})


def fixture_lines(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read().splitlines()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def put_run(batch, rec, transcript=(), proxy_lines=(), folder=None):
    """A run folder of the batch with run.json (None: no run.json), transcript.jsonl and proxy.jsonl."""
    folder = os.path.join(batch, folder or rec["id"])
    write(os.path.join(folder, "transcript.jsonl"), "".join(line + "\n" for line in transcript))
    write(os.path.join(folder, "proxy.jsonl"), "".join(line + "\n" for line in proxy_lines))
    if rec is not None:
        write(os.path.join(folder, "run.json"), json.dumps(rec, indent=1))
    return folder


class MeasuresTest(unittest.TestCase):
    def test_measures_of_an_ok_run(self):
        usage = {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 300,
                 "cache_read_input_tokens": 4000, "service_tier": "standard"}
        rec = run("PS", aid="rule", sc=score(3, 1, 1), cost=0.25, seconds=42.5, turns=7, usage=usage,
                  tools={"Bash": 2, ide("ide_find_usages"): 3, "mcp__other__ide_find_class": 1, "StructuredOutput": 2})
        m = triage.measures(rec)
        self.assertAlmostEqual(0.75, m["f1"])
        self.assertEqual((0.75, 0.75, False), (m["precision"], m["recall"], m["exact"]))
        self.assertEqual((0.25, 7, 42.5), (m["cost_usd"], m["turns"], m["seconds"]))
        self.assertEqual((6, 4, 4330), (m["tool_calls"], m["ide_calls"], m["tokens"]))
        self.assertEqual({"f1", "precision", "recall", "exact", "cost_usd", "turns", "seconds", "tool_calls",
                          "ide_calls", "tokens"}, set(m))
        exact = triage.measures(run(sc=score(4, 0, 0)))
        self.assertEqual((1.0, 1.0, 1.0, True), (exact["f1"], exact["precision"], exact["recall"], exact["exact"]))
        # No answer line hits the key: f1 0 (the precision of an empty answer is None, as the score has it).
        empty = triage.measures(run(sc=score(0, 0, 4), usage=None))
        self.assertEqual((0.0, None, 0.0, False, None),
                         (empty["f1"], empty["precision"], empty["recall"], empty["exact"], empty["tokens"]))

    def test_failed_outcome_counts_as_wrong(self):
        for outcome in triage.FAILED:
            with self.subTest(outcome=outcome):
                m = triage.measures(run("PF", outcome, sc=score(4, 0, 0) if outcome == "error" else None,
                                        cost=1.5, tools={"Bash": 9}))
                self.assertEqual((0.0, 0.0, 0.0, False), (m["f1"], m["precision"], m["recall"], m["exact"]))
                self.assertEqual((1.5, 9, 0), (m["cost_usd"], m["tool_calls"], m["ide_calls"]))

    def test_excluded_and_stopped_have_no_score(self):
        for outcome in triage.EXCLUDED + ("stopped",):
            with self.subTest(outcome=outcome):
                m = triage.measures(run("P", outcome, sc=score(4, 0, 0), stop=5))
                self.assertEqual((None, None, None, None), (m["f1"], m["precision"], m["recall"], m["exact"]))
                self.assertEqual(2, m["tool_calls"])
        leak = run("P", "key_leak", tools={}, cost=0.3)
        leak.update(tools=None, usage=None, seconds=None)
        m = triage.measures(leak)
        self.assertEqual((0.3, None, None, None, None),
                         (m["cost_usd"], m["seconds"], m["tool_calls"], m["ide_calls"], m["tokens"]))


class ArmLabelTest(unittest.TestCase):
    def test_arm_label_of_each_form(self):
        cases = [(run("C"), "C"), (run("C", no_tools=True), "C-no-tools"), (run("P"), "P"), (run("PF"), "PF"),
                 (run("PFN"), "PFN"), (run("PFN", stop=5), "PFN-stop-5"),
                 (run("PS", aid="rule"), "PS-rule"), (run("PS", aid="skill"), "PS-skill"),
                 (run("P", variant="instructions"), "P-instructions"),
                 (run("P", variant="no-tool-search", stop=5), "P-no-tool-search-stop-5"),
                 (run("PS", aid="rule", stop=5), "PS-rule-stop-5"),
                 (run("C", question="demo-refs-__init__"), "C")]
        for rec, label in cases:
            with self.subTest(label=label):
                self.assertEqual(label, triage.arm_label(rec))
                self.assertIn(f"__{label}__", rec["id"])
        scrub = dict(run("C"), env_scrub=True)
        self.assertEqual("C-scrub", triage.arm_label(scrub))
        old = run("P")
        del old["env_scrub"]
        self.assertEqual("P", triage.arm_label(old))


class LoadBatchTest(unittest.TestCase):
    def test_load_batch_counts_set_aside_and_unfinished(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        b, a = run("P", n=2), run("C", n=1)
        put_run(d, b)
        put_run(d, a)
        put_run(d, run("P", n=3), folder=run("P", n=3)["id"] + ".invalid-1")
        put_run(d, run("P", n=3), folder=run("P", n=3)["id"] + ".api-error-2")
        put_run(d, None, transcript=["{}"], folder=run("PF")["id"])
        write(os.path.join(d, "notes.txt"), "a file is no run\n")
        got = triage.load_batch(d)
        self.assertEqual(sorted([a["id"], b["id"]]), [r["id"] for r in got["runs"]])
        self.assertEqual(os.path.join(d, a["id"]), got["runs"][0]["folder"])
        self.assertEqual("ok", got["runs"][0]["outcome"])
        self.assertEqual((2, 1), (got["set_aside"], got["unfinished"]))

    def test_record_with_no_question_and_no_challenge_is_a_value_error(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        rec = run("C")
        del rec["question"]
        folder = put_run(d, rec)
        with mock.patch.object(qfiles, "by_old_id", side_effect=AssertionError("a read of the keys")):
            with self.assertRaises(ValueError) as e:
                triage.load_batch(d)
        self.assertEqual(f"{os.path.join(folder, 'run.json')}: the run record has no question and no challenge",
                         str(e.exception))


class IdeResultsTest(unittest.TestCase):
    def test_ide_results_pairs_use_and_result(self):
        lines = fixture_lines("transcript.jsonl")
        got = triage.ide_results(lines)
        self.assertEqual([("ide_find_usages", 1, False), ("ide_find_definition", 2, False),
                          ("ide_find_usages", 4, False), ("ide_find_definition", 5, True)],
                         [(r["tool"], r["index"], r["is_error"]) for r in got])
        self.assertEqual({"file": "pkg/a.go", "line": 3, "column": 6, "pageSize": 2}, got[0]["input"])
        self.assertEqual({"cursor": "c1"}, got[2]["input"])
        # The results of toolu_02 and toolu_03 come in the other order in one user event.
        self.assertEqual({("pkg/a.go", 3), ("pkg/c.go", 12)}, got[0]["sites"])
        self.assertEqual({("pkg/b.go", 8)}, got[1]["sites"])
        # The same assistant event two times: one tool use for each block id, as claude_code.parse_transcript counts.
        self.assertEqual(got, triage.ide_results(lines[:4] + [lines[3]] + lines[4:]))
        self.assertEqual(got, triage.ide_results([line.encode("utf-8") for line in lines] + ["no json", "[1]"]))

    def test_ide_results_reads_sites_and_has_more(self):
        text = json.dumps({"method": {"file": "pkg/a.go", "line": 3, "name": "Run"},
                           "hierarchy": [{"file": "/work/s1/proj/pkg/b.go", "line": 9,
                                          "children": [{"file": "/usr/lib/go/src/io/io.go", "line": 90}]},
                                         {"file": "pkg/a.go", "line": 3}],
                           "page": {"hasMore": True},
                           "bad": [{"file": "pkg/x.go", "line": "4"}, {"file": "pkg/y.go", "line": True},
                                   {"file": 7, "line": 4}, {"path": "pkg/z.go", "line": 4}],
                           "hasMore": False})
        lines = [use("u1", ide("ide_find_super_methods")), result("u1", text),
                 use("u2", ide("ide_find_usages")), result("u2", json.dumps({"usages": [], "hasMore": False}))]
        first, second = triage.ide_results(lines)
        self.assertEqual({("pkg/a.go", 3), ("/work/s1/proj/pkg/b.go", 9), ("/usr/lib/go/src/io/io.go", 90)},
                         first["sites"])
        self.assertTrue(first["has_more"])
        self.assertIsNone(first["text"])
        self.assertEqual((set(), False, None), (second["sites"], second["has_more"], second["text"]))

    def test_ide_result_with_block_list_content(self):
        blocks = [{"type": "text", "text": '{"usages": [{"file": "pkg/a.go", '},
                  {"type": "image", "source": {"type": "base64", "data": "AAAA"}},
                  {"type": "text", "text": '"line": 4}], "hasMore": true}'}]
        got, = triage.ide_results([use("u1", ide("ide_find_usages")), result("u1", blocks)])
        self.assertEqual(({("pkg/a.go", 4)}, True, False, None),
                         (got["sites"], got["has_more"], got["is_error"], got["text"]))

    def test_ide_result_that_is_no_json(self):
        long_text = "The index is not ready. " * 20
        lines = [use("u1", ide("ide_find_class"), {"query": "Widget"}), result("u1", long_text),
                 use("u2", ide("ide_find_usages")), result("u2", [{"type": "text", "text": "plain words"}], False)]
        first, second = triage.ide_results(lines)
        self.assertEqual((set(), False, False), (first["sites"], first["has_more"], first["is_error"]))
        self.assertEqual(long_text[:200], first["text"])
        self.assertEqual("plain words", second["text"])

    def test_tool_use_with_no_result(self):
        lines = [use("u1", "Bash", {"command": "ls"}), result("u1", "a.go"),
                 use("u2", ide("ide_search_text"), {"query": "Widget"})]
        got, = triage.ide_results(lines)
        self.assertEqual(("ide_search_text", 1, None, set(), False, None),
                         (got["tool"], got["index"], got["is_error"], got["sites"], got["has_more"], got["text"]))


class FlagsTest(unittest.TestCase):
    def flags(self, rec, lines, sites=FIXTURE_SITES, proxy_lines=(), root=ROOT, slug=None):
        return triage.flags(rec, lines, list(proxy_lines), key_of(sites), root=root, slug=slug)

    def test_repo_access_flag(self):
        curl = "curl https://raw.githubusercontent.com/o/r/main/live-test/bench/keys/x.json"
        finder = "mcp__goland-idesense__ide_find_usages"
        cases = [
            ("curl of a key with the slug", [use("u1", "Bash", {"command": curl})], "o/r", True),
            ("slug in another case", [use("u1", "Bash", {"command": "git clone https://github.com/O/R.git"})],
             "o/r", True),
            ("slug of the remote in another case", [use("u1", "Bash", {"command": "curl https://github.com/o/r"})],
             "O/R", True),
            ("WebFetch", [use("u1", "WebFetch", {"url": "https://github.com/o/r", "prompt": "list the files"})],
             "o/r", True),
            ("WebSearch", [use("u1", "WebSearch", {"query": "o/r question keys"})], "o/r", True),
            ("bench/keys with no slug", [use("u1", "Bash", {"command": "cat live-test/bench/keys/x.json"})], None,
             True),
            ("slug text with no slug", [use("u1", "Bash", {"command": "curl https://github.com/o/r"})], None, False),
            ("other Bash", [use("u1", "Bash", {"command": "grep -rn Widget pkg"})], "o/r", False),
            ("Read is no such tool", [use("u1", "Read", {"file_path": "/x/o/r/live-test/bench/keys/x.json"})],
             "o/r", False),
            ("only the MCP tool", [use("u1", finder, {"file": "pkg/a.go", "line": 3}),
                                   result("u1", json.dumps({"usages": []}))], "o/r", False),
            ("MCP input with the texts", [use("u1", finder, {"file": "o/r/bench/keys.go", "line": 3})], "o/r",
             False),
        ]
        for label, lines, slug, expected in cases:
            with self.subTest(label):
                self.assertIs(expected, self.flags(run("PF"), lines, slug=slug)["repo_access"])

    def test_no_plugin_call_flag(self):
        with_ide = {"Bash": 1, ide("ide_find_usages"): 2, "StructuredOutput": 1}
        cases = [(run("P"), True), (run("PS", aid="skill"), True), (run("PF", "timeout"), True),
                 (run("PFN"), True), (run("PFN", "invalid"), False),
                 (run("P", "stopped", stop=5), True), (run("C"), False), (run("C", no_tools=True), False),
                 (run("PS", aid="rule", tools=with_ide), False), (run("P", "invalid"), False),
                 (run("PF", "api_error"), False), (run("PF", "key_leak"), False)]
        for rec, expected in cases:
            with self.subTest(run=rec["id"], outcome=rec["outcome"]):
                got = self.flags(rec, [])
                self.assertIs(expected, got["no_plugin_call"])
        got = self.flags(run("PS", aid="rule", tools=with_ide), [])
        self.assertEqual((2, {"ide_find_usages": 2}), (got["ide_calls"], got["ide_tools"]))

    def test_has_more_no_cursor_flag_and_its_clear_by_a_cursor_call(self):
        more = json.dumps({"usages": [{"file": "pkg/a.go", "line": 3}], "hasMore": True, "nextCursor": "c1"})
        done = json.dumps({"usages": [], "hasMore": False})
        head = [use("u1", ide("ide_find_usages"), {"cursor": "old"}), result("u1", done),
                use("u2", ide("ide_find_usages"), {"file": "pkg/a.go", "line": 3}), result("u2", more),
                use("u3", ide("ide_find_class"), {"query": "Widget"}), result("u3", more)]
        rec = run("P", tools={ide("ide_find_usages"): 3})
        self.assertEqual(2, self.flags(rec, head)["has_more_no_cursor"])
        later = head + [use("u4", "Bash", {"command": "ls"}), use("u5", ide("ide_find_usages"), {"cursor": "c1"}),
                        result("u5", done)]
        self.assertEqual(0, self.flags(rec, later)["has_more_no_cursor"])

    def test_ide_forbidden_lines_and_answer_repeat(self):
        sites = [site("a.go", 3), site("a.go", 5, "forbidden", "comment"), site("a.go", 7, "dnc", "unproven"),
                 site("b.go", 2), site("b.go", 2, "forbidden", "decoy"), site("b.go", 6, "forbidden", "string")]
        listed = json.dumps({"usages": [{"file": f, "line": n} for f, n in
                                        (("a.go", 3), ("a.go", 5), ("a.go", 7), ("a.go", 9), ("b.go", 2))]})
        second = json.dumps({"usages": [{"file": "b.go", "line": 6}, {"file": "a.go", "line": 5}]})
        lines = [use("u1", ide("ide_find_usages")), result("u1", listed),
                 use("u2", ide("ide_find_usages")), result("u2", second)]
        rec = run("PF", tools={ide("ide_find_usages"): 2}, answer=["a.go:3", "a.go:5", "a.go:9"])
        got = self.flags(rec, lines, sites)
        # a.go:9 is in no key site (no class); b.go:2 is required+decoy.
        self.assertEqual({("a.go", 5), ("b.go", 6)}, got["ide_forbidden_lines"])
        self.assertEqual(1, got["answer_repeats_ide_forbidden"])

    def test_ide_missed_required_and_answer_miss(self):
        sites = [site("a.go", 3), site("a.go", 4), site("b.go", 8), site("c.go", 1, "dnc", "unproven"),
                 site("d.go", 2), site("d.go", 2, "forbidden", "decoy")]
        listed = json.dumps({"usages": [{"file": "a.go", "line": 3}]})
        lines = [use("u1", ide("ide_find_usages")), result("u1", listed)]
        rec = run("PS", aid="rule", tools={ide("ide_find_usages"): 1}, answer=["a.go:3", "a.go:4"])
        got = self.flags(rec, lines, sites)
        self.assertEqual({("a.go", 4), ("b.go", 8), ("d.go", 2)}, got["ide_missed_required"])
        self.assertEqual(2, got["answer_miss_not_in_ide"])
        none = self.flags(run("P", answer=["a.go:3"]), [], sites)
        self.assertEqual((set(), 0), (none["ide_missed_required"], none["answer_miss_not_in_ide"]))

    def test_absolute_ide_path_inside_the_root_is_normalized(self):
        sites = [site("pkg/a.go", 3), site("pkg/a.go", 5, "forbidden", "comment")]
        listed = json.dumps({"usages": [{"file": "/work/s1/proj/pkg/a.go", "line": 5},
                                        {"file": "./pkg/a.go", "line": 3},
                                        {"file": "/work/s1/proj-old/pkg/a.go", "line": 3},
                                        {"file": "/usr/lib/go/src/io/io.go", "line": 90}]})
        lines = [use("u1", ide("ide_find_usages")), result("u1", listed)]
        rec = run("P", tools={ide("ide_find_usages"): 1}, answer=["pkg/a.go:5"])
        got = self.flags(rec, lines, sites, root=ROOT + "/")
        self.assertEqual({("pkg/a.go", 5)}, got["ide_forbidden_lines"])
        self.assertEqual((1, set()), (got["answer_repeats_ide_forbidden"], got["ide_missed_required"]))
        raw = self.flags(rec, lines, sites, root=None)
        self.assertEqual((set(), {("pkg/a.go", 3)}), (raw["ide_forbidden_lines"], raw["ide_missed_required"]))

    def test_text_after_ide_counts_grep_in_bash(self):
        bash = ["grep -rn Widget pkg", "rg -w Widget", "cd pkg && git grep -n Widget", "ag Widget .",
                "ack Widget", "ls -la | /usr/bin/grep go", "ls -la", "cat tag.txt", "echo --tag", "egrep x a.go",
                "rgx --help"]
        lines = [use("u0", "Grep", {"pattern": "Widget"}), use("u1", "Bash", {"command": "grep -rn Widget ."}),
                 use("u2", ide("ide_find_usages")), result("u2", "{}"), use("u3", "Grep", {"pattern": "Widget"}),
                 use("u4", "Read", {"file_path": "pkg/a.go"})]
        lines += [use(f"b{i}", "Bash", {"command": command}) for i, command in enumerate(bash)]
        rec = run("PF", tools={ide("ide_find_usages"): 1})
        self.assertEqual(7, self.flags(rec, lines)["text_after_ide"])
        self.assertEqual(0, self.flags(run("C"), lines[:2] + lines[4:])["text_after_ide"])

    def test_edit_then_ide_no_sync_and_its_clear_by_sync(self):
        # Counted: the two IDE uses after Edit, the one after Write and the one after NotebookEdit.
        names = [ide("ide_find_usages"), "Edit", ide("ide_find_usages"), "Read", ide("ide_diagnostics"),
                 ide("ide_sync_files"), ide("ide_find_usages"), "Write", ide("ide_find_class"),
                 ide("ide_sync_files"), ide("ide_find_symbol"), "NotebookEdit", "Bash", ide("ide_find_definition")]
        lines = [use(f"u{i}", name) for i, name in enumerate(names)]
        rec = run("PF", tools={ide("ide_find_usages"): 3})
        self.assertEqual(4, self.flags(rec, lines)["edit_then_ide_no_sync"])
        self.assertEqual(0, self.flags(rec, [use("e", "Edit"), use("s", ide("ide_sync_files"))])
                         ["edit_then_ide_no_sync"])

    def test_anchor_error_flag(self):
        def err(message):
            return json.dumps({"error": "tool_error", "message": message})

        cases = [(err("No named element at position. Named elements on line 3: 'Run' at column 6."), True),
                 (err("Could not resolve symbol definition"), True), (err("index_not_ready"), True),
                 ("Error: File not found: pkg/zz.go", True), (err("Symbol not found in project files"), True),
                 (err("timeout after 30 s"), True), (err("timeout after 30 s"), True),
                 (err("No named element at position. (second form)"), None),
                 ("File not found is only a word of this text", False),
                 (err("Could not resolve symbol definition"), False)]
        lines = []
        for i, (content, is_error) in enumerate(cases):
            lines += [use(f"u{i}", ide("ide_find_definition")), result(f"u{i}", content, is_error)]
        proxy_lines = fixture_lines("proxy.jsonl")
        rec = run("PF", tools={ide("ide_find_definition"): len(cases)})
        got = self.flags(rec, lines, proxy_lines=proxy_lines)
        # The anchor phrases: cases 0, 1, 3, 4 (error results), 7 and 9 (a JSON `error`, is_error absent or false).
        # Case 8 has a phrase, but it is no error result.
        self.assertEqual(6, got["anchor_error"])
        # 7 error results (cases 0 to 6) and 1 refused tool call of the proxy log.
        self.assertEqual(8, got["ide_error"])
        self.assertEqual([c[:200] for c, _ in cases[:5]], got["ide_error_texts"])
        none = self.flags(rec, [use("u1", ide("ide_find_definition")), result("u1", err("Could not resolve symbol"),
                                                                                 True)])
        self.assertEqual((1, 1), (none["anchor_error"], none["ide_error"]))

    def test_fixture_transcript_flags(self):
        rec = run("PF", sc=score(1, 1, 2), answer=["pkg/a.go:3", "pkg/c.go:12"],
                  tools={"Grep": 1, ide("ide_find_usages"): 2, ide("ide_find_definition"): 2, "Bash": 1,
                         "StructuredOutput": 1})
        got = self.flags(rec, fixture_lines("transcript.jsonl"), proxy_lines=fixture_lines("proxy.jsonl"))
        self.assertEqual(set(triage.FLAGS) - {"plugin_wrong_control_right"}, set(got))
        self.assertEqual({"no_plugin_call": False, "ide_calls": 4,
                          "ide_tools": {"ide_find_usages": 2, "ide_find_definition": 2}, "ide_error": 2,
                          "anchor_error": 1, "has_more_no_cursor": 0,
                          "ide_forbidden_lines": {("pkg/c.go", 12)}, "answer_repeats_ide_forbidden": 1,
                          "ide_missed_required": {("pkg/d.go", 20)}, "answer_miss_not_in_ide": 1,
                          "text_after_ide": 1, "edit_then_ide_no_sync": 0, "repo_access": False},
                         {k: v for k, v in got.items() if k != "ide_error_texts"})
        self.assertEqual(1, len(got["ide_error_texts"]))
        self.assertIn("No named element at position", got["ide_error_texts"][0])


class RepoSlugTest(unittest.TestCase):
    def slug(self, stdout="", code=0, error=None):
        def fake(cmd, **kwargs):
            self.assertEqual(["git", "--no-optional-locks", "-C", "/r", "remote", "get-url", "origin"], cmd)
            if error is not None:
                raise error
            return subprocess.CompletedProcess(cmd, code, stdout, "")

        with mock.patch.object(settings, "repo_root", return_value="/r"), \
                mock.patch.object(subprocess, "run", side_effect=fake):
            return triage.repo_slug()

    def test_slug_of_each_url_form(self):
        for url in ("https://github.com/o/r.git\n", "https://github.com/o/r\n", "git@github.com:o/r.git\n",
                    "git@github.com:o/r"):
            with self.subTest(url=url):
                self.assertEqual("o/r", self.slug(url))
        self.assertEqual("O/R", self.slug("https://github.com/O/R.git\n"))

    def test_no_slug_with_no_remote_no_git_or_another_url(self):
        self.assertIsNone(self.slug("", code=2))
        self.assertIsNone(self.slug(error=FileNotFoundError("git")))
        self.assertIsNone(self.slug(error=subprocess.TimeoutExpired("git", 60)))
        for url in ("https://gitlab.com/o/r.git\n", "https://github.com/o/r/tree/main\n", "/srv/git/r.git\n"):
            with self.subTest(url=url):
                self.assertIsNone(self.slug(url))


class TablesTest(unittest.TestCase):
    def test_plugin_wrong_control_right(self):
        x, y, z = "demo-x", "demo-y", "demo-z"
        records = [
            run("C", question=x, sc=score(2, 0, 0)), run("C", question=x, n=2, sc=score(2, 0, 0)),
            run("C", "invalid", question=x, n=3), run("C", question=x, no_tools=True, sc=score(0, 0, 2)),
            run("PS", question=x, aid="rule", sc=score(1, 0, 1)),
            run("PS", "timeout", question=x, aid="rule", n=2),
            run("PS", "invalid", question=x, aid="rule", n=3),
            run("PS", "stopped", question=x, aid="rule", stop=5, sc=score(1, 0, 1)),
            run("PF", question=x, sc=score(2, 0, 0)),
            run("PF", question=x, model=HAIKU, sc=score(0, 1, 2)),
            run("C", question=y, sc=score(2, 0, 0)), run("C", "timeout", question=y, n=2),
            run("PF", question=y, sc=score(0, 1, 2)),
            run("C", "invalid", question=z), run("PF", question=z, sc=score(0, 1, 2)),
        ]
        triage.batch_flags(records)
        got = {(r["question"], triage.arm_label(r), r["model"], r["n"]) for r in records
               if r["plugin_wrong_control_right"]}
        self.assertEqual({(x, "PS-rule", OPUS, 1), (x, "PS-rule", OPUS, 2)}, got)
        self.assertTrue(all(isinstance(r["plugin_wrong_control_right"], bool) for r in records))

    def test_summary_rows_means_and_adoption(self):
        with_ide = {"Bash": 1, ide("ide_find_usages"): 2, "StructuredOutput": 1}
        records = [
            run("C", sc=score(2, 0, 0), cost=0.1, seconds=10.0, turns=4),
            run("C", "timeout", n=2, cost=0.3, seconds=30.0, turns=8, tools={"Bash": 6}),
            run("C", "invalid", n=3, cost=9.0),
            run("PS", aid="rule", sc=score(1, 1, 1), tools=with_ide, cost=0.2),
            run("PS", aid="rule", n=2, sc=score(2, 0, 0), cost=0.4, usage={"input_tokens": 5, "output_tokens": 5}),
            run("PS", "stopped", aid="rule", n=3, stop=5, sc=score(2, 0, 0), tools=with_ide),
            run("PS", "stopped", aid="skill", stop=5, tools=with_ide),
        ]
        rows = triage.summary_rows(records)
        self.assertEqual([(QUESTION, OPUS, "C"), (QUESTION, OPUS, "PS-rule")],
                         [(r["question"], r["model"], r["arm_label"]) for r in rows])
        c, ps = rows
        self.assertEqual((2, {"ok": 1, "timeout": 1}, 1), (c["runs"], c["outcomes"], c["excluded"]))
        self.assertEqual((0.5, 0.5, 0.5, 0.5), (c["f1"], c["precision"], c["recall"], c["exact"]))
        self.assertAlmostEqual(0.2, c["cost_usd"])
        self.assertEqual((20.0, 6.0, 4.0, 0.0, None, None),
                         (c["seconds"], c["turns"], c["tool_calls"], c["ide_calls"], c["tokens"], c["adoption"]))
        self.assertEqual((2, {"ok": 2}, 0, 0.5), (ps["runs"], ps["outcomes"], ps["excluded"], ps["adoption"]))
        self.assertAlmostEqual((2 * 0.5 * 0.5 / 1.0 + 1.0) / 2, ps["f1"])
        self.assertEqual((0.5, 1.0, 10.0), (ps["exact"], ps["ide_calls"], ps["tokens"]))
        only_excluded = triage.summary_rows([run("PF", "invalid"), run("PF", "api_error", n=2)])
        self.assertEqual([(0, 2, None, None)],
                         [(r["runs"], r["excluded"], r["f1"], r["adoption"]) for r in only_excluded])

    def test_paired_differences(self):
        x, y, z = "demo-x", "demo-y", "demo-z"
        records = [
            run("C", question=x, sc=score(2, 0, 0), cost=0.1, seconds=10.0),
            run("C", question=x, n=2, sc=score(2, 0, 2), cost=0.3, seconds=20.0),
            run("PF", question=x, sc=score(2, 0, 0), cost=0.5, seconds=40.0,
                tools={ide("ide_find_usages"): 1, "Bash": 1, "StructuredOutput": 1}),
            run("PS", question=x, aid="rule", sc=score(2, 2, 0), cost=0.2, seconds=5.0),
            run("C", question=x, no_tools=True, sc=score(0, 0, 2)),
            run("C", question=y, sc=score(2, 0, 0)), run("PF", "invalid", question=y),
            run("PS", "stopped", question=y, aid="rule", stop=5, sc=score(2, 0, 0)),
            run("PF", question=z, sc=score(2, 0, 0)), run("C", "key_leak", question=z),
            run("C", question=x, model=HAIKU, sc=score(2, 0, 0)),
            run("PF", question=x, model=HAIKU, sc=score(0, 2, 2)),
        ]
        rows = triage.paired(records)
        # The arms in the order of runner.ARMS: PS before PF.
        self.assertEqual([(HAIKU, "PF", x), (OPUS, "PS-rule", x), (OPUS, "PF", x)],
                         [(r["model"], r["arm_label"], r["question"]) for r in rows])
        self.assertEqual(["C"] * 3, [r["base_label"] for r in rows])
        haiku, ps, pf = rows
        self.assertEqual((0.0, 1.0, -1.0), (haiku["f1_arm"], haiku["f1_base"], haiku["f1_diff"]))
        c_f1 = (1.0 + 2 * 1.0 * 0.5 / 1.5) / 2
        self.assertAlmostEqual(1.0 - c_f1, pf["f1_diff"])
        self.assertEqual((1.0, 0.5, 0.5), (pf["exact_arm"], pf["exact_base"], pf["exact_diff"]))
        self.assertAlmostEqual(0.3, pf["cost_usd_diff"])
        self.assertEqual((40.0, 15.0, 25.0), (pf["seconds_arm"], pf["seconds_base"], pf["seconds_diff"]))
        self.assertEqual((2.0, 2.0, 0.0), (pf["tool_calls_arm"], pf["tool_calls_base"], pf["tool_calls_diff"]))
        self.assertEqual((0.0, -0.5), (ps["exact_arm"], ps["exact_diff"]))
        self.assertEqual({"model", "arm_label", "base_label", "question"} | {f"{k}_{p}" for k in triage.PAIRED
                                                                              for p in ("arm", "base", "diff")},
                         set(pf))

    def test_paired_rows_PFN_minus_PF(self):
        x, y, z = "demo-x", "demo-y", "demo-z"
        records = [
            run("C", question=x, sc=score(2, 0, 0), cost=0.1),
            run("PF", question=x, sc=score(1, 0, 1), cost=0.4, seconds=30.0),
            run("PFN", question=x, sc=score(2, 0, 0), cost=0.5, seconds=20.0),
            run("PFN", question=x, n=2, sc=score(2, 0, 0), cost=0.5, seconds=20.0),
            # y: no C run, so only PFN - PF.
            run("PF", question=y, sc=score(2, 0, 0)), run("PFN", question=y, sc=score(0, 2, 2)),
            # z: the PF run is no measurement, so only PFN - C.
            run("C", question=z, sc=score(2, 0, 0)), run("PF", "invalid", question=z),
            run("PFN", question=z, sc=score(2, 0, 0)),
            run("PS", question=x, aid="rule", sc=score(2, 0, 0)),
            # A PFN run that was stopped is in no pair; PFN of another model has no PF run.
            run("PFN", "stopped", question=y, n=2, stop=5), run("PFN", question=x, model=HAIKU, sc=score(2, 0, 0)),
        ]
        rows = triage.paired(records)
        self.assertEqual([(OPUS, "PS-rule", "C", x), (OPUS, "PF", "C", x), (OPUS, "PFN", "C", x),
                          (OPUS, "PFN", "C", z), (OPUS, "PFN", "PF", x), (OPUS, "PFN", "PF", y)],
                         [(r["model"], r["arm_label"], r["base_label"], r["question"]) for r in rows])
        pfn_x, pfn_y = rows[4], rows[5]
        self.assertAlmostEqual(1.0 - 2 * 1.0 * 0.5 / 1.5, pfn_x["f1_diff"])
        self.assertEqual((1.0, 0.0, 1.0), (pfn_x["exact_arm"], pfn_x["exact_base"], pfn_x["exact_diff"]))
        self.assertAlmostEqual(0.1, pfn_x["cost_usd_diff"])
        self.assertEqual((20.0, 30.0, -10.0), (pfn_x["seconds_arm"], pfn_x["seconds_base"], pfn_x["seconds_diff"]))
        self.assertEqual((0.0, 1.0, -1.0), (pfn_y["f1_arm"], pfn_y["f1_base"], pfn_y["f1_diff"]))

    def test_paired_rows_of_PFR_and_PFL_have_the_bases_C_and_PF(self):
        records = [
            run("PFL", sc=score(2, 0, 0)), run("PFR", sc=score(2, 1, 0)), run("PFN", sc=score(2, 0, 0)),
            run("PFR", stop=5, sc=score(1, 0, 1)), run("PF", stop=5, sc=score(2, 0, 0)),
            run("PF", sc=score(1, 0, 1)), run("C", sc=score(2, 0, 0)),
        ]
        rows = triage.paired(records)
        self.assertEqual([("PF", "C"), ("PF-stop-5", "C"), ("PFN", "C"), ("PFN", "PF"), ("PFR", "C"), ("PFR", "PF"),
                          ("PFR-stop-5", "C"), ("PFR-stop-5", "PF-stop-5"), ("PFL", "C"), ("PFL", "PF")],
                         [(r["arm_label"], r["base_label"]) for r in rows])
        by_pair = {(r["arm_label"], r["base_label"]): r for r in rows}
        self.assertAlmostEqual(0.8 - 2 / 3, by_pair[("PFR", "PF")]["f1_diff"])
        self.assertAlmostEqual(1.0 - 2 / 3, by_pair[("PFL", "PF")]["f1_diff"])
        self.assertAlmostEqual(2 / 3 - 1.0, by_pair[("PFR-stop-5", "PF-stop-5")]["f1_diff"])

    def test_paired_rows_of_PFG_have_the_bases_C_and_PF(self):
        records = [
            run("PFG", sc=score(2, 0, 0)), run("PFG", stop=5, sc=score(1, 0, 1)), run("PF", stop=5, sc=score(2, 0, 0)),
            run("PF", sc=score(1, 0, 1)), run("C", sc=score(2, 0, 0)),
        ]
        rows = triage.paired(records)
        self.assertEqual([("PF", "C"), ("PF-stop-5", "C"), ("PFG", "C"), ("PFG", "PF"), ("PFG-stop-5", "C"),
                          ("PFG-stop-5", "PF-stop-5")],
                         [(r["arm_label"], r["base_label"]) for r in rows])
        by_pair = {(r["arm_label"], r["base_label"]): r for r in rows}
        self.assertAlmostEqual(1.0 - 2 / 3, by_pair[("PFG", "PF")]["f1_diff"])
        self.assertAlmostEqual(2 / 3 - 1.0, by_pair[("PFG-stop-5", "PF-stop-5")]["f1_diff"])

    def test_paired_rows_of_PFI_and_PFS_have_the_bases_C_and_PF(self):
        self.assertEqual(("PFN", "PFR", "PFL", "PFG", "PFI", "PFS"), triage.PF_BASED)
        self.assertEqual([arm for arm in runner.ARMS if arm in triage.PF_BASED], list(triage.PF_BASED),
                         "the order of runner.ARMS")
        records = [
            run("PFS", sc=score(2, 1, 0)), run("PFI", stop=5, sc=score(1, 0, 1)), run("PFI", sc=score(2, 0, 0)),
            run("PF", stop=5, sc=score(2, 0, 0)), run("PF", sc=score(1, 0, 1)), run("C", sc=score(2, 0, 0)),
        ]
        rows = triage.paired(records)
        self.assertEqual([("PF", "C"), ("PF-stop-5", "C"), ("PFI", "C"), ("PFI", "PF"), ("PFI-stop-5", "C"),
                          ("PFI-stop-5", "PF-stop-5"), ("PFS", "C"), ("PFS", "PF")],
                         [(r["arm_label"], r["base_label"]) for r in rows])
        by_pair = {(r["arm_label"], r["base_label"]): r for r in rows}
        self.assertAlmostEqual(1.0 - 2 / 3, by_pair[("PFI", "PF")]["f1_diff"])
        self.assertAlmostEqual(2 / 3 - 1.0, by_pair[("PFI-stop-5", "PF-stop-5")]["f1_diff"])
        self.assertAlmostEqual(0.8 - 2 / 3, by_pair[("PFS", "PF")]["f1_diff"])

    def test_tables_give_the_arms_in_the_order_of_runner_ARMS(self):
        arms = ("PFS", "PFI", "PFG", "PFL", "PFR", "PFN", "PF", "PS", "P", "C")
        records = [run(arm, aid="rule" if arm == "PS" else None, sc=score(2, 0, 0)) for arm in arms]
        self.assertEqual(("C", "P", "PS", "PF", "PFN", "PFR", "PFL", "PFG", "PFI", "PFS"), runner.ARMS)
        self.assertEqual(["C", "P", "PS-rule", "PF", "PFN", "PFR", "PFL", "PFG", "PFI", "PFS"],
                         [r["arm_label"] for r in triage.summary_rows(records)])
        self.assertEqual(["P", "PS-rule", "PF", "PFN", "PFR", "PFL", "PFG", "PFI", "PFS"],
                         [r["arm_label"] for r in triage.adoption_rows(records)])

    def test_bootstrap_is_stable_with_a_seed_and_handles_small_lists(self):
        self.assertEqual((None, None, None), triage.bootstrap([]))
        self.assertEqual((0.25, None, None), triage.bootstrap([0.25]))
        values = [0.0, 0.1, -0.2, 0.5, 0.3, 0.05, -0.1, 0.4]
        first = triage.bootstrap(values)
        self.assertEqual(first, triage.bootstrap(values))
        self.assertEqual(first, triage.bootstrap(values, seed=1, n=10000))
        mean, low, high = first
        self.assertAlmostEqual(sum(values) / len(values), mean)
        self.assertTrue(min(values) <= low < mean < high <= max(values), first)
        other = triage.bootstrap(values, seed=2, n=200)
        self.assertEqual(other, triage.bootstrap(values, seed=2, n=200))
        self.assertEqual((0.2, 0.2, 0.2), tuple(round(v, 12) for v in triage.bootstrap([0.2, 0.2, 0.2])))

    def test_adoption_rows_use_first_tools(self):
        first_ide = ["ToolSearch", ide("ide_find_usages"), "Bash"]
        late = {"Bash": 5, ide("ide_find_usages"): 1}
        records = [
            run("PS", "stopped", aid="rule", stop=5, model=HAIKU, first_tools=first_ide, tools={}),
            run("PS", aid="rule", stop=5, model=HAIKU, n=2, first_tools=first_ide, sc=score(2, 0, 0)),
            run("PS", aid="rule", stop=5, model=HAIKU, n=3, first_tools=["Bash"] * 5, tools=late),
            run("PS", aid="rule", stop=5, model=HAIKU, n=4, first_tools=["Bash", "StructuredOutput"]),
            run("PS", "invalid", aid="rule", stop=5, model=HAIKU, n=5, first_tools=first_ide),
            run("PS", aid="rule", stop=5, model=OPUS, first_tools=["Bash", "Bash"]),
            run("P", "timeout", variant="instructions", stop=5, first_tools=[]),
            run("C", first_tools=["Bash"]),
            run("PFN", first_tools=first_ide), run("PF", first_tools=["Bash"]),
        ]
        rows = triage.adoption_rows(records)
        self.assertEqual([("P-instructions-stop-5", OPUS, 1, 0, 0.0), ("PS-rule-stop-5", HAIKU, 4, 2, 0.5),
                          ("PS-rule-stop-5", OPUS, 1, 0, 0.0), ("PF", OPUS, 1, 0, 0.0), ("PFN", OPUS, 1, 1, 1.0)],
                         [(r["arm_label"], r["model"], r["runs"], r["ide_first"], r["share"]) for r in rows])


class ReportTest(unittest.TestCase):
    def setUp(self):
        d = self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        self.keys = os.path.join(d, "tracked", "keys")
        write(os.path.join(self.keys, QUESTION + ".json"), json.dumps(key_of(FIXTURE_SITES), indent=2) + "\n")
        slots = os.path.join(d, "slots.json")
        write(slots, json.dumps({"demo": {"slot": "s1", "path": ROOT, "product": "demo"}}))
        self.runs = os.path.join(d, "runs")
        # The repository root is the temporary folder: no git repository, so no slug (RepoSlugTest).
        for target, name, value in ((qfiles, "KEYS", self.keys), (triage, "SLOTS_FILE", slots),
                                    (triage, "RUNS", self.runs), (settings, "repo_root", lambda: d)):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.batch = os.path.join(self.runs, "b1")
        self.out = os.path.join(d, "out")
        self.ledger_dir = os.path.join(d, "ledger")
        versions = {"plugin_version_start": "2.2.0-dev.01", "plugin_version_end": "2.2.0-dev.01",
                    "image_id": "sha256:aa"}
        self.pf = run("PF", sc=score(1, 1, 2), answer=["pkg/a.go:3", "pkg/c.go:12"], cost=0.5, seconds=40.0,
                      tools={"Grep": 1, ide("ide_find_usages"): 2, ide("ide_find_definition"): 2, "Bash": 1,
                             "StructuredOutput": 1})
        self.pf.update(versions, started="2026-11-18T00:10:00+00:00")
        self.c = run("C", sc=score(3, 0, 0), answer=["pkg/a.go:3", "pkg/d.go:20", "pkg/e.go:2"], cost=0.1234,
                     seconds=12.0)
        self.c.update(versions, started="2026-11-17T23:59:59+00:00")
        self.stopped = run("PS", "stopped", aid="rule", stop=5, first_tools=["ToolSearch", ide("ide_find_usages")],
                           tools={"ToolSearch": 1, ide("ide_find_usages"): 4}, cost=None)
        self.stopped.update(versions, plugin_version_end="2.2.0-dev.02", started="2026-11-18T00:01:00+00:00")
        put_run(self.batch, self.pf, fixture_lines("transcript.jsonl"), fixture_lines("proxy.jsonl"))
        put_run(self.batch, self.c, [use("u1", "Bash", {"command": "grep -rn Widget ."}), result("u1", "x")])
        put_run(self.batch, self.stopped, [use("u1", "ToolSearch"), use("u2", ide("ide_find_usages"))])
        put_run(self.batch, run("P"), folder=run("P")["id"] + ".invalid-1")
        put_run(self.batch, None, ["{}"], folder=run("PS", aid="rule")["id"])

    def test_report_writes_both_files(self):
        path = triage.report(self.batch, self.out)
        self.assertEqual(os.path.join(self.out, "summary.md"), path)
        with open(os.path.join(self.out, "runs.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual(sorted([self.pf["id"], self.c["id"], self.stopped["id"]]), [r["id"] for r in rows])
        pf = next(r for r in rows if r["id"] == self.pf["id"])
        self.assertEqual(["id", "question", "model", "arm_label", "n", "outcome"], list(pf)[:6])
        self.assertEqual(("PF", QUESTION, OPUS, 1, "ok"),
                         (pf["arm_label"], pf["question"], pf["model"], pf["n"], pf["outcome"]))
        self.assertAlmostEqual(0.4, pf["f1"])
        self.assertEqual((["pkg/c.go:12"], ["pkg/d.go:20"], 2, 1, 1, True),
                         (pf["ide_forbidden_lines"], pf["ide_missed_required"], pf["ide_error"], pf["anchor_error"],
                          pf["text_after_ide"], pf["plugin_wrong_control_right"]))
        self.assertTrue(set(triage.FLAGS) <= set(pf))
        c = next(r for r in rows if r["id"] == self.c["id"])
        self.assertEqual(([], False, 0), (c["ide_forbidden_lines"], c["plugin_wrong_control_right"], c["ide_calls"]))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        self.assertEqual(["## Batch", "## By question, model and arm", "## Paired differences", "## Adoption",
                          "## Flags"], headings)
        for line in ("| ok | 2 |", "| stopped | 1 |", "| set aside | 1 |", "| unfinished | 1 |",
                     "| total cost (USD) | 0.6234 |", f"| `{QUESTION}` | {OPUS} | PF | 1 | ok 1 | 0.400 |",
                     f"| PS-rule-stop-5 | {OPUS} | 1 | 1 | 1.000 |",
                     f"| plugin_wrong_control_right | 1 | `{self.pf['id']}` |"):
            self.assertIn(line, text)
        paired = [line for line in text.splitlines() if line.startswith(f"| {OPUS} | PF |")]
        self.assertEqual(2, len(paired), text)
        self.assertTrue(paired[0].startswith(f"| {OPUS} | PF | C | `{QUESTION}` | 0.400 | 1.000 | -0.600 |"),
                        paired[0])
        self.assertTrue(paired[1].startswith(f"| {OPUS} | PF | C | all | 0.400 | 1.000 | -0.600 |"), paired[1])

    def test_report_reads_records_with_and_without_login(self):
        # A record of a runner before the field `login` has no `login` (self.pf, self.stopped).
        self.assertNotIn("login", self.pf)
        put_run(self.batch, {**self.c, "login": "subscription"}, [use("u1", "Bash", {"command": "grep -rn x ."})])
        triage.report(self.batch, self.out)
        with open(os.path.join(self.out, "runs.jsonl"), encoding="utf-8") as f:
            ids = [json.loads(line)["id"] for line in f]
        self.assertEqual(sorted([self.pf["id"], self.c["id"], self.stopped["id"]]), ids)
        self.assertEqual(4, len(triage._table_lines(triage.load_batch(self.batch)["runs"])))

    def test_report_has_the_rows_PFN_minus_PF_and_the_arm_order(self):
        put_run(self.batch, run("PFN", sc=score(2, 0, 1), answer=["pkg/a.go:3", "pkg/e.go:2"], cost=0.3))
        put_run(self.batch, run("PS", aid="rule", n=2, sc=score(1, 0, 2), answer=["pkg/a.go:3"]))
        with open(triage.report(self.batch, self.out), encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(["C", "PS-rule", "PF", "PFN"],
                         [line.split(" | ")[2] for line in lines if line.startswith(f"| `{QUESTION}` | {OPUS} |")])
        paired = [line for line in lines if line.startswith(f"| {OPUS} | ")]
        pairs = (("PS-rule", "C"), ("PF", "C"), ("PFN", "C"), ("PFN", "PF"))
        self.assertEqual([[arm, base, cell] for arm, base in pairs for cell in (f"`{QUESTION}`", "all")],
                         [line.split(" | ")[1:4] for line in paired])
        # PFN: f1 0.8 (precision 1, recall 2/3); PF: f1 0.4.
        self.assertTrue(paired[6].startswith(f"| {OPUS} | PFN | PF | `{QUESTION}` | 0.800 | 0.400 | 0.400 |"),
                        paired[6])
        self.assertTrue(any(line.startswith("| model | arm | base | question | f1 arm | f1 base | f1 diff |")
                            for line in lines))
        adoption = [line.split(" | ")[0][2:] for line in lines if line.endswith(" |") and f" | {OPUS} | " in line
                    and line.count(" | ") == 4]
        self.assertEqual(["PS-rule", "PS-rule-stop-5", "PF", "PFN"], adoption)

    def test_old_record_maps_by_old_id(self):
        old = run("PFN", sc=score(1, 1, 2), answer=["pkg/a.go:3", "pkg/c.go:12"], tools=self.pf["tools"])
        del old["question"]
        old.update(id=old["id"].replace(QUESTION, CH["id"]), challenge=CH["id"])
        put_run(self.batch, old, fixture_lines("transcript.jsonl"), fixture_lines("proxy.jsonl"))
        self.assertEqual(QUESTION, next(r for r in triage.load_batch(self.batch)["runs"] if r["id"] == old["id"])
                         ["question"])
        triage.report(self.batch, self.out)
        with open(os.path.join(self.out, "runs.jsonl"), encoding="utf-8") as f:
            row = next(r for r in map(json.loads, f) if r["id"] == old["id"])
        self.assertEqual((QUESTION, ["pkg/c.go:12"], ["pkg/d.go:20"]),
                         (row["question"], row["ide_forbidden_lines"], row["ide_missed_required"]))
        gone = {**old, "id": old["id"].replace(CH["id"], "demo-refs-gone"), "challenge": "demo-refs-gone"}
        put_run(self.batch, gone)
        self.assertEqual("demo-refs-gone", next(r for r in triage.load_batch(self.batch)["runs"]
                                                if r["id"] == gone["id"])["question"])
        with self.assertRaises(ValueError) as e:
            triage.report(self.batch, self.out)
        self.assertIn("'demo-refs-gone'", str(e.exception))

    def test_report_names_the_arms_with_the_base_PF(self):
        with open(triage.report(self.batch, self.out), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("The base is C for each plugin arm, and also PF for PFN, PFR, PFL, PFG, PFI and PFS. ", text)

    def test_report_has_the_flag_repo_access(self):
        slug_run, keys_run = run("PFN", sc=score(1, 0, 3), answer=["pkg/a.go:3"]), run("P", n=2)
        put_run(self.batch, slug_run, [use("u1", "Bash", {"command": "curl -s https://github.com/O/R/tree/main"})])
        put_run(self.batch, keys_run, [use("u1", "WebFetch", {"url": "https://example.com/live-test/bench/keys/"})])
        with mock.patch.object(triage, "repo_slug", return_value="o/r") as slug:
            path = triage.report(self.batch, self.out)
        slug.assert_called_once_with()
        with open(os.path.join(self.out, "runs.jsonl"), encoding="utf-8") as f:
            got = {row["id"]: row["repo_access"] for row in map(json.loads, f)}
        self.assertEqual({slug_run["id"]: True, keys_run["id"]: True, self.pf["id"]: False, self.c["id"]: False,
                          self.stopped["id"]: False}, got)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        ids = ", ".join(f"`{i}`" for i in sorted([slug_run["id"], keys_run["id"]]))
        self.assertIn(f"| repo_access | 2 | {ids} |", text)
        # With no slug (no git repository at the repository root), only the text bench/keys counts.
        triage.report(self.batch, self.out)
        with open(os.path.join(self.out, "runs.jsonl"), encoding="utf-8") as f:
            self.assertEqual([keys_run["id"]], [row["id"] for row in map(json.loads, f) if row["repo_access"]])

    # ------------------------------------------------------------ ledger

    def ledger(self, **statuses):
        counts = {"b1": dict(dict.fromkeys(qfiles.STATUSES, 0), equal=3, **statuses), "other": {"different": 5}}
        with mock.patch.object(qfiles, "rescore", return_value=counts) as rescore:
            path = triage.ledger(self.batch, self.ledger_dir)
        rescore.assert_called_once_with(self.runs, batch="b1")
        with open(path, encoding="utf-8") as f:
            return path, f.read()

    def test_ledger_writes_one_summary_named_by_the_date_of_the_first_run(self):
        before = sorted(os.listdir(self.batch))
        path, text = self.ledger()
        self.assertEqual(["2026-11-17-b1.md"], os.listdir(self.ledger_dir))
        self.assertEqual(os.path.join(self.ledger_dir, "2026-11-17-b1.md"), path)
        self.assertTrue(text.startswith("# Batch `b1`\n"), text[:80])
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        for heading in ("## Batch", "## By question, model and arm", "## Paired differences", "## Adoption",
                        "## Flags", "## Total cost"):
            self.assertIn(heading, headings)
        for line in ("| ok | 2 |", "| total cost (USD) | 0.6234 |",
                     f"| `{QUESTION}` | {OPUS} | PF | 1 | ok 1 | 0.400 |", "| runs of the batch | 3 | 0.6234 |",
                     "| set-aside tries | 1 | 0.1000 |", "| repo_access | 0 | - |"):
            self.assertIn(line, text)
        self.assertIn("The first run of the batch started on 2026-11-17 (UTC).", text)
        self.assertNotIn("scored with an earlier key", text)
        # No absolute path: not the temporary folder, not the root of a tree, no word that starts with a slash.
        for absent in (self.tmp, ROOT, "Batch folder"):
            self.assertNotIn(absent, text)
        self.assertIsNone(re.search(r"(?:^|[\s`(\"'])/\w", text, re.M))
        # Nothing is written below the runs folder.
        self.assertEqual((["b1"], before), (os.listdir(self.runs), sorted(os.listdir(self.batch))))

    def test_ledger_of_a_batch_with_no_plan_and_no_manifest_shows_the_run_records(self):
        _, text = self.ledger()
        self.assertIn("The batch has no stored plan (`plan.json`).", text)
        self.assertIn("The batch has no recorded manifest (`manifest.json`).", text)
        for line in ("| plugin version (demo) | 2.2.0-dev.01, 2.2.0-dev.02 |", "| image (demo) | sha256:aa |",
                     f"| models | {OPUS} |"):
            self.assertIn(line, text)
        # With no set-aside try, the total cost has one line.
        shutil.rmtree(os.path.join(self.batch, run("P")["id"] + ".invalid-1"))
        _, text = self.ledger()
        self.assertIn("| runs of the batch | 3 | 0.6234 |", text)
        self.assertNotIn("set-aside tries", text)

    def test_ledger_shows_the_plan_and_the_recorded_manifest(self):
        plan = {"rule": "each arm of one question", "questions": [QUESTION], "arms": [{"arm": "C"}, {"arm": "PF"}],
                "models": [OPUS], "runs": 1}
        write(os.path.join(self.batch, "plan.json"), json.dumps(plan, indent=2) + "\n")
        build = {"goland": {"version": "2026.3", "build": "263.7307.211"},
                 "pycharm": {"version": "2026.3.0.1", "build": "263.7307.329"},
                 "webstorm": {"version": "2026.3", "build": "263.7307.202"}}
        record = {"ides": build, "agent": {"name": "claude-code", "version": "2.1.326"},
                  "image": {"base": "ubuntu:24.04"}, "models": ["claude-haiku-5-5", OPUS], "machine_ides": build,
                  "repository": {"commit": "0123abc", "dirty": True}, "plugin": {"demo": "2.2.0-dev.07"},
                  "plan_models": [OPUS], "image_ids": {"demo": "sha256:bb"}, "slots_root": "/home/someone/ws",
                  "login": "subscription", "questions": {QUESTION: {"question_sha256": "q" * 64,
                                                                    "key_sha256": "k" * 64}}}
        write(os.path.join(self.batch, "manifest.json"), json.dumps(record, indent=1))
        _, text = self.ledger()
        self.assertIn("```json\n" + json.dumps(plan, indent=2) + "\n```", text)
        manifest_part, records_part = text.split("The values of the run records")
        for line in ("| plugin version (demo) | 2.2.0-dev.07 |",
                     "| agent (pin at the batch start) | claude-code 2.1.326 |",
                     f"| models | {OPUS} |", "| image (demo) | sha256:bb |", "| repository commit | 0123abc (dirty) |",
                     "| login | subscription |", "| IDE goland | 2026.3 (build 263.7307.211) |",
                     "| IDE pycharm | 2026.3.0.1 (build 263.7307.329) |"):
            self.assertIn(line, manifest_part)
        # The run records give the plugin versions and the image ids that the runs had.
        for line in ("| plugin version (demo) | 2.2.0-dev.01, 2.2.0-dev.02 |", "| image (demo) | sha256:aa |",
                     f"| models | {OPUS} |"):
            self.assertIn(line, records_part.split("## ")[0])
        for absent in ("webstorm", "/home/", "someone", "q" * 64, "no stored plan", "no recorded manifest",
                       "claude-haiku-5-5", "ubuntu"):
            self.assertNotIn(absent, text)
        # The agent version of each image record.
        write(os.path.join(self.batch, "manifest.json"), json.dumps(dict(record, claude_versions={"demo": "2.1.400"})))
        _, text = self.ledger()
        self.assertIn("| agent (demo) | claude-code 2.1.400 |", text)
        self.assertNotIn("2.1.326", text)
        # A plugin version for each product (the option -plugin-version), a clean tree, an unknown login and no
        # benchmark IDE on the machine.
        record.update(plugin="2.2.0-dev.08", repository={"commit": "0123abc", "dirty": False},
                      login="unknown (BENCH_LOGIN='/home/someone': use one of api-key, subscription)", machine_ides={})
        write(os.path.join(self.batch, "manifest.json"), json.dumps(record, indent=1))
        _, text = self.ledger()
        for line in ("| plugin version (each product) | 2.2.0-dev.08 |", "| repository commit | 0123abc |",
                     "| login | unknown |", "| IDE goland | - |", "| IDE pycharm | - |"):
            self.assertIn(line, text)
        self.assertNotIn("someone", text)

    def test_ledger_notes_a_score_of_an_earlier_key(self):
        _, text = self.ledger(different=2)
        self.assertIn("Note: 2 runs were scored with an earlier key. ", text)
        # The note comes before the tables.
        self.assertLess(text.index("scored with an earlier key"), text.index("## Batch"))
        _, text = self.ledger(different=1)
        self.assertIn("Note: 1 run was scored with an earlier key. ", text)

    def test_ledger_of_a_batch_with_no_start_time_is_a_value_error(self):
        for rec in (self.pf, self.c, self.stopped):
            write(os.path.join(self.batch, rec["id"], "run.json"), json.dumps(dict(rec, started=None)))
        with mock.patch.object(qfiles, "rescore", return_value={}), self.assertRaises(ValueError) as e:
            triage.ledger(self.batch, self.ledger_dir)
        self.assertIn("no run of the batch has a start time", str(e.exception))
        self.assertFalse(os.path.exists(self.ledger_dir))

    def test_cli_ledger_prints_the_path_and_writes_the_file_again(self):
        self.assertEqual(os.path.join(os.path.dirname(os.path.abspath(triage.__file__)), "ledger"), triage.LEDGER)
        default = os.path.join(self.tmp, "tracked", "ledger")
        expected = os.path.join(default, "2026-11-17-b1.md")

        def cli(*extra):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(0, triage.main(["ledger", "-batch", "b1", *extra]))
            return out.getvalue().strip()

        def cost_line(path):
            with open(path, encoding="utf-8") as f:
                return next(line for line in f if line.startswith("| runs of the batch |"))

        with mock.patch.object(triage, "LEDGER", default), mock.patch.object(qfiles, "rescore", return_value={}):
            self.assertEqual(expected, cli())
            self.assertEqual("| runs of the batch | 3 | 0.6234 |\n", cost_line(expected))
            put_run(self.batch, run("C", n=2, sc=score(3, 0, 0), cost=2.0))
            self.assertEqual(expected, cli())
            self.assertEqual("| runs of the batch | 4 | 2.6234 |\n", cost_line(expected))
            self.assertEqual(["2026-11-17-b1.md"], os.listdir(default))
            self.assertEqual(os.path.join(self.ledger_dir, "2026-11-17-b1.md"), cli("-out", self.ledger_dir))

    def test_table_prints_one_line_for_each_run(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, triage.main(["table", "-batch", "b1"]))
        lines = out.getvalue().splitlines()
        self.assertEqual(4, len(lines))
        self.assertEqual(["question", "arm", "model", "n", "outcome", "tp", "fp", "miss", "exact", "USD", "turns",
                          "seconds", "tools", "IDE"], lines[0].split())
        self.assertEqual([QUESTION, "PF", OPUS, "1", "ok", "1", "1", "2", "False", "0.5000", "3", "40.0", "6", "4"],
                         next(line for line in lines if " PF " in line).split())
        self.assertEqual([QUESTION, "PS-rule-stop-5", OPUS, "1", "stopped", "-", "-", "-", "-", "-", "3", "10.0", "5",
                          "4"], next(line for line in lines if "stop-5" in line).split())

    def test_cli_exit_2_for_a_missing_batch(self):
        for command in ("report", "table", "ledger"):
            with self.subTest(command=command):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()), \
                        mock.patch.object(triage, "LEDGER", self.ledger_dir):
                    self.assertEqual(2, triage.main([command, "-batch", "absent"]))
                self.assertIn(os.path.join(self.runs, "absent"), err.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.runs, "absent.triage")))
        self.assertFalse(os.path.exists(self.ledger_dir))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, triage.main(["report", "-batch", "b1"]))
        self.assertEqual(os.path.join(self.runs, "b1.triage", "summary.md"), out.getvalue().strip())

    def test_cli_exit_2_for_a_record_with_no_question_and_no_challenge(self):
        rec = run("P", n=2)
        del rec["question"]
        path = os.path.join(put_run(self.batch, rec), "run.json")
        for command in ("report", "table"):
            with self.subTest(command=command):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                    self.assertEqual(2, triage.main([command, "-batch", "b1"]))
                self.assertEqual(("", f"triage: ValueError: {path}: the run record has no question and no challenge\n"),
                                 (out.getvalue(), err.getvalue()))


if __name__ == "__main__":
    unittest.main()
