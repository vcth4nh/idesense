"""Unit tests of bench/planfile.py: load, problems, expand, the check command and the tracked plans.

The questions of a plan are the tracked questions (`qfiles.names()`). A test plan file is in a temporary folder.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from bench import planfile, qfiles
from common import trees

HAIKU, OPUS = "claude-haiku-5-5", "claude-opus-5-5"
SAMPLE = {"rule": "The first question.", "questions": ["caddy-impls-validator"],
          "arms": [{"arm": "C"}, {"arm": "PF"}], "models": [HAIKU], "runs": 1}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class ExpandTest(unittest.TestCase):
    def test_expand_of_the_sample_gives_two_lines(self):
        self.assertEqual([{"question": "caddy-impls-validator", "arm": "C", "model": HAIKU, "n": 1},
                          {"question": "caddy-impls-validator", "arm": "PF", "model": HAIKU, "n": 1}],
                         planfile.expand(SAMPLE))

    def test_expand_gives_question_model_arm_and_n_in_this_order(self):
        plan = dict(SAMPLE, questions=["q1", "q2"], models=[HAIKU, OPUS], runs=2,
                    arms=[{"arm": "C"}, {"arm": "PS", "aid": "skill", "variant": "guide"}])
        lines = planfile.expand(plan)
        order = [(q, m, a, n) for q in ("q1", "q2") for m in (HAIKU, OPUS) for a in ("C", "PS") for n in (1, 2)]
        self.assertEqual(order, [(line["question"], line["model"], line["arm"], line["n"]) for line in lines])
        self.assertEqual({"question": "q1", "arm": "PS", "model": HAIKU, "n": 1, "aid": "skill", "variant": "guide"},
                         lines[2])
        self.assertEqual(["question", "arm", "model", "n", "aid", "variant"], list(lines[2]))


class ProblemsTest(unittest.TestCase):
    def test_sample_has_no_problem(self):
        self.assertIn("caddy-impls-validator", qfiles.names())
        self.assertEqual([], planfile.problems(SAMPLE))
        self.assertEqual([], planfile.problems(dict(SAMPLE, arms=[{"arm": "PS", "aid": "rule", "variant": "guide"}])))

    def test_problems_reports_each_bad_case(self):
        cases = [
            ("an unknown question", dict(SAMPLE, questions=["caddy-impls-validator", "caddy-impls-gone"]),
             "questions: unknown question 'caddy-impls-gone'"),
            ("an unknown arm", dict(SAMPLE, arms=[{"arm": "C"}, {"arm": "X"}]), "arms: unknown arm 'X'"),
            ("runs 0", dict(SAMPLE, runs=0), "runs 0: use a whole number of 1 or more"),
            ("runs -1", dict(SAMPLE, runs=-1), "runs -1: use a whole number of 1 or more"),
            ("runs as text", dict(SAMPLE, runs="1"), "runs '1': use a whole number of 1 or more"),
            ("runs true", dict(SAMPLE, runs=True), "runs True: use a whole number of 1 or more"),
            ("no model", dict(SAMPLE, models=[]), "models: no list of one or more model names"),
            ("a model that is no text", dict(SAMPLE, models=[HAIKU, ""]), "models: '' is no model name"),
            ("a model that no run id can hold", dict(SAMPLE, models=["claude opus/5"]),
             "models: 'claude opus/5' is no model name: use only the characters A-Z a-z 0-9 . _ - (first: a letter "
             "or digit)"),
            ("an unknown key", dict(SAMPLE, note="x"), "unknown key 'note'"),
            ("a missing key", {k: v for k, v in SAMPLE.items() if k != "runs"}, "no key 'runs'"),
            ("no rule", dict(SAMPLE, rule=" "), "rule: no sentence"),
            ("no question", dict(SAMPLE, questions=[]), "questions: no list of one or more question names"),
            ("questions no list", dict(SAMPLE, questions="caddy-impls-validator"),
             "questions: no list of one or more question names"),
            ("a question two times", dict(SAMPLE, questions=["caddy-impls-validator"] * 2),
             "questions: 'caddy-impls-validator' is two times in the list"),
            ("an arm entry two times", dict(SAMPLE, arms=[{"arm": "C"}, {"arm": "C"}]),
             "arms: {'arm': 'C'} is two times in the list"),
            ("an arm entry with no arm", dict(SAMPLE, arms=[{"aid": "skill"}]),
             "arms: {'aid': 'skill'} is no object with the key arm"),
            ("an arm entry with another key", dict(SAMPLE, arms=[{"arm": "C", "dry-run": True}]),
             "arms: unknown key 'dry-run' in {'arm': 'C', 'dry-run': True}"),
            ("an unknown aid", dict(SAMPLE, arms=[{"arm": "PS", "aid": "book"}]), "arms: unknown aid 'book'"),
            ("an unknown variant", dict(SAMPLE, arms=[{"arm": "P", "variant": "x"}]), "arms: unknown variant 'x'"),
            ("arm PS with no aid", dict(SAMPLE, arms=[{"arm": "C"}, {"arm": "PS"}]),
             "arms: {'arm': 'PS'}: arm PS needs -aid skill or -aid rule"),
            ("an aid on another arm", dict(SAMPLE, arms=[{"arm": "P", "aid": "skill"}]),
             "arms: {'arm': 'P', 'aid': 'skill'}: -aid is for arm PS only, not for arm P"),
            ("a variant on an arm that takes none", dict(SAMPLE, arms=[{"arm": "PFN", "variant": "guide"}]),
             "arms: {'arm': 'PFN', 'variant': 'guide'}: -variant is for the arms P, PS and PF, not for arm PFN"),
            ("a variant on arm C", dict(SAMPLE, arms=[{"arm": "C", "variant": "instructions"}]),
             "arms: {'arm': 'C', 'variant': 'instructions'}: -variant is for the arms P, PS and PF, not for arm C"),
            ("no object", ["caddy-impls-validator"], "the plan is no JSON object"),
        ]
        for what, plan, problem in cases:
            with self.subTest(what):
                self.assertEqual([problem], planfile.problems(plan))


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="planfile-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        patcher = mock.patch.object(planfile, "PLANS", os.path.join(self.tmp, "plans"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_name_is_a_file_of_the_plan_folder_and_a_path_is_a_path(self):
        write(os.path.join(planfile.PLANS, "mini.json"), json.dumps(SAMPLE))
        other = os.path.join(self.tmp, "other.json")
        write(other, json.dumps(dict(SAMPLE, runs=2)))
        self.assertEqual(SAMPLE, planfile.load("mini"))
        self.assertEqual(2, planfile.load(other)["runs"])
        with self.assertRaises(FileNotFoundError):
            planfile.load("other")

    def test_check_prints_the_run_counts_and_the_problems(self):
        write(os.path.join(planfile.PLANS, "mini.json"), json.dumps(SAMPLE))
        write(os.path.join(planfile.PLANS, "bad.json"), json.dumps(dict(SAMPLE, runs=0, note="x")))
        write(os.path.join(planfile.PLANS, "broken.json"), "{not json")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, planfile.main(["check", "mini"]))
        self.assertEqual("mini: 2 runs\n0 problems\n", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(1, planfile.main(["check", "mini", "bad", "broken", "absent"]))
        lines = out.getvalue().splitlines()
        self.assertEqual(["mini: 2 runs", "bad: unknown key 'note'", "bad: runs 0: use a whole number of 1 or more"],
                         lines[:3])
        self.assertTrue(lines[3].startswith("broken: no plan (JSONDecodeError: "), lines[3])
        self.assertTrue(lines[4].startswith("absent: no plan (FileNotFoundError: "), lines[4])
        self.assertEqual("4 problems", lines[5])
        self.assertEqual(6, len(lines))

    def test_check_refuses_a_bad_combination_of_arm_options(self):
        write(os.path.join(planfile.PLANS, "ps.json"), json.dumps(dict(SAMPLE, arms=[{"arm": "C"}, {"arm": "PS"}])))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(1, planfile.main(["check", "ps"]))
        self.assertEqual("ps: arms: {'arm': 'PS'}: arm PS needs -aid skill or -aid rule\n1 problem\n", out.getvalue())


class TrackedPlansTest(unittest.TestCase):
    """The plans of bench/plans/: their fields, their format and their rules."""

    def plan(self, name):
        return planfile.load(name)

    def test_each_tracked_plan_has_no_problem_and_only_the_fields_of_a_plan(self):
        self.assertEqual(["dev.json", "release.json", "smoke.json"], sorted(os.listdir(planfile.PLANS)))
        for name in ("smoke", "dev", "release"):
            plan = self.plan(name)
            self.assertEqual([], planfile.problems(plan), name)
            self.assertEqual(list(planfile.FIELDS), list(plan), name)
            with open(os.path.join(planfile.PLANS, name + ".json"), encoding="utf-8") as f:
                self.assertEqual(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", f.read(), name)
            for word in (os.path.expanduser("~"), trees.BENCH, os.path.basename(trees.BENCH)):
                self.assertNotIn(word, plan["rule"], name)

    def test_smoke_has_the_first_question_of_two_kinds(self):
        keys = {name: qfiles.load_key(name) for name in qfiles.names()}
        first = lambda **want: next(n for n in sorted(keys) if all(keys[n][k] == v for k, v in want.items()))
        smoke = self.plan("smoke")
        self.assertEqual([first(product="caddy", family="impls"), first(product="beets", family="refs", tree="beets")],
                         smoke["questions"])
        self.assertEqual(([{"arm": "C"}, {"arm": "PF"}], [HAIKU], 1), (smoke["arms"], smoke["models"], smoke["runs"]))
        self.assertEqual(4, len(planfile.expand(smoke)))

    def test_dev_has_at_most_12_questions_with_two_arms_and_both_models(self):
        dev = self.plan("dev")
        self.assertLessEqual(len(dev["questions"]), 12)
        self.assertEqual(([{"arm": "C"}, {"arm": "PF"}], [HAIKU, OPUS], 1), (dev["arms"], dev["models"], dev["runs"]))
        self.assertLessEqual(len(planfile.expand(dev)), 48)

    def test_release_has_each_question_three_arms_both_models_and_three_runs(self):
        release = self.plan("release")
        self.assertEqual(qfiles.names(), release["questions"])
        self.assertEqual(([{"arm": "C"}, {"arm": "P"}, {"arm": "PF"}], [HAIKU, OPUS], 3),
                         (release["arms"], release["models"], release["runs"]))
        self.assertEqual(len(qfiles.names()) * 3 * 2 * 3, len(planfile.expand(release)))


if __name__ == "__main__":
    unittest.main()
