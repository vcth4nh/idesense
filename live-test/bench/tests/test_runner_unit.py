"""Unit tests of bench/runner.py with a fake `docker` on PATH.

The fake `docker` writes its arguments and the value of ANTHROPIC_API_KEY in its environment to a log file, prints a
stream-json fixture of tests/fixtures/stream/, and exits. For a route URL in its arguments it reads the route file and
writes four lines to the proxy log of the route, as the proxy would. No test starts a container, calls an IDE or the
proxy, or reads the real key file: the paths of the runner, the data root of the lock and the secret file point into
a temporary folder, `check_ide`, `ide_version` and `proxy_healthy` are fakes, and the key is a fake value.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from bench import planfile, proxy, qfiles, runner
from bench import sets as challenges
from common import lock, mcp, settings, trees

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "stream")
ROOT = "/srv/ws/0000/beets"  # the slot path of the tree in the stream fixtures
VERSION = "2.1.1-bench.f4ff0a2"  # the plugin version of the fake IDE
MACHINE_LEAK_WORDS = runner.LEAK_WORDS  # the words of this machine; each test has the words of a sample machine
LEAK_WORDS = ("idesense-bench", "-plant-", "BENCH_", "/srv/repo/")
SERVER = "pycharm-idesense"
FAKE_KEY = "sk-fake-0123456789abcdef-test-only"
MODEL = "claude-opus-5-5"
CHALLENGE = {"id": "beets-refs-helper", "product": "beets", "tree": "beets", "family": "refs",
             "keys": "beets/test.jsonl", "key_id": "py:demo.helper", "sample": "hard", "note": "test"}
RECORD = {"id": "py:demo.helper", "lang": "python", "kind": "function", "name": "helper", "container": "",
          "decl": {"file": "beets/util.py", "line": 5, "col": 5}, "implementers": [], "source": "scan",
          "sites": [{"file": "beets/a.py", "line": 10, "col": 3, "class": "required", "why": "use"},
                    {"file": "beets/b.py", "line": 4, "col": 1, "class": "required", "why": "use"},
                    {"file": "beets/b.py", "line": 9, "col": 1, "class": "forbidden", "why": "comment"}]}
# The tracked key of CHALLENGE (bench.qfiles); the question file is the prompt of CHALLENGE with `{root}`.
KEY = {"question": CHALLENGE["id"], "old_ids": [CHALLENGE["id"]], "product": "beets", "pin": "v0", "tree": "beets",
       "family": "refs", "lang": "python", "symbol": RECORD["id"], "name": "helper",
       "answer": challenges.answer(CHALLENGE, RECORD), "pick": {"sample": "hard", "rule": "test"},
       "key_file": "beets/test.jsonl", "source": "test"}
MANIFEST = "".join(f"{'0' * 64}  {p}\n" for p in ("beets/a.py", "beets/b.py", "beets/util.py"))
IMAGE = {"image": "idesense-bench-beets:p2", "id": "sha256:feed", "server_name": SERVER,
         "slots": {"beets": {"slot": "0000", "path": ROOT}}}
ROUTE_URL = r"http://172\.17\.0\.1:29380/r/[0-9a-f]{32}/mcp"
INIT_SERVERS = '"mcp_servers":[{"name":"pycharm-idesense","status":"connected"}]'  # the init event of ok.jsonl
# The container flags of the plan (Global Constraints), as text: the test does not trust the constant of the runner.
FLAGS = ("--rm --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges --memory 6g --cpus 4 "
         "--pids-limit 1024 --network bridge").split()

FAKE_DOCKER = r'''#!{python}
import json, os, re, sys, time
args = sys.argv[1:]
log = os.environ["FAKE_DOCKER_LOG"]
with open(log, "a") as f:
    f.write(json.dumps({"argv": args, "key": os.environ.get("ANTHROPIC_API_KEY")}) + "\n")
if not args or args[0] != "run":
    sys.exit(0)
tokens = [m for a in args for m in re.findall(r"/r/([0-9a-f]{32})/mcp", a)]
if tokens:
    with open(os.environ["FAKE_ROUTES"]) as f:
        entry = json.load(f).get(tokens[0])
    with open(log, "a") as f:
        f.write(json.dumps({"route": entry}) + "\n")
    if entry:
        version = os.environ.get("FAKE_DOCKER_PROXY_VERSION", "{version}")
        status = int(os.environ.get("FAKE_DOCKER_PROXY_STATUS", "200"))
        with open(os.path.join(os.environ["FAKE_PROXY_LOG_DIR"], entry["run"] + ".jsonl"), "a") as f:
            f.write(json.dumps({"method": "initialize", "status": 200, "server_version": version}) + "\n")
            for method in ("tools/list", "tools/call", "tools/call"):
                f.write(json.dumps({"method": method, "status": status}) + "\n")
fixture = os.environ.get("FAKE_DOCKER_FIXTURE")
if fixture:
    with open(fixture, "rb") as f:
        for line in f:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
            time.sleep(float(os.environ.get("FAKE_DOCKER_DELAY", "0")))
extra = os.environ.get("FAKE_DOCKER_EXTRA")
if extra:
    sys.stdout.write(extra + "\n")
if os.environ.get("FAKE_DOCKER_PRINT_KEY"):
    sys.stdout.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_x",
         "content": "ANTHROPIC_API_KEY=" + os.environ.get("ANTHROPIC_API_KEY", "")}]}}) + "\n")
sys.stdout.flush()
sys.stderr.write("fake docker\n")
time.sleep(float(os.environ.get("FAKE_DOCKER_SLEEP", "0")))
sys.exit(int(os.environ.get("FAKE_DOCKER_EXIT", "0")))
'''


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_tracked(tmp, ch, record, key):
    """The tracked question file and key file of a challenge, in `<tmp>/tracked/`."""
    write(os.path.join(tmp, "tracked", "questions", key["question"] + ".md"),
          challenges.prompt(ch, record, "{root}") + "\n")
    write(os.path.join(tmp, "tracked", "keys", key["question"] + ".json"), json.dumps(key, indent=2) + "\n")


class RunnerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="runner-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        t = lambda *p: os.path.join(self.tmp, *p)
        write_tracked(self.tmp, CHALLENGE, RECORD, KEY)  # no key record file: the runner reads the tracked files
        write(t("trees", "beets.manifest"), MANIFEST)
        write(t("slots.json"), json.dumps({"beets": {"slot": "0000", "path": ROOT, "product": "beets"}}))
        write(t("images", "beets.json"), json.dumps(IMAGE))
        write(t("key"), FAKE_KEY + "\n")
        os.makedirs(t("proxy", "log"))
        self.routes, self.log_dir, self.docker_log = t("proxy", "routes.json"), t("proxy", "log"), t("docker.log")
        write(t("bin", "docker"), FAKE_DOCKER.replace("{python}", sys.executable)
              .replace("{version}", VERSION))
        os.chmod(t("bin", "docker"), stat.S_IRWXU)
        self.runs = t("runs")
        self.ide = []
        for name, value in (("RUNS", self.runs), ("IMAGES", t("images")), ("ROUTES_FILE", self.routes),
                            ("PROXY_LOG_DIR", self.log_dir), ("SLOTS_FILE", t("slots.json")),
                            ("ADDITIONS_FILE", t("additions.json")), ("check_ide", self.fake_ide),
                            ("ide_version", self.fake_version), ("proxy_healthy", lambda *a, **k: True),
                            ("LEAK_WORDS", LEAK_WORDS)):
            p = mock.patch.object(runner, name, value)
            p.start()
            self.addCleanup(p.stop)
        for module, name, value in ((challenges, "KEYS", t("keys")), (challenges, "TREES", t("trees")),
                                    (trees, "TREES", t("trees")), (qfiles, "QUESTIONS", t("tracked", "questions")),
                                    (qfiles, "KEYS", t("tracked", "keys"))):
            p = mock.patch.object(module, name, value)
            p.start()
            self.addCleanup(p.stop)
        env = mock.patch.dict(os.environ, {"PATH": t("bin") + os.pathsep + os.environ.get("PATH", ""),
                                           "FAKE_DOCKER_LOG": self.docker_log, "FAKE_ROUTES": self.routes,
                                           "FAKE_PROXY_LOG_DIR": self.log_dir, "BENCH_ROOT": self.tmp,
                                           "BENCH_SECRET_FILE": t("key")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def fake_ide(self, url, root, timeout):
        self.assertEqual(ROOT, root)
        self.assertEqual(runner.IDE_URLS["beets"], url)
        return self.ide.pop(0) if self.ide else (VERSION, None)

    def fake_version(self, url):
        self.assertEqual(runner.IDE_URLS["beets"], url)
        return VERSION

    def main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runner.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def run_args(self, arm, *extra):
        return ["run", "-question", KEY["question"], "-arm", arm, "-model", MODEL, "-batch", "b1", *extra]

    def start(self, arm, *extra, fixture="ok.jsonl", **fake):
        """One run with the fake docker; the exit code, the run.json record, stdout and stderr."""
        os.environ["FAKE_DOCKER_FIXTURE"] = os.path.join(FIXTURES, fixture) if fixture else ""
        for name, value in fake.items():
            os.environ["FAKE_DOCKER_" + name.upper()] = str(value)
        code, out, err = self.main(*self.run_args(arm, *extra))
        run_id = runner.run_id_of(runner._parser().parse_args(self.run_args(arm, *extra)))
        path = os.path.join(self.runs, "b1", run_id, "run.json")
        rec = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        return code, rec, out, err

    def fixture_with(self, name, old, new, drop_first=False):
        """A copy of a fixture in the temporary folder with `old` replaced by `new` (and with no first line)."""
        with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
            lines = f.readlines()
        text = "".join(lines[1:] if drop_first else lines)
        self.assertEqual(1 if old else 0, text.count(old) if old else 0, old)
        path = os.path.join(self.tmp, f"fixture-{len(os.listdir(self.tmp))}.jsonl")
        write(path, text.replace(old, new) if old else text)
        return path

    def c_ok(self):
        """ok.jsonl with no MCP server in its init event (the form of arm C)."""
        return self.fixture_with("ok.jsonl", INIT_SERVERS, '"mcp_servers":[]')

    def dry(self, arm, *extra):
        code, out, err = self.main(*self.run_args(arm, *extra), "-dry-run")
        self.assertEqual(0, code, err)
        return json.loads(out)

    def docker_calls(self):
        if not os.path.exists(self.docker_log):
            return []
        with open(self.docker_log, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def runs_of_docker(self):
        return [c for c in self.docker_calls() if "argv" in c and c["argv"][0] == "run"]

    def folder(self, arm_part):
        return os.path.join(self.runs, "b1", f"{CHALLENGE['id']}__{arm_part}__{MODEL}__1")

    def routes_now(self):
        return proxy.read_routes(self.routes)


def claude_args(cmd):
    return cmd[cmd.index(IMAGE["id"]) + 1:]


def prompt_of(cmd):
    args = claude_args(cmd)
    return args[args.index("-p") + 1]


def env_values(cmd):
    return [cmd[i + 1] for i, a in enumerate(cmd[:cmd.index(IMAGE["id"])]) if a == "-e"]


class CommandTest(RunnerCase):
    def test_arm_C_has_no_mcp_config(self):
        cmd = self.dry("C")
        self.assertNotIn("--mcp-config", cmd)
        self.assertIn("--strict-mcp-config", cmd)
        self.assertNotIn("172.17.0.1", json.dumps(cmd))
        self.assertNotIn("--tools", cmd)
        self.assertEqual(["--tools", ""], self.dry("C", "-no-tools")[-2:])

    def test_arm_P_has_mcp_config_with_route_url(self):
        for arm, extra in (("P", ()), ("PS", ("-aid", "rule")), ("PF", ()), ("PFN", ())):
            cmd = self.dry(arm, *extra)
            self.assertEqual("--mcp-config", cmd[-2], arm)
            config = json.loads(cmd[-1])
            self.assertEqual([SERVER], list(config["mcpServers"]), arm)
            server = config["mcpServers"][SERVER]
            self.assertEqual("http", server["type"])
            self.assertRegex(server["url"], "^" + ROUTE_URL + "$")
        self.assertEqual({}, self.routes_now(), "a dry run adds no route")
        # A real run: the route of the token exists while the container runs, with the slot path as its project.
        code, rec, _, err = self.start("P", "-variant", "instructions")
        self.assertEqual(0, code, err)
        route = [c["route"] for c in self.docker_calls() if "route" in c]
        self.assertEqual(1, len(route))
        self.assertEqual(ROOT, route[0]["project"])
        self.assertEqual(runner.IDE_URLS["beets"], route[0]["upstream"])
        self.assertTrue(route[0]["run"].startswith(rec["id"] + "."), route[0]["run"])
        self.assertEqual(runner.INSTRUCTIONS, route[0]["instructions"])

    def test_arm_PF_prompt_has_the_sentence_and_others_do_not(self):
        sentence = runner.PF_SENTENCE.format(server=SERVER)
        base = challenges.prompt(CHALLENGE, RECORD, ROOT)
        for arm, extra in (("C", ()), ("P", ()), ("PS", ("-aid", "skill")), ("PF", ()), ("PFN", ())):
            text = prompt_of(self.dry(arm, *extra))
            if arm in ("PF", "PFN"):
                paragraphs = text.split("\n\n")
                self.assertEqual(sentence, paragraphs[-2])
                self.assertEqual(challenges.TAIL, paragraphs[-1])
                self.assertEqual(base, text.replace("\n\n" + sentence, ""))
            else:
                self.assertEqual(base, text, arm)
                self.assertNotIn("MCP", text, arm)
                self.assertNotIn(SERVER, text, arm)

    def test_PS_sets_bench_aid(self):
        self.assertIn("BENCH_AID=skill", env_values(self.dry("PS", "-aid", "skill")))
        self.assertIn("BENCH_AID=rule", env_values(self.dry("PS", "-aid", "rule")))
        for arm in ("C", "P", "PF"):
            self.assertIn("BENCH_AID=none", env_values(self.dry(arm)), arm)
        code, _, err = self.main(*self.run_args("PS"), "-dry-run")
        self.assertEqual(2, code)
        self.assertIn("-aid", err)

    def test_docker_command_has_the_container_flags_and_no_mount(self):
        for arm, extra in (("C", ()), ("C", ("-no-tools",)), ("P", ("-variant", "no-tool-search")),
                           ("PS", ("-aid", "skill")), ("PF", ()), ("PFN", ())):
            cmd = self.dry(arm, *extra)
            self.assertEqual(["docker", "run"], cmd[:2])
            flags = cmd[:cmd.index(IMAGE["id"])]
            self.assertEqual(FLAGS, flags[2:2 + len(FLAGS)])
            for bad in ("-v", "--volume", "--mount", "--privileged", "--network=host", "--net=host", "--net"):
                self.assertNotIn(bad, flags, (arm, bad))
            self.assertNotIn("host", [flags[i + 1] for i, a in enumerate(flags) if a == "--network"])
            self.assertNotIn("docker.sock", json.dumps(cmd))
            self.assertNotIn("CLAUDE_CONFIG_DIR", json.dumps(cmd))
            values = env_values(cmd)
            self.assertIn("ANTHROPIC_API_KEY", values)
            self.assertIn("BENCH_SLOT=0000", values)
            self.assertEqual("--name", flags[2 + len(FLAGS)])
            self.assertEqual(arm == "P", "ENABLE_TOOL_SEARCH=false" in values)
            self.assertEqual(runner.claude_flags(prompt_of(cmd), MODEL, challenges.schema(CHALLENGE)),
                             claude_args(cmd)[:len(runner.claude_flags("", MODEL, {}))])

    def test_arm_options_are_checked(self):
        for arm, extra, word in (("C", ("-aid", "skill"), "-aid"), ("P", ("-no-tools",), "-no-tools"),
                                 ("C", ("-variant", "instructions"), "-variant"), ("C", ("-n", "0"), "-n"),
                                 ("C", ("-stop-after-tools", "0"), "-stop-after-tools"),
                                 ("PFN", ("-aid", "skill"), "-aid"), ("PFN", ("-variant", "instructions"), "-variant"),
                                 ("PFN", ("-variant", "no-tool-search"), "-variant"),
                                 ("PFN", ("-no-tools",), "-no-tools"),
                                 *((arm, extra, extra[0]) for arm in ("PFR", "PFL", "PFG", "PFI", "PFS")
                                   for extra in (("-aid", "skill"), ("-variant", "instructions"),
                                                 ("-variant", "no-tool-search"), ("-no-tools",)))):
            code, _, err = self.main(*self.run_args(arm, *extra), "-dry-run")
            self.assertEqual(2, code, (arm, extra))
            self.assertIn(word, err)
        code, _, err = self.main("run", "-question", KEY["question"], "-arm", "C", "-model", "claude opus", "-batch",
                                 "b1", "-dry-run")
        self.assertEqual(2, code)

    def test_question_must_be_a_name(self):
        upper = {**KEY, "question": "Beets-refs-helper"}
        write_tracked(self.tmp, CHALLENGE, RECORD, upper)  # a pair of files that a run could read
        read = mock.Mock(side_effect=AssertionError("a file read"))
        with mock.patch.object(qfiles, "load_key", read), mock.patch.object(qfiles, "load_question", read):
            for name in ("Beets-refs-helper", "../beets-refs-helper", "x/../beets-refs-helper", "..", "a/b"):
                code, out, err = self.main("run", "-question", name, "-arm", "C", "-model", MODEL, "-batch", "b1",
                                           "-dry-run")
                self.assertEqual((2, ""), (code, out), name)
                self.assertIn(f"SetupError: -question {name!r}: ", err)
        self.assertEqual(([], []), (read.call_args_list, self.docker_calls()))

    def test_digests_are_of_the_two_tracked_files(self):
        run = runner.prepare(runner._parser().parse_args(self.run_args("C")))
        for field, path in (("question_sha256", qfiles.question_path(KEY["question"], qfiles.QUESTIONS)),
                            ("key_sha256", qfiles.key_path(KEY["question"], qfiles.KEYS))):
            with open(path, "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), run[field], field)

    def test_run_id_has_the_probe_options(self):
        args = runner._parser().parse_args(self.run_args("C", "-no-tools", "-n", "3"))
        self.assertTrue(args.no_tools)
        self.assertEqual(f"{CHALLENGE['id']}__C-no-tools__{MODEL}__3", runner.run_id_of(args))
        args = runner._parser().parse_args(self.run_args("PS", "-aid", "skill", "-variant", "instructions",
                                                         "-stop-after-tools", "5"))
        self.assertEqual(f"{CHALLENGE['id']}__PS-skill-instructions-stop-5__{MODEL}__1", runner.run_id_of(args))

    def test_image_without_slots_refuses_run_but_dry_run_prints(self):
        write(os.path.join(runner.IMAGES, "beets.json"), json.dumps({k: v for k, v in IMAGE.items() if k != "slots"}))
        code, out, err = self.main(*self.run_args("C"), "-dry-run")
        self.assertEqual(0, code)
        self.assertEqual("docker", json.loads(out)[0])
        self.assertIn("slots", err)
        code, rec, _, err = self.start("C")
        self.assertEqual(2, code)
        self.assertIn("slots", err)
        self.assertEqual([], self.docker_calls())


class CaddyCase(RunnerCase):
    """A RunnerCase that also makes the run options of a caddy challenge."""
    GO_ROOT = "/srv/ws/0001/caddy"
    GO_SERVER = "goland-idesense"
    GO_CHALLENGE = {"id": "caddy-refs-Helper", "product": "caddy", "tree": "caddy", "family": "refs",
                    "keys": "caddy/test.jsonl", "key_id": "go:example.com/demo.Helper", "sample": "hard",
                    "note": "test"}
    GO_RECORD = {"id": "go:example.com/demo.Helper", "lang": "go", "kind": "func", "name": "Helper", "container": "",
                 "decl": {"file": "demo/helper.go", "line": 3, "col": 6}, "implementers": [], "source": "go/types",
                 "sites": [{"file": "demo/use.go", "line": 7, "col": 2, "class": "required", "why": "use"}]}
    GO_KEY = {**KEY, "question": "caddy-refs-helper", "old_ids": [GO_CHALLENGE["id"]], "product": "caddy",
              "tree": "caddy", "lang": "go", "symbol": GO_RECORD["id"], "name": "Helper",
              "answer": challenges.answer(GO_CHALLENGE, GO_RECORD), "key_file": "caddy/test.jsonl"}

    def caddy_args(self, arm):
        """The run options of a caddy challenge (a Go key record, a slot and an image of caddy)."""
        t = lambda *p: os.path.join(self.tmp, *p)
        write(t("trees", "caddy", "demo", "helper.go"), "package demo\n")
        write_tracked(self.tmp, self.GO_CHALLENGE, self.GO_RECORD, self.GO_KEY)
        write(t("slots.json"), json.dumps({"beets": {"slot": "0000", "path": ROOT, "product": "beets"},
                                           "caddy": {"slot": "0001", "path": self.GO_ROOT, "product": "caddy"}}))
        write(t("images", "caddy.json"), json.dumps({"image": "idesense-bench-caddy:p2", "id": "sha256:cafe",
                                                     "server_name": self.GO_SERVER,
                                                     "slots": {"caddy": {"slot": "0001", "path": self.GO_ROOT}}}))
        return runner._parser().parse_args(["run", "-question", self.GO_KEY["question"], "-arm", arm, "-model", MODEL,
                                            "-batch", "b1"])


class PfnTest(CaddyCase):
    """Arm PFN: the prompt of arm PF, and a route with the notes of the product language (runner.NOTES_FILE)."""
    PY_TOOLS = ["ide_find_implementations", "ide_find_usages", "ide_type_hierarchy"]

    def notes(self, lang):
        with open(runner.NOTES_FILE, encoding="utf-8") as f:
            return json.load(f)[lang]

    def test_notes_file_has_a_note_for_each_tool_of_the_plan(self):
        with open(runner.NOTES_FILE, encoding="utf-8") as f:
            notes = json.load(f)
        self.assertEqual(["go", "python"], sorted(notes))
        self.assertEqual(self.PY_TOOLS, sorted(notes["python"]))
        self.assertEqual(["ide_find_usages"], sorted(notes["go"]))
        for lang, texts in notes.items():
            for tool, text in texts.items():
                self.assertIn(tool, proxy.PERMITTED_TOOLS)
                self.assertTrue(text.startswith("This list can be incomplete: "), (lang, tool))

    def test_PFN_has_the_PF_prompt_and_the_notes_of_the_product_language(self):
        beets = runner.prepare(runner._parser().parse_args(self.run_args("PFN")))
        caddy = runner.prepare(self.caddy_args("PFN"))
        self.assertEqual((self.notes("python"), self.notes("go")), (beets["notes"], caddy["notes"]))
        for run, server in ((beets, SERVER), (caddy, self.GO_SERVER)):
            text = run["cmd"][run["cmd"].index("-p") + 1]
            self.assertEqual(runner.PF_SENTENCE.format(server=server), text.split("\n\n")[-2])
            self.assertEqual(challenges.TAIL, text.split("\n\n")[-1])
        pf = runner.prepare(self.caddy_args("PF"))
        self.assertIsNone(pf["notes"])
        self.assertEqual(caddy["cmd"][caddy["cmd"].index("-p") + 1], pf["cmd"][pf["cmd"].index("-p") + 1])

    def test_PFN_route_has_the_notes_and_PF_route_has_none(self):
        code, rec, _, err = self.start("PFN")
        self.assertEqual((0, "ok", "PFN"), (code, rec["outcome"], rec["arm"]), err)
        self.assertEqual(f"{CHALLENGE['id']}__PFN__{MODEL}__1", rec["id"])
        self.assertTrue(os.path.isdir(self.folder("PFN")))
        sentence = runner.PF_SENTENCE.format(server=SERVER)
        self.assertEqual(sentence, prompt_of(self.runs_of_docker()[0]["argv"]).split("\n\n")[-2])
        code, rec, _, err = self.start("PF")
        self.assertEqual((0, "ok"), (code, rec["outcome"]), err)
        routes = [c["route"] for c in self.docker_calls() if "route" in c]
        self.assertEqual(2, len(routes))
        self.assertEqual(self.notes("python"), routes[0]["notes"])
        self.assertIsNone(routes[1].get("notes"))
        self.assertEqual({}, self.routes_now())

    def test_dry_run_prints_the_arm(self):
        code, out, err = self.main(*self.run_args("PFN"), "-dry-run")
        self.assertEqual(0, code, err)
        self.assertIn(f"runner: dry run {CHALLENGE['id']}__PFN__{MODEL}__1: arm PFN; route notes (python): "
                      + ", ".join(self.PY_TOOLS) + "\n", err)
        self.assertEqual(runner.PF_SENTENCE.format(server=SERVER), prompt_of(json.loads(out)).split("\n\n")[-2])
        code, out, err = self.main(*self.run_args("PF"), "-dry-run")
        self.assertEqual(0, code, err)
        self.assertIn(f"runner: dry run {CHALLENGE['id']}__PF__{MODEL}__1: arm PF\n", err)
        self.assertNotIn("route notes", err)
        self.assertEqual(({}, []), (self.routes_now(), self.docker_calls()))

    def test_PFN_with_no_notes_of_the_language_starts_nothing(self):
        path, go = os.path.join(self.tmp, "notes.json"), self.notes("go")
        with mock.patch.object(runner, "NOTES_FILE", path):
            code, _, err = self.main(*self.run_args("PFN"), "-dry-run")
            self.assertEqual(2, code)
            self.assertIn(path, err)
            write(path, json.dumps({"go": go}))
            code, _, _, err = self.start("PFN")
            self.assertEqual(2, code)
            self.assertIn("python", err)
            self.assertEqual([], self.docker_calls())
            self.assertEqual(0, self.main(*self.run_args("PF"), "-dry-run")[0], "only arm PFN reads the note file")


class AdditionsTest(RunnerCase):
    """Arms PFR and PFL: the prompt of arm PF, and a route with the additions of runner.ADDITIONS_FILE for the
    question."""
    ROWS = [{"file": "beets/a.py", "line": 12, "column": 9, "preview": "item.label", "usageType": "REFERENCE",
             "enclosingScope": ["a", "run"]},
            {"file": "beets/b.py", "line": 3, "column": 5, "preview": "obj.label", "usageType": "REFERENCE",
             "enclosingScope": ["b"]}]
    KNOWN = [["beets/util.py", 5], ["beets/a.py", 10]]

    def setUp(self):
        super().setUp()
        self.item = {"name": "label", "known": self.KNOWN, "rows": self.ROWS}
        write(runner.ADDITIONS_FILE, json.dumps({CHALLENGE["id"]: self.item, "other-challenge": {"name": "x"}}))

    def test_arm_with_no_form_has_no_additions_and_reads_no_file(self):
        os.unlink(runner.ADDITIONS_FILE)
        for arm in ("C", "P", "PS", "PF", "PFN"):
            self.assertIsNone(runner.route_additions(KEY, arm), arm)

    def test_PFR_rows_have_match_DYNAMIC(self):
        got = runner.route_additions(KEY, "PFR")
        self.assertEqual(["ide_find_usages"], list(got))
        add = got["ide_find_usages"]
        self.assertEqual(["known", "rows", "form", "field", "note"], list(add))
        self.assertEqual((self.KNOWN, "rows", "nameOnlyMatches"), (add["known"], add["form"], add["field"]))
        self.assertEqual([{**row, "match": "DYNAMIC"} for row in self.ROWS], add["rows"])
        self.assertNotIn("match", self.ROWS[0], "the rows are copies")
        self.assertTrue(add["note"].startswith("2 rows of `usages` have `match` = `DYNAMIC` and come from the name "
                                               "only: each is an attribute `label` on a value whose type does not "
                                               "declare `label`, "), add["note"])
        self.assertEqual(runner.ADDITION_NOTES["rows"].format(n=2, name="label"), add["note"])
        self.assertIs(add, proxy._addition({"additions": got}, runner.ADDITION_TOOL), "the proxy takes the addition")

    def test_PFL_rows_are_the_file_rows(self):
        got = runner.route_additions(KEY, "PFL")
        add = got["ide_find_usages"]
        self.assertEqual((self.KNOWN, self.ROWS, "field", "nameOnlyMatches"),
                         (add["known"], add["rows"], add["form"], add["field"]))
        self.assertFalse(any("match" in row for row in add["rows"]))
        self.assertTrue(add["note"].startswith("`nameOnlyMatches` holds 2 lines that are not in `usages` and come "
                                               "from the name only: each is an attribute `label` on a value whose "
                                               "type does not declare `label`, "), add["note"])
        self.assertEqual(runner.ADDITION_NOTES["field"].format(n=2, name="label"), add["note"])
        self.assertIs(add, proxy._addition({"additions": got}, runner.ADDITION_TOOL), "the proxy takes the addition")

    def test_entry_is_the_entry_of_the_name_else_of_an_old_id(self):
        key = {**KEY, "question": "beets-refs-new", "old_ids": ["beets-refs-old", CHALLENGE["id"]]}
        self.assertEqual(self.ROWS, runner.route_additions(key, "PFL")["ide_find_usages"]["rows"], "an old id")
        named = {**self.item, "rows": self.ROWS[:1]}
        write(runner.ADDITIONS_FILE, json.dumps({CHALLENGE["id"]: self.item, "beets-refs-new": named}))
        self.assertEqual(self.ROWS[:1], runner.route_additions(key, "PFL")["ide_find_usages"]["rows"], "the name")
        with self.assertRaises(runner.SetupError) as e:
            runner.route_additions({**key, "old_ids": ["beets-refs-old"], "question": "beets-refs-x"}, "PFR")
        self.assertIn("'beets-refs-x'", str(e.exception))

    def test_bad_file_or_entry_is_a_setup_error(self):
        item = lambda **change: json.dumps({CHALLENGE["id"]: {**self.item, **change}})
        cases = [("no JSON", "{not json"), ("a list", "[]"), ("no entry", json.dumps({"other": self.item})),
                 ("entry no object", json.dumps({CHALLENGE["id"]: ["label"]})),
                 ("name absent", json.dumps({CHALLENGE["id"]: {"known": self.KNOWN, "rows": self.ROWS}})),
                 ("name empty", item(name="")), ("name no text", item(name=7)),
                 ("known no list", item(known={"beets/a.py": 10})),
                 ("known pair with a text line", item(known=[["beets/a.py", "10"]])),
                 ("known pair with a bool line", item(known=[["beets/a.py", True]])),
                 ("known pair of one item", item(known=[["beets/a.py"]])),
                 ("rows absent", json.dumps({CHALLENGE["id"]: {"name": "label", "known": self.KNOWN}})),
                 ("rows empty", item(rows=[])), ("rows no list", item(rows=self.ROWS[0])),
                 ("row no object", item(rows=["beets/a.py:12"])), ("row with no file", item(rows=[{"line": 3}])),
                 ("row with a text line", item(rows=[{"file": "beets/a.py", "line": "12"}]))]
        for what, text in [("absent file", None)] + cases:
            with self.subTest(what):
                if text is None:
                    os.unlink(runner.ADDITIONS_FILE)
                else:
                    write(runner.ADDITIONS_FILE, text)
                for arm in ("PFR", "PFL"):
                    with self.assertRaises(runner.SetupError) as e:
                        runner.route_additions(KEY, arm)
                    self.assertIn(runner.ADDITIONS_FILE, str(e.exception))
        os.unlink(runner.ADDITIONS_FILE)
        code, _, _, err = self.start("PFR")
        self.assertEqual(2, code)
        self.assertIn(runner.ADDITIONS_FILE, err)
        self.assertEqual([], self.docker_calls())

    def test_prepare_gives_the_PF_prompt_and_the_additions(self):
        pf = runner.prepare(runner._parser().parse_args(self.run_args("PF")))
        self.assertIsNone(pf["additions"])
        self.assertEqual(runner.PF_SENTENCE.format(server=SERVER), prompt_of(pf["cmd"]).split("\n\n")[-2])
        self.assertIsNone(runner.prepare(runner._parser().parse_args(self.run_args("PFN")))["additions"])
        for arm in ("PFR", "PFL"):
            run = runner.prepare(runner._parser().parse_args(self.run_args(arm)))
            self.assertEqual(runner.route_additions(KEY, arm), run["additions"], arm)
            self.assertEqual((True, None), (run["plugin"], run["notes"]), arm)
            self.assertEqual(prompt_of(pf["cmd"]), prompt_of(run["cmd"]), arm)
            self.assertEqual("--mcp-config", run["cmd"][-2], arm)

    def test_route_of_a_run_has_the_additions(self):
        for arm in ("PFR", "PFL", "PF"):
            code, rec, _, err = self.start(arm)
            self.assertEqual((0, "ok", arm), (code, rec["outcome"], rec["arm"]), err)
            self.assertEqual(f"{CHALLENGE['id']}__{arm}__{MODEL}__1", rec["id"])
        routes = [c["route"] for c in self.docker_calls() if "route" in c]
        self.assertEqual(3, len(routes))
        self.assertEqual(runner.route_additions(KEY, "PFR"), routes[0]["additions"])
        self.assertEqual(runner.route_additions(KEY, "PFL"), routes[1]["additions"])
        self.assertIsNone(routes[2]["additions"])
        self.assertEqual([None] * 3, [route["notes"] for route in routes])
        self.assertEqual({}, self.routes_now())

    def test_dry_run_prints_the_form_and_the_row_count(self):
        for arm, form in (("PFR", "rows"), ("PFL", "field")):
            code, out, err = self.main(*self.run_args(arm), "-dry-run")
            self.assertEqual(0, code, err)
            self.assertIn(f"runner: dry run {CHALLENGE['id']}__{arm}__{MODEL}__1: arm {arm}; route additions: {form}, "
                          "2 rows\n", err)
            self.assertEqual(runner.PF_SENTENCE.format(server=SERVER), prompt_of(json.loads(out)).split("\n\n")[-2])
        code, _, err = self.main(*self.run_args("PF"), "-dry-run")
        self.assertEqual(0, code, err)
        self.assertNotIn("route additions", err)
        self.assertEqual(({}, []), (self.routes_now(), self.docker_calls()))


class PfgTest(RunnerCase):
    """Arm PFG: the prompt of arm PF with runner.PFG_SENTENCE after the PF sentence in the same paragraph, and a route
    with no notes and no additions."""
    TEXT = ("A usage list of the IDE holds the references that the IDE can prove, and it can lack a line. After a usage "
            "list, search the text for the name, and check each line that the list does not hold.")

    def test_PFG_prompt_has_the_PFG_sentence_in_the_PF_paragraph(self):
        self.assertEqual(self.TEXT, runner.PFG_SENTENCE)
        self.assertEqual(("PF", "PFN", "PFR", "PFL", "PFG", "PFI", "PFS"), runner.PF_ARMS)
        base = challenges.prompt(CHALLENGE, RECORD, ROOT)
        self.assertTrue(base.endswith("\n\n" + challenges.TAIL))
        head, sentence = base[:-len(challenges.TAIL)], runner.PF_SENTENCE.format(server=SERVER)
        pf, pfg = prompt_of(self.dry("PF")), prompt_of(self.dry("PFG"))
        self.assertEqual(f"{head}{sentence}\n\n{challenges.TAIL}", pf, "the PF prompt did not change")
        self.assertEqual(f"{head}{sentence} {self.TEXT}\n\n{challenges.TAIL}", pfg)
        self.assertEqual(len(pf.split("\n\n")), len(pfg.split("\n\n")), "no new paragraph")
        self.assertEqual([f"{sentence} {self.TEXT}", challenges.TAIL], pfg.split("\n\n")[-2:])
        self.assertEqual((pf, pfg), (runner.pf_prompt(base, SERVER), runner.pf_prompt(base, SERVER, self.TEXT)))
        self.assertEqual(pf, prompt_of(self.dry("PFN")), "arm PFN keeps the PF prompt")

    def test_prepare_gives_a_plugin_run_with_no_notes_and_no_additions(self):
        self.assertFalse(os.path.exists(runner.ADDITIONS_FILE))
        self.assertIn("PFG", runner.PLUGIN_ARMS)
        with mock.patch.object(runner, "NOTES_FILE", os.path.join(self.tmp, "absent-notes.json")):
            run = runner.prepare(runner._parser().parse_args(self.run_args("PFG")))
        self.assertEqual((True, None, None), (run["plugin"], run["notes"], run["additions"]))
        self.assertRegex(run["token"], "^[0-9a-f]{32}$")
        self.assertEqual("--mcp-config", run["cmd"][-2])
        self.assertIn(proxy.route_url(run["token"]), run["cmd"][-1])
        self.assertIsNone(runner.route_additions(KEY, "PFG"))

    def test_route_of_a_run_has_no_notes_and_no_additions(self):
        code, rec, _, err = self.start("PFG")
        self.assertEqual((0, "ok", "PFG", f"{CHALLENGE['id']}__PFG__{MODEL}__1"),
                         (code, rec["outcome"], rec["arm"], rec["id"]), err)
        routes = [c["route"] for c in self.docker_calls() if "route" in c]
        self.assertEqual([(None, None)], [(route["notes"], route["additions"]) for route in routes])
        self.assertIn(self.TEXT, prompt_of(self.runs_of_docker()[0]["argv"]))
        self.assertEqual({}, self.routes_now())

    def test_dry_run_line_has_no_notes_and_no_additions(self):
        code, out, err = self.main(*self.run_args("PFG"), "-dry-run")
        self.assertEqual(0, code, err)
        self.assertIn(f"runner: dry run {CHALLENGE['id']}__PFG__{MODEL}__1: arm PFG\n", err)
        self.assertNotIn("route notes", err)
        self.assertNotIn("route additions", err)
        self.assertEqual("docker", json.loads(out)[0])
        self.assertEqual(({}, []), (self.routes_now(), self.docker_calls()))


class PfiTest(CaddyCase):
    """Arm PFI: the prompt of arm PF, and a route whose note for ide_find_usages is runner.PFG_SENTENCE (the
    instruction of PFG at the place of the notes of PFN)."""
    NOTES = {"ide_find_usages": PfgTest.TEXT}

    @staticmethod
    def prompt_in(run):
        return run["cmd"][run["cmd"].index("-p") + 1]

    def test_PFI_prompt_is_the_PF_prompt(self):
        self.assertIn("PFI", runner.PF_ARMS)
        self.assertEqual(prompt_of(self.dry("PF")), prompt_of(self.dry("PFI")))
        self.assertEqual(self.prompt_in(runner.prepare(self.caddy_args("PF"))),
                         self.prompt_in(runner.prepare(self.caddy_args("PFI"))))

    def test_prepare_gives_the_PFG_sentence_as_the_note_of_find_usages(self):
        self.assertEqual("ide_find_usages", runner.ADDITION_TOOL)
        self.assertFalse(os.path.exists(runner.ADDITIONS_FILE))
        self.assertIn("PFI", runner.PLUGIN_ARMS)
        for notes_file in (runner.NOTES_FILE, os.path.join(self.tmp, "absent-notes.json")):
            with mock.patch.object(runner, "NOTES_FILE", notes_file):
                beets = runner.prepare(runner._parser().parse_args(self.run_args("PFI")))
                caddy = runner.prepare(self.caddy_args("PFI"))
            for run in (beets, caddy):
                self.assertEqual((True, self.NOTES, None), (run["plugin"], run["notes"], run["additions"]), notes_file)
                self.assertEqual("--mcp-config", run["cmd"][-2])
        self.assertIsNone(runner.route_additions(KEY, "PFI"))

    def test_route_of_a_run_has_the_note(self):
        code, rec, _, err = self.start("PFI")
        self.assertEqual((0, "ok", "PFI", f"{CHALLENGE['id']}__PFI__{MODEL}__1"),
                         (code, rec["outcome"], rec["arm"], rec["id"]), err)
        self.assertTrue(os.path.isdir(self.folder("PFI")))
        routes = [c["route"] for c in self.docker_calls() if "route" in c]
        self.assertEqual([(self.NOTES, None)], [(route["notes"], route["additions"]) for route in routes])
        self.assertEqual(prompt_of(self.dry("PF")), prompt_of(self.runs_of_docker()[0]["argv"]))
        self.assertEqual({}, self.routes_now())

    def test_dry_run_line_names_the_tool_of_the_note(self):
        code, out, err = self.main(*self.run_args("PFI"), "-dry-run")
        self.assertEqual(0, code, err)
        self.assertIn(f"runner: dry run {CHALLENGE['id']}__PFI__{MODEL}__1: arm PFI; route notes (python): "
                      "ide_find_usages\n", err)
        self.assertNotIn("route additions", err)
        self.assertEqual("docker", json.loads(out)[0])
        self.assertEqual(({}, []), (self.routes_now(), self.docker_calls()))


class PfsTest(RunnerCase):
    """Arm PFS: the prompt of arm PF with runner.PFS_SENTENCE (the statement of PFN) after the PF sentence in the same
    paragraph, and a route with no notes and no additions."""
    TEXT = ("A usage list of the IDE can be incomplete: a call on a value with no known type is absent. A text search "
            "for the name finds such calls.")

    def head_and_sentence(self):
        base = challenges.prompt(CHALLENGE, RECORD, ROOT)
        self.assertTrue(base.endswith("\n\n" + challenges.TAIL))
        return base[:-len(challenges.TAIL)], runner.PF_SENTENCE.format(server=SERVER)

    def test_PFS_prompt_has_the_PFS_sentence_in_the_PF_paragraph(self):
        self.assertEqual(self.TEXT, runner.PFS_SENTENCE)
        self.assertIn("PFS", runner.PF_ARMS)
        head, sentence = self.head_and_sentence()
        pf, pfs = prompt_of(self.dry("PF")), prompt_of(self.dry("PFS"))
        self.assertEqual(f"{head}{sentence} {self.TEXT}\n\n{challenges.TAIL}", pfs)
        self.assertEqual(len(pf.split("\n\n")), len(pfs.split("\n\n")), "no new paragraph")
        self.assertEqual([f"{sentence} {self.TEXT}", challenges.TAIL], pfs.split("\n\n")[-2:])
        self.assertEqual(pfs, runner.pf_prompt(challenges.prompt(CHALLENGE, RECORD, ROOT), SERVER, self.TEXT))

    def test_prompts_of_PF_PFN_and_PFG_did_not_change(self):
        head, sentence = self.head_and_sentence()
        pf = f"{head}{sentence}\n\n{challenges.TAIL}"
        self.assertEqual(pf, prompt_of(self.dry("PF")))
        self.assertEqual(pf, prompt_of(self.dry("PFN")))
        self.assertEqual(f"{head}{sentence} {PfgTest.TEXT}\n\n{challenges.TAIL}", prompt_of(self.dry("PFG")))

    def test_prepare_gives_a_plugin_run_with_no_notes_and_no_additions(self):
        self.assertFalse(os.path.exists(runner.ADDITIONS_FILE))
        self.assertIn("PFS", runner.PLUGIN_ARMS)
        with mock.patch.object(runner, "NOTES_FILE", os.path.join(self.tmp, "absent-notes.json")):
            run = runner.prepare(runner._parser().parse_args(self.run_args("PFS")))
        self.assertEqual((True, None, None), (run["plugin"], run["notes"], run["additions"]))
        self.assertEqual("--mcp-config", run["cmd"][-2])
        self.assertIsNone(runner.route_additions(KEY, "PFS"))

    def test_route_of_a_run_has_no_notes_and_no_additions(self):
        code, rec, _, err = self.start("PFS")
        self.assertEqual((0, "ok", "PFS", f"{CHALLENGE['id']}__PFS__{MODEL}__1"),
                         (code, rec["outcome"], rec["arm"], rec["id"]), err)
        routes = [c["route"] for c in self.docker_calls() if "route" in c]
        self.assertEqual([(None, None)], [(route["notes"], route["additions"]) for route in routes])
        self.assertIn(self.TEXT, prompt_of(self.runs_of_docker()[0]["argv"]))
        self.assertEqual({}, self.routes_now())

    def test_dry_run_line_has_no_notes_and_no_additions(self):
        code, _, err = self.main(*self.run_args("PFS"), "-dry-run")
        self.assertEqual(0, code, err)
        self.assertIn(f"runner: dry run {CHALLENGE['id']}__PFS__{MODEL}__1: arm PFS\n", err)
        self.assertNotIn("route notes", err)
        self.assertNotIn("route additions", err)
        self.assertEqual(({}, []), (self.routes_now(), self.docker_calls()))


class GuideTest(RunnerCase):
    """Variant guide: the route gets runner.GUIDE_INSTRUCTIONS (the instruction of PFG in the server instructions), and
    each other part of the run is the part of a run with no variant."""
    HEAD = "Use the tools of this server for code navigation in the open project. "
    LABELS = (("P", (), "P"), ("PS", ("-aid", "rule"), "PS-rule"), ("PF", (), "PF"))

    @staticmethod
    def neutral(run):
        """The docker command of a prepared run with no container name and no route token."""
        return [a.replace(run["name"], "NAME").replace(run["token"], "TOKEN") for a in run["cmd"]]

    def test_guide_text_is_the_head_and_the_PFG_sentence(self):
        self.assertEqual(("instructions", "no-tool-search", "guide"), runner.VARIANTS)
        self.assertTrue(runner.GUIDE_INSTRUCTIONS.startswith(self.HEAD))
        self.assertTrue(runner.GUIDE_INSTRUCTIONS.endswith(runner.PFG_SENTENCE))
        self.assertEqual(self.HEAD + PfgTest.TEXT, runner.GUIDE_INSTRUCTIONS)

    def test_prepare_gives_the_parts_of_a_run_with_no_variant(self):
        for arm, extra, label in self.LABELS:
            plain = runner.prepare(runner._parser().parse_args(self.run_args(arm, *extra)))
            guide = runner.prepare(runner._parser().parse_args(self.run_args(arm, *extra, "-variant", "guide")))
            self.assertEqual((True, None, None), (guide["plugin"], guide["notes"], guide["additions"]), arm)
            self.assertEqual(self.neutral(plain), self.neutral(guide), arm)
            self.assertEqual(f"{CHALLENGE['id']}__{label}-guide__{MODEL}__1", guide["run_id"])
        code, out, err = self.main(*self.run_args("P", "-variant", "guide"), "-dry-run")
        self.assertEqual(0, code, err)
        self.assertIn(f"runner: dry run {CHALLENGE['id']}__P-guide__{MODEL}__1: arm P\n", err)
        self.assertEqual(prompt_of(self.dry("P")), prompt_of(json.loads(out)))
        self.assertEqual(({}, []), (self.routes_now(), self.docker_calls()))

    def test_route_of_a_P_run_has_the_guide_instructions(self):
        code, rec, _, err = self.start("P", "-variant", "guide")
        self.assertEqual((0, "ok", "P", "guide", f"{CHALLENGE['id']}__P-guide__{MODEL}__1"),
                         (code, rec["outcome"], rec["arm"], rec["variant"], rec["id"]), err)
        self.assertTrue(os.path.isdir(self.folder("P-guide")))
        routes = [c["route"] for c in self.docker_calls() if "route" in c]
        self.assertEqual([(runner.GUIDE_INSTRUCTIONS, None, None)],
                         [(route["instructions"], route["notes"], route["additions"]) for route in routes])
        self.assertEqual(prompt_of(self.dry("P")), prompt_of(self.runs_of_docker()[0]["argv"]))
        self.assertEqual({}, self.routes_now())

    def test_route_instructions_of_each_variant(self):
        texts = {None: None, "instructions": runner.INSTRUCTIONS, "no-tool-search": None,
                 "guide": runner.GUIDE_INSTRUCTIONS}
        for arm, extra, label in self.LABELS:
            for variant, text in texts.items():
                code, rec, _, err = self.start(arm, *extra, *(("-variant", variant) if variant else ()))
                self.assertEqual((0, "ok"), (code, rec["outcome"]), (label, variant, err))
                route = [c["route"] for c in self.docker_calls() if "route" in c][-1]
                self.assertEqual(text, route["instructions"], (label, variant))
        self.assertEqual({}, self.routes_now())

    def test_guide_is_refused_for_the_other_arms(self):
        for arm in ("C", "PFN", "PFR", "PFL", "PFG", "PFI", "PFS"):
            code, out, err = self.main(*self.run_args(arm, "-variant", "guide"), "-dry-run")
            self.assertEqual((2, ""), (code, out), arm)
            self.assertIn(f"-variant is for the arms P, PS and PF, not for arm {arm}", err)
        self.assertEqual(({}, []), (self.routes_now(), self.docker_calls()))


class KeyTest(RunnerCase):
    def test_read_key_refuses_two_lines(self):
        path = os.path.join(self.tmp, "k2")
        write(path, "  sk-one  \n")
        self.assertEqual("sk-one", runner.read_key(path))
        for text in ("sk-one\nsk-two\n", "", " \n\t\n"):
            write(path, text)
            with self.assertRaises(runner.KeyFileError) as e:
                runner.read_key(path)
            self.assertNotIn("sk-", str(e.exception))
        with self.assertRaises(runner.KeyFileError):
            runner.read_key(os.path.join(self.tmp, "absent"))

    def test_key_is_not_in_command_or_run_json_or_dry_run(self):
        with mock.patch.object(runner, "read_key", side_effect=AssertionError("a dry run reads the key")):
            code, out, err = self.main(*self.run_args("P"), "-dry-run")
        self.assertEqual(0, code)
        self.assertNotIn(FAKE_KEY, out + err)
        code, rec, out, err = self.start("P")
        self.assertEqual((0, "ok"), (code, rec["outcome"]), err)
        run_call = self.runs_of_docker()
        self.assertEqual(1, len(run_call))
        self.assertEqual(FAKE_KEY, run_call[0]["key"], "the key is in the environment of the docker process")
        self.assertNotIn(FAKE_KEY, json.dumps(run_call[0]["argv"]))
        self.assertIn("ANTHROPIC_API_KEY", run_call[0]["argv"])
        with open(os.path.join(self.folder("P"), "run.json"), encoding="utf-8") as f:
            self.assertNotIn(FAKE_KEY, f.read())
        self.assertNotIn(FAKE_KEY, out + err)
        self.assertEqual([], runner.search_key(
            [os.path.join(self.folder("P"), name) for name in os.listdir(self.folder("P"))], FAKE_KEY))

    def test_key_hit_deletes_files_and_exits_9(self):
        code, rec, out, err = self.start("P", print_key=1)
        self.assertEqual(9, code)
        self.assertEqual("key_leak", rec["outcome"])
        self.assertEqual(["run.json"], os.listdir(self.folder("P")))
        self.assertIsNone(rec["answer"])
        self.assertIsNone(rec["tools"])
        self.assertEqual(0.4321, rec["cost_usd"])
        self.assertIn("transcript.jsonl", rec["reason"])
        with open(os.path.join(self.folder("P"), "run.json"), encoding="utf-8") as f:
            self.assertNotIn(FAKE_KEY, f.read())
        self.assertNotIn(FAKE_KEY, out + err)
        self.assertEqual([], os.listdir(self.log_dir), "the proxy log of the run went into the run folder")
        self.assertEqual({}, self.routes_now())


class RunTest(RunnerCase):
    def test_run_reads_the_question_file(self):
        question = os.path.join(qfiles.QUESTIONS, KEY["question"] + ".md")
        write(question, "Find each use of `helper` below {root}.\n\n" + challenges.TAIL + "\n")
        self.assertFalse(os.path.exists(challenges.KEYS), "no key record file of the data root")
        self.assertEqual(f"Find each use of `helper` below {ROOT}.\n\n{challenges.TAIL}", prompt_of(self.dry("C")))
        code, rec, _, err = self.start("C", fixture=self.c_ok())
        self.assertEqual((0, "ok"), (code, rec["outcome"]), err)
        def digest(path):
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        self.assertEqual((KEY["question"], digest(question),
                          digest(os.path.join(qfiles.KEYS, KEY["question"] + ".json"))),
                         (rec["question"], rec["question_sha256"], rec["key_sha256"]))
        self.assertNotIn("challenge", rec)
        self.assertEqual(2, rec["score"]["tp"], "the score comes from the tracked key")
        os.unlink(os.path.join(qfiles.KEYS, KEY["question"] + ".json"))
        code, _, err = self.main(*self.run_args("C", "-n", "2"))
        self.assertEqual(2, code)
        self.assertIn(KEY["question"], err)
        self.assertEqual(1, len(self.runs_of_docker()), "no run starts with no key")

    def test_result_event_gives_cost_turns_answer(self):
        code, rec, _, err = self.start("P")
        self.assertEqual(0, code, err)
        self.assertEqual("ok", rec["outcome"])
        self.assertIsNone(rec["reason"])
        self.assertEqual((0.4321, 7, 0), (rec["cost_usd"], rec["turns"], rec["exit_code"]))
        self.assertEqual(160, rec["usage"]["output_tokens"])
        self.assertEqual([MODEL], list(rec["model_usage"]))
        self.assertEqual([".venv/lib/x.py:1", "beets/a.py:10", "beets/b.py:4", "beets/b.py:9"], rec["answer"])
        self.assertEqual(["beets/a.py:3-9"], rec["invalid"])
        self.assertEqual({"tp": 2, "fp": 1, "miss": 0, "ignored": 0, "precision": 2 / 3, "recall": 1.0,
                          "exact": False, "invalid": 1, "outside": 1, "listed": 3}, rec["score"])
        find = f"mcp__{SERVER}__ide_find_usages"
        self.assertEqual({"ToolSearch": 1, find: 2, "Grep": 1, "Read": 1, "StructuredOutput": 1}, rec["tools"])
        self.assertEqual(["ToolSearch", find, "Grep", find, "Read"], rec["first_tools"])
        self.assertEqual(2, rec["mcp_calls"])
        self.assertEqual({w: 0 for w in LEAK_WORDS}, rec["leak_words"])
        self.assertEqual((VERSION, VERSION), (rec["plugin_version_start"], rec["plugin_version_end"]))
        self.assertEqual("sha256:feed", rec["image_id"])
        self.assertEqual(list(runner.RUN_FIELDS), list(rec))
        folder = self.folder("P")
        self.assertEqual(sorted(runner.RUN_FILES + ("run.json",)), sorted(os.listdir(folder)))
        with open(os.path.join(folder, "transcript.jsonl"), "rb") as f, \
                open(os.path.join(FIXTURES, "ok.jsonl"), "rb") as g:
            self.assertEqual(g.read(), f.read())
        with open(os.path.join(folder, "stderr.txt"), encoding="utf-8") as f:
            self.assertEqual("fake docker\n", f.read())
        with open(os.path.join(folder, "proxy.jsonl"), encoding="utf-8") as f:
            self.assertEqual(4, len(f.readlines()))
        code, _, err = self.main(*self.run_args("P"))
        self.assertEqual(2, code, "a folder with run.json is not run again")
        self.assertIn("run.json", err)

    def test_no_result_event_is_no_answer(self):
        code, rec, _, err = self.start("C", fixture="no_result.jsonl")
        self.assertEqual((0, "no_answer"), (code, rec["outcome"]), err)
        self.assertIsNone(rec["cost_usd"])
        self.assertIsNone(rec["answer"])
        self.assertIsNone(rec["score"])
        self.assertEqual(0, rec["mcp_calls"])
        with open(os.path.join(self.folder("C"), "proxy.jsonl"), encoding="utf-8") as f:
            self.assertEqual("", f.read(), "arm C has an empty proxy log")
        shutil.rmtree(self.folder("C"))
        code, rec, _, _ = self.start("C", fixture="no_structured.jsonl")
        self.assertEqual("no_answer", rec["outcome"])
        self.assertEqual(0.0123, rec["cost_usd"])

    def test_budget_and_docker_failure(self):
        code, rec, _, _ = self.start("C", fixture="budget.jsonl")
        self.assertEqual((0, "budget"), (code, rec["outcome"]))
        self.assertEqual(20.0412, rec["cost_usd"])
        shutil.rmtree(self.folder("C"))
        code, rec, _, _ = self.start("C", fixture=None, exit=125)
        self.assertEqual((1, "error", 125), (code, rec["outcome"], rec["exit_code"]))

    def test_timeout_kills_and_sets_outcome(self):
        with mock.patch.object(runner, "WALL_LIMIT", 1):
            begin = time.monotonic()
            code, rec, _, err = self.start("C", fixture="no_result.jsonl", sleep=30)
            took = time.monotonic() - begin
        self.assertEqual((0, "timeout"), (code, rec["outcome"]), err)
        self.assertLess(took, 15)
        name = self.runs_of_docker()[0]["argv"][self.runs_of_docker()[0]["argv"].index("--name") + 1]
        self.assertIn(["kill", name], [c["argv"] for c in self.docker_calls()])

    def test_stop_after_tools(self):
        code, rec, _, err = self.start("C", "-stop-after-tools", "2", fixture="tools3.jsonl", delay=1, sleep=30)
        self.assertEqual((0, "stopped"), (code, rec["outcome"]), err)
        self.assertEqual(["Grep", "ToolSearch"], rec["first_tools"])
        self.assertEqual(2, sum(rec["tools"].values()))
        self.assertTrue(os.path.isdir(self.folder("C-stop-2")))

    def test_stop_after_tools_does_not_count_structured_output(self):
        tool = lambda i, name: json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": {}}]}})
        names = ("Bash", "StructuredOutput", "Bash", "Grep")
        path = os.path.join(self.tmp, "stop.jsonl")
        init = json.dumps({"type": "system", "subtype": "init", "mcp_servers": []})
        write(path, "".join(line + "\n" for line in [init] + [tool(i, name) for i, name in enumerate(names)]))
        code, rec, _, err = self.start("C", "-stop-after-tools", "2", fixture=path, delay=1, sleep=30)
        self.assertEqual((0, "stopped"), (code, rec["outcome"]), err)
        self.assertEqual(["Bash", "StructuredOutput", "Bash"], rec["first_tools"])
        self.assertEqual({"Bash": 2, "StructuredOutput": 1}, rec["tools"])

    def test_route_is_removed_after_the_run(self):
        code, rec, _, _ = self.start("PF")
        self.assertEqual("ok", rec["outcome"])
        self.assertEqual(1, len([c for c in self.docker_calls() if c.get("route")]), "the route existed in the run")
        self.assertEqual({}, self.routes_now())
        shutil.rmtree(self.folder("PF"))
        code, rec, _, _ = self.start("PF", fixture=None, exit=125)
        self.assertEqual((1, "error"), (code, rec["outcome"]))
        self.assertEqual({}, self.routes_now())
        shutil.rmtree(self.folder("PF"))
        os.environ["PATH"] = os.path.join(self.tmp, "no-bin")
        code, rec, _, _ = self.start("PF")
        self.assertEqual((1, "error"), (code, rec["outcome"]))
        self.assertIn("FileNotFoundError", rec["reason"])
        self.assertEqual({}, self.routes_now())

    def test_invalid_when_version_differs(self):
        self.ide = [("2.1.0", None)]
        code, rec, _, _ = self.start("P", "-plugin-version", VERSION)
        self.assertEqual((0, "invalid"), (code, rec["outcome"]))
        self.assertIn("2.1.0", rec["reason"])
        self.assertEqual([], self.runs_of_docker(), "no container starts")
        self.assertEqual({}, self.routes_now())
        # With no -plugin-version, the version of the IDE at the start is the expected version.
        cases = (([(VERSION, "isDumbMode is True")], {}, "not ready"),
                 ([(VERSION, None), ("2.1.0", None)], {}, "at the end"),
                 ([("2.1.0", None), (VERSION, None)], {}, "at the end"),
                 ([], {"proxy_status": 502}, "no answer from the IDE"),
                 ([], {"proxy_version": "2.1.0"}, "2.1.0"))
        for ide, fake, word in cases:
            shutil.rmtree(os.path.join(self.runs, "b1"))
            for name in ("FAKE_DOCKER_PROXY_STATUS", "FAKE_DOCKER_PROXY_VERSION"):
                os.environ.pop(name, None)
            self.ide = list(ide)
            code, rec, _, _ = self.start("P", **fake)
            self.assertEqual((0, "invalid"), (code, rec["outcome"]), word)
            self.assertIn(word, rec["reason"])

    def test_plugin_arm_needs_the_proxy(self):
        with mock.patch.object(runner, "proxy_healthy", lambda *a, **k: False):
            code, rec, _, err = self.start("P")
            self.assertEqual(2, code)
            self.assertIn("proxy", err)
            self.assertEqual([], self.docker_calls())
            self.assertFalse(os.path.exists(os.path.join(self.runs, "b1")))
            code, rec, _, _ = self.start("C", fixture=self.c_ok())
            self.assertEqual((0, "ok"), (code, rec["outcome"]))

    def test_run_refuses_another_version(self):
        self.ide = [("2.0", None)]
        code, rec, out, err = self.start("P", "-plugin-version", "1.0")
        self.assertEqual((0, "invalid"), (code, rec["outcome"]), err)
        self.assertEqual("plugin version '2.0' at the start, expected 1.0", rec["reason"])
        self.assertEqual(("2.0", None), (rec["plugin_version_start"], rec["plugin_version_end"]))
        self.assertIn("2.0", out)
        self.assertIn("1.0", out)
        self.assertEqual([], self.runs_of_docker(), "no container command")
        self.assertEqual({}, self.routes_now())

    def test_missing_key_file_starts_nothing(self):
        os.unlink(os.environ["BENCH_SECRET_FILE"])
        code, rec, _, err = self.start("C")
        self.assertEqual(2, code)
        self.assertIn("absent", err)
        del os.environ["BENCH_SECRET_FILE"]
        code, rec, _, err = self.start("C")
        self.assertEqual(2, code)
        self.assertIn("BENCH_SECRET_FILE", err)
        self.assertEqual([], self.docker_calls())

    def test_busy_lock_starts_nothing(self):
        plan = os.path.join(self.tmp, "plan.json")
        write(plan, json.dumps({"rule": "A test plan.", "questions": [KEY["question"]], "arms": [{"arm": "P"}],
                                "models": [MODEL], "runs": 1}))
        self.assertEqual([], planfile.problems(planfile.load(plan)), "a valid plan: the lock is the only cause")
        with lock.ide_lock("audit.symbols run /x/out"):
            for argv in (self.run_args("P"), ["batch", "-plan", plan, "-batch", "b1"]):
                code, out, err = self.main(*argv)
                self.assertEqual(2, code, argv)
                self.assertIn("audit.symbols run /x/out", err)
                self.assertIn(f"pid {os.getpid()}", err)
                self.assertIn("no run starts", err)
        self.assertEqual([], self.docker_calls(), "no container")
        self.assertFalse(os.path.exists(self.routes), "no route")
        self.assertFalse(os.path.exists(self.runs))
        # A dry run uses no IDE and takes no lock.
        with lock.ide_lock("x"):
            self.dry("P")
        # Free again: the run takes the lock and runs.
        code, rec, _, err = self.start("P")
        self.assertEqual((0, "ok"), (code, rec["outcome"]), err)

    def test_leak_words_are_counted(self):
        self.assertEqual((os.path.basename(trees.BENCH), "-plant-", "BENCH_", settings.repo_root() + "/"),
                         MACHINE_LEAK_WORDS)
        code, rec, _, _ = self.start("C", fixture=self.c_ok(), extra=json.dumps(
            {"type": "user", "x": "/srv/idesense-bench/trees/caddy-plant-2 BENCH_SLOT"}))
        self.assertEqual("ok", rec["outcome"])
        self.assertEqual({"idesense-bench": 1, "-plant-": 1, "BENCH_": 1, "/srv/repo/": 0}, rec["leak_words"])


class McpStatusTest(RunnerCase):
    def servers(self, status):
        return f'"mcp_servers":[{{"name":"{SERVER}","status":"{status}"}}]'

    def test_plugin_arm_with_failed_server_is_invalid(self):
        for status in ("failed", "pending", "needs-auth"):
            code, rec, _, _ = self.start("P", fixture=self.fixture_with("ok.jsonl", INIT_SERVERS, self.servers(status)))
            self.assertEqual((0, "invalid"), (code, rec["outcome"]), status)
            self.assertIn(repr(status), rec["reason"])
            self.assertEqual({SERVER: status}, rec["mcp_status"])
            self.assertIsNotNone(rec["score"], "the answer stays in run.json")
            shutil.rmtree(self.folder("P"))
        code, rec, _, _ = self.start("PF", fixture=self.c_ok())
        self.assertEqual("invalid", rec["outcome"])
        self.assertIn("not in the init event", rec["reason"])
        self.assertEqual({}, rec["mcp_status"])
        # stopped, timeout and key_leak keep their outcome.
        failed_tools = self.fixture_with("tools3.jsonl", INIT_SERVERS, self.servers("failed"))
        code, rec, _, _ = self.start("P", "-stop-after-tools", "1", fixture=failed_tools, sleep=30)
        self.assertEqual("stopped", rec["outcome"])
        self.assertEqual({SERVER: "failed"}, rec["mcp_status"])
        with mock.patch.object(runner, "WALL_LIMIT", 1):
            code, rec, _, _ = self.start("PS", "-aid", "rule", fixture="no_result.jsonl", sleep=30)
        self.assertEqual(("timeout", {}), (rec["outcome"], rec["mcp_status"]))
        shutil.rmtree(os.path.join(self.runs, "b1"))
        os.environ.pop("FAKE_DOCKER_SLEEP")
        code, rec, _, _ = self.start("P", fixture=self.fixture_with("ok.jsonl", INIT_SERVERS, self.servers("failed")),
                                     print_key=1)
        self.assertEqual((9, "key_leak"), (code, rec["outcome"]))

    def test_arm_C_with_a_server_is_invalid(self):
        code, rec, _, _ = self.start("C")
        self.assertEqual((0, "invalid"), (code, rec["outcome"]))
        self.assertIn("arm C has MCP servers", rec["reason"])
        self.assertEqual({SERVER: "connected"}, rec["mcp_status"])

    def test_init_event_gives_mcp_status(self):
        code, rec, _, _ = self.start("P")
        self.assertEqual(("ok", {SERVER: "connected"}), (rec["outcome"], rec["mcp_status"]))
        code, rec, _, _ = self.start("C", fixture="no_result.jsonl")
        self.assertEqual({}, rec["mcp_status"])
        init = lambda servers: json.dumps({"type": "system", "subtype": "init", "mcp_servers": servers})
        two = [init([{"name": "a", "status": "connected"}, {"status": "x"}, "b"]), init([{"name": "c", "status": "failed"}])]
        self.assertEqual({"a": "connected"}, runner.parse_transcript(two)["mcp_status"], "the first init event counts")
        no_field = json.dumps({"type": "system", "subtype": "init", "tools": []})
        self.assertIsNone(runner.parse_transcript([no_field])["mcp_status"])
        self.assertIsNone(runner.parse_transcript([init("text")])["mcp_status"])
        other = json.dumps({"type": "system", "subtype": "api_retry", "mcp_servers": []})
        self.assertIsNone(runner.parse_transcript([other])["mcp_status"])

    def test_no_init_event_keeps_the_outcome(self):
        for arm in ("P", "C"):
            code, rec, _, _ = self.start(arm, fixture=self.fixture_with("ok.jsonl", "", "", drop_first=True))
            self.assertEqual((0, "ok", None), (code, rec["outcome"], rec["mcp_status"]), arm)
        shutil.rmtree(self.folder("P"))
        code, rec, _, _ = self.start("P", fixture=self.fixture_with("ok.jsonl", INIT_SERVERS, '"other":[]'))
        self.assertEqual(("ok", None), (rec["outcome"], rec["mcp_status"]), "an init event with no mcp_servers")


class EnvScrubTest(RunnerCase):
    SCRUB = "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1"

    def test_env_scrub_adds_the_variable(self):
        for arm, extra in (("C", ()), ("C", ("-no-tools",)), ("P", ()), ("PS", ("-aid", "skill")), ("PF", ())):
            cmd = self.dry(arm, *extra, "-env-scrub")
            self.assertIn(self.SCRUB, env_values(cmd), arm)
            self.assertEqual(1, json.dumps(cmd).count("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"))
        code, rec, _, _ = self.start("C", "-env-scrub", fixture=self.c_ok())
        self.assertEqual((0, "ok", True), (code, rec["outcome"], rec["env_scrub"]))
        self.assertEqual(f"{CHALLENGE['id']}__C-scrub__{MODEL}__1", rec["id"])
        self.assertTrue(os.path.isdir(self.folder("C-scrub")))
        self.assertIn(self.SCRUB, env_values(self.runs_of_docker()[0]["argv"]))
        args = runner.plan_args({"question": KEY["question"], "model": MODEL, "arm": "PS", "aid": "skill",
                                 "stop-after-tools": 5, "env-scrub": True}, "b1")
        self.assertTrue(args.env_scrub)
        self.assertEqual(f"{CHALLENGE['id']}__PS-skill-stop-5-scrub__{MODEL}__1", runner.run_id_of(args))

    def test_default_has_no_scrub_variable(self):
        for arm, extra in (("C", ()), ("P", ("-variant", "no-tool-search")), ("PS", ("-aid", "rule")), ("PF", ())):
            self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", json.dumps(self.dry(arm, *extra)), arm)
        code, rec, _, _ = self.start("C", fixture=self.c_ok())
        self.assertEqual((0, False), (code, rec["env_scrub"]))
        self.assertEqual(f"{CHALLENGE['id']}__C__{MODEL}__1", rec["id"])
        self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", json.dumps(self.runs_of_docker()[0]["argv"]))
        self.assertFalse(runner.plan_args({"question": "c", "model": "m", "arm": "C"}, "b1").env_scrub)


class ApiErrorTest(RunnerCase):
    """auth_error.jsonl has the events of Claude Code 2.1.326 with no key (init, the synthetic message, the result)."""
    REASON = "success / api_error / -: Not logged in · Please run /login"

    def test_api_error_result_gives_the_outcome_api_error(self):
        with open(os.path.join(FIXTURES, "auth_error.jsonl"), "rb") as f:
            parsed = runner.parse_transcript(f)
        result = parsed["result"]
        self.assertEqual(("api_error", True), (result["terminal_reason"], result["is_error"]))
        self.assertEqual(({SERVER: "connected"}, {}), (parsed["mcp_status"], parsed["tools"]))
        self.assertEqual("api_error", runner.outcome_of("exit", 1, result, False))
        self.assertEqual("api_error", runner.outcome_of(
            "exit", 1, {"subtype": "error_during_execution", "is_error": True, "terminal_reason": "api_error"}, False))
        self.assertEqual("timeout", runner.outcome_of("timeout", 137, result, False))
        self.assertEqual("stopped", runner.outcome_of("stopped", 137, result, False))
        self.assertEqual("error", runner.outcome_of("exit", 1, {**result, "terminal_reason": "completed"}, False))

    def test_api_error_wins_over_a_failed_mcp_status(self):
        failed = self.fixture_with("auth_error.jsonl", '"status":"connected"', '"status":"failed"')
        code, rec, _, _ = self.start("P", fixture=failed, exit=1)
        self.assertEqual((3, "api_error", {SERVER: "failed"}), (code, rec["outcome"], rec["mcp_status"]))
        self.assertEqual(self.REASON, rec["reason"])
        # Arm C with a server in the init event.
        code, rec, _, _ = self.start("C", fixture="auth_error.jsonl", exit=1)
        self.assertEqual((3, "api_error"), (code, rec["outcome"]))
        # The IDE check at the end and the proxy log do not replace it either.
        self.ide = [(VERSION, None), ("2.1.0", "isDumbMode is True")]
        code, rec, _, _ = self.start("PF", fixture="auth_error.jsonl", exit=1, proxy_status=502)
        self.assertEqual((3, "api_error", "2.1.0"), (code, rec["outcome"], rec["plugin_version_end"]))
        self.assertEqual(self.REASON, rec["reason"])

    def test_run_with_api_error_returns_3_and_names_the_reason(self):
        code, rec, out, err = self.start("P", fixture="auth_error.jsonl", exit=1)
        self.assertEqual((3, "api_error", 1), (code, rec["outcome"], rec["exit_code"]), err)
        self.assertEqual(self.REASON, rec["reason"])
        self.assertEqual((0, 1, None, None), (rec["cost_usd"], rec["turns"], rec["answer"], rec["score"]))
        self.assertIn(f"{rec['id']}: api_error ({self.REASON})", out)
        self.assertTrue(os.path.exists(os.path.join(self.folder("P"), "run.json")), "only the batch sets it aside")
        sentence = "3: the API refused or failed; the run is no measurement"
        self.assertIn(sentence, runner.__doc__)
        self.assertIn(sentence, self.help("run"))
        self.assertIn("3: ", self.help("batch"))

    def help(self, command):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            runner.main([command, "-h"])
        return out.getvalue()

    def test_error_outcome_has_a_reason_from_the_result(self):
        text = "a" * 150 + "b" * 150
        init = json.dumps({"type": "system", "subtype": "init", "mcp_servers": []})
        cases = (({"subtype": "error_during_execution", "is_error": True, "api_error_status": 529, "result": text},
                  "error", "error_during_execution / - / 529: " + text[:200]),
                 ({"subtype": "success", "is_error": True}, "error", "success / - / -: -"),
                 ({"subtype": "success", "is_error": True, "terminal_reason": "api_error", "api_error_status": 401,
                   "result": text}, "api_error", "success / api_error / 401: " + text[:200]))
        for result, outcome, reason in cases:
            path = os.path.join(self.tmp, "error.jsonl")
            write(path, init + "\n" + json.dumps({"type": "result", **result}) + "\n")
            code, rec, _, _ = self.start("C", fixture=path, exit=1)
            self.assertEqual((outcome, reason), (rec["outcome"], rec["reason"]))
            shutil.rmtree(self.folder("C"))
        code, rec, _, _ = self.start("C", fixture=None, exit=125)
        self.assertEqual(("error", "no result event; docker exit code 125"), (rec["outcome"], rec["reason"]))
        shutil.rmtree(self.folder("C"))
        code, rec, _, _ = self.start("C", fixture=self.c_ok())
        self.assertEqual(("ok", None), (rec["outcome"], rec["reason"]))
        os.environ["PATH"] = os.path.join(self.tmp, "no-bin")
        code, rec, _, _ = self.start("C", "-n", "2")
        self.assertEqual("error", rec["outcome"])
        self.assertTrue(rec["reason"].startswith("FileNotFoundError"), "the own reason of the runner stays")


class ParserTest(unittest.TestCase):
    def test_parse_transcript_skips_unknown_events(self):
        tool = lambda i, name, parent=None: json.dumps({"type": "assistant", "parent_tool_use_id": parent, "message": {
            "content": [{"type": "tool_use", "id": i, "name": name, "input": {}}]}})
        lines = ["not json", "[1, 2]", "", json.dumps({"type": "a_new_event", "message": {"content": [
                     {"type": "tool_use", "id": "t0", "name": "Hidden"}]}}),
                 tool("t1", "Bash"), tool("t1", "Bash"), tool("t2", "Read", parent="toolu_agent"),
                 json.dumps({"type": "assistant", "message": {"content": "text only"}}),
                 json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": 7}]}}),
                 json.dumps({"type": "result", "subtype": "success", "num_turns": 1}),
                 json.dumps({"type": "result", "subtype": "success", "num_turns": 2}).encode("utf-8"),
                 b"\xff\xfe"]
        parsed = runner.parse_transcript(lines)
        self.assertEqual(2, parsed["result"]["num_turns"])
        self.assertEqual({"Bash": 1, "Read": 1}, parsed["tools"])
        self.assertEqual(["Bash", "Read"], parsed["first_tools"])
        self.assertEqual({"result": None, "tools": {}, "first_tools": [], "mcp_status": None},
                         runner.parse_transcript([]))

    def test_outcome_of(self):
        ok = {"subtype": "success", "is_error": False}
        self.assertEqual("ok", runner.outcome_of("exit", 0, ok, True))
        self.assertEqual("no_answer", runner.outcome_of("exit", 0, ok, False))
        self.assertEqual("timeout", runner.outcome_of("timeout", 137, ok, True))
        self.assertEqual("stopped", runner.outcome_of("stopped", 137, None, False))
        self.assertEqual("no_answer", runner.outcome_of("exit", 1, None, False))
        self.assertEqual("error", runner.outcome_of("exit", 125, None, False))
        self.assertEqual("budget", runner.outcome_of("exit", 1, {"subtype": "success", "is_error": True,
                                                                  "terminal_reason": "budget_exhausted"}, False))
        self.assertEqual("no_answer", runner.outcome_of(
            "exit", 1, {"subtype": "error_max_structured_output_retries", "is_error": True}, False))
        self.assertEqual("error", runner.outcome_of("exit", 1, {"subtype": "error_during_execution"}, False))
        self.assertEqual("error", runner.outcome_of("exit", 0, {"subtype": "success", "is_error": True}, False))


class BatchTest(CaddyCase):
    def plan(self, *arms, questions=(KEY["question"],), runs=1):
        """A plan file (bench.planfile) of the arm entries, with the model MODEL."""
        path = os.path.join(self.tmp, "plan.json")
        write(path, json.dumps({"rule": "A test plan.", "questions": list(questions), "arms": list(arms),
                                "models": [MODEL], "runs": runs}, indent=2) + "\n")
        return path

    def fake_run(self, codes):
        calls = []

        def run_one(args):
            calls.append(runner.run_id_of(args))
            code, outcome = codes.pop(0) if codes else (0, "ok")
            return self.fake_record(args, code, outcome, f"reason {len(calls)}")
        return calls, run_one

    def fake_record(self, args, code, outcome, reason):
        """What run_one does for a run that writes run.json."""
        folder = os.path.join(self.runs, args.batch, runner.run_id_of(args))
        os.makedirs(folder, exist_ok=True)
        write(os.path.join(folder, "run.json"), json.dumps({"outcome": outcome, "reason": reason}))
        return code, {"outcome": outcome, "reason": reason}

    def listing(self, batch="b1"):
        """The run folders of the batch (not the file plan.json)."""
        folder = os.path.join(self.runs, batch)
        return sorted(name for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name)))

    def test_batch_tries_an_api_error_run_one_more_time(self):
        plan = self.plan({"arm": "C"}, {"arm": "PF"})
        calls, fake = self.fake_run([(3, "api_error"), (0, "ok")])
        with mock.patch.object(runner, "run_one", fake):
            code, out, err = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual(0, code, err)
        self.assertEqual(3, len(calls))
        self.assertEqual(calls[0], calls[1], "the same run again")
        self.assertEqual(sorted([calls[0], calls[0] + ".api-error-1", calls[2]]), self.listing())
        with open(os.path.join(self.runs, "b1", calls[0], "run.json"), encoding="utf-8") as f:
            self.assertEqual("ok", json.load(f)["outcome"])
        self.assertIn(f"{calls[0]}: api_error, moved to {calls[0]}.api-error-1; one more run", out)
        # Each kind has its own second try: an API error, then an invalid run, then the run.
        shutil.rmtree(os.path.join(self.runs, "b1"))
        plan = self.plan({"arm": "C"})
        calls, fake = self.fake_run([(3, "api_error"), (0, "invalid"), (0, "ok")])
        with mock.patch.object(runner, "run_one", fake):
            code, _, _ = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual((0, 3), (code, len(calls)))
        self.assertEqual(sorted([calls[0], calls[0] + ".api-error-1", calls[0] + ".invalid-1"]), self.listing())

    def test_batch_stops_after_two_api_errors_and_leaves_no_run_json(self):
        plan = self.plan({"arm": "C"}, {"arm": "P"}, {"arm": "PF"})
        calls, fake = self.fake_run([(3, "api_error"), (3, "api_error")])
        with mock.patch.object(runner, "run_one", fake):
            code, out, err = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual(3, code)
        self.assertEqual(2, len(calls), "no new run starts")
        self.assertEqual(calls[0], calls[1])
        self.assertEqual([calls[0] + ".api-error-1", calls[0] + ".api-error-2"], self.listing())
        self.assertIn("batch b1: STOPPED after an API error (reason 2)", err)
        # The next start of the batch does the run again.
        calls2, fake = self.fake_run([])
        with mock.patch.object(runner, "run_one", fake):
            code, out, _ = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual(0, code)
        self.assertIn(calls[0], calls2)
        self.assertIn("0 finished before, 3 to run", out)
        # Two workers: 3 wins over 2 (the other run could not start).
        b_started, a_done, a_calls = threading.Event(), threading.Event(), []

        def two(args):
            if args.arm == "C":
                b_started.wait(10)
                a_calls.append(1)
                if len(a_calls) == 2:
                    a_done.set()
                return self.fake_record(args, 3, "api_error", f"reason {len(a_calls)}")
            b_started.set()
            a_done.wait(10)
            return 2, None
        plan = self.plan({"arm": "C"}, {"arm": "PF"})
        with mock.patch.object(runner, "run_one", two):
            code, _, err = self.main("batch", "-plan", plan, "-batch", "b2", "-jobs", "2")
        self.assertEqual(3, code, err)
        self.assertEqual(2, len(a_calls))
        self.assertIn("batch b2: STOPPED after an API error (reason 2)", err)
        self.assertEqual([f"{CHALLENGE['id']}__C__{MODEL}__1.api-error-{k}" for k in (1, 2)], self.listing("b2"))

    def test_batch_skips_a_finished_run(self):
        plan = self.plan({"arm": "C"}, {"arm": "PF"}, {"arm": "PS", "aid": "skill"}, runs=2)
        os.makedirs(self.folder("C"))
        write(os.path.join(self.folder("C"), "run.json"), "{}")
        calls, fake = self.fake_run([])
        with mock.patch.object(runner, "run_one", fake):
            code, out, _ = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual(0, code)
        rest = [f"{CHALLENGE['id']}__{arm}__{MODEL}__{n}" for arm in ("PF", "PS-skill") for n in (1, 2)]
        self.assertEqual(sorted([f"{CHALLENGE['id']}__C__{MODEL}__2"] + rest), sorted(calls))
        self.assertIn("batch b1: 6 runs, 1 finished before, 5 to run", out)

    def test_batch_runs_a_plan_by_name_and_keeps_a_copy_of_the_plan(self):
        plans = os.path.join(self.tmp, "plans")
        path = self.plan({"arm": "C"}, {"arm": "PF"}, runs=2)
        os.makedirs(plans)
        shutil.copy(path, os.path.join(plans, "mini.json"))
        os.unlink(path)
        calls, fake = self.fake_run([])
        with mock.patch.object(planfile, "PLANS", plans), mock.patch.object(runner, "run_one", fake):
            code, out, err = self.main("batch", "-plan", "mini", "-batch", "b1", "-jobs", "1")
        self.assertEqual(0, code, err)
        self.assertEqual(sorted(f"{CHALLENGE['id']}__{arm}__{MODEL}__{n}" for arm in ("C", "PF") for n in (1, 2)),
                         sorted(calls))
        with open(os.path.join(plans, "mini.json"), encoding="utf-8") as f:
            text = f.read()
        with open(os.path.join(self.runs, "b1", "plan.json"), encoding="utf-8") as f:
            self.assertEqual(text, f.read(), "the batch folder has a copy of the plan")
        self.assertEqual(sorted(calls), self.listing())

    def test_batch_runs_again_a_single_run_that_left_an_api_error(self):
        # A single `run` with the outcome api_error writes run.json (exit 3). For a batch it is no finished run.
        plan = self.plan({"arm": "C"}, {"arm": "PF"})
        for arm, outcome in (("C", "api_error"), ("PF", "ok")):
            os.makedirs(self.folder(arm))
            write(os.path.join(self.folder(arm), "run.json"), json.dumps({"outcome": outcome, "reason": "r"}))
        calls, fake = self.fake_run([])
        with mock.patch.object(runner, "run_one", fake):
            code, out, _ = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual(0, code)
        run_c = f"{CHALLENGE['id']}__C__{MODEL}__1"
        self.assertEqual([run_c], calls)
        self.assertIn("1 finished before, 1 to run", out)
        self.assertEqual(sorted([run_c, run_c + ".api-error-1", f"{CHALLENGE['id']}__PF__{MODEL}__1"]),
                         self.listing())

    def test_batch_stops_on_exit_9(self):
        plan = self.plan({"arm": "C"}, {"arm": "P"}, {"arm": "PF"})
        calls, fake = self.fake_run([(9, "key_leak")])
        with mock.patch.object(runner, "run_one", fake):
            code, _, err = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual(9, code)
        self.assertEqual(1, len(calls))
        self.assertIn("key leak", err)

    def test_key_leak_wins_over_api_error(self):
        code, rec, out, err = self.start("P", fixture="auth_error.jsonl", exit=1, print_key=1)
        self.assertEqual((9, "key_leak"), (code, rec["outcome"]))
        self.assertEqual(["run.json"], os.listdir(self.folder("P")))
        self.assertIn("transcript.jsonl", rec["reason"])
        self.assertNotIn(FAKE_KEY, out + err)
        # In a batch: the other worker has a key leak, so the API error run does not start again.
        a_started, b_returned, a_calls = threading.Event(), threading.Event(), []

        def two(args):
            if args.arm == "C":
                a_calls.append(1)
                a_started.set()
                b_returned.wait(10)
                time.sleep(0.5)  # the worker of the other run sets the stop after its run_one returns
                return self.fake_record(args, 3, "api_error", "reason")
            a_started.wait(10)
            b_returned.set()
            return 9, {"outcome": "key_leak", "reason": "leak"}
        plan = self.plan({"arm": "C"}, {"arm": "PF"})
        with mock.patch.object(runner, "run_one", two):
            code, out, err = self.main("batch", "-plan", plan, "-batch", "b3", "-jobs", "2")
        self.assertEqual(9, code)
        self.assertEqual(1, len(a_calls), "no second try after the stop")
        self.assertIn("STOPPED after a key leak", err)
        self.assertNotIn("API error", err)
        self.assertEqual([f"{CHALLENGE['id']}__C__{MODEL}__1.api-error-1"], self.listing("b3"))

    def test_batch_repeats_an_invalid_run_one_time(self):
        plan = self.plan({"arm": "C"})
        calls, fake = self.fake_run([(0, "invalid"), (0, "invalid")])
        with mock.patch.object(runner, "run_one", fake):
            code, _, _ = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual(0, code)
        self.assertEqual(2, len(calls))
        self.assertTrue(os.path.isdir(self.folder("C") + ".invalid-1"))
        self.assertTrue(os.path.exists(os.path.join(self.folder("C"), "run.json")))

    def test_batch_order_keeps_question_and_model_together(self):
        parse = lambda *a: runner._parser().parse_args(
            ["run", "-batch", "b", "-question", a[0], "-model", a[1], "-arm", a[2]])
        runs = [parse(c, m, arm) for c in ("x", "y") for m in ("m1", "m2") for arm in ("C", "P", "PF")]
        order = runner.batch_order(runs, 1)
        keys = [(a.question, a.model) for a in order]
        self.assertEqual([("x", "m1")] * 3 + [("x", "m2")] * 3 + [("y", "m1")] * 3 + [("y", "m2")] * 3, keys)
        self.assertEqual([runner.run_id_of(a) for a in order],
                         [runner.run_id_of(a) for a in runner.batch_order(runs, 1)])
        self.assertNotEqual([a.arm for a in order], [a.arm for a in runs], "seed 1 changes the arm order")

    def test_bad_plan_exits_2_and_starts_no_container(self):
        with open(self.plan({"arm": "C"}), encoding="utf-8") as f:
            good = json.load(f)
        bad = os.path.join(self.tmp, "bad.json")
        cases = [("an unknown question", dict(good, questions=["beets-refs-gone"]),
                  "questions: unknown question 'beets-refs-gone'"),
                 ("an unknown arm", dict(good, arms=[{"arm": "X"}]), "arms: unknown arm 'X'"),
                 ("runs 0", dict(good, runs=0), "runs 0: use a whole number of 1 or more"),
                 ("no model", dict(good, models=[]), "models: no list of one or more model names"),
                 ("an unknown key", dict(good, batch="b2"), "unknown key 'batch'"),
                 ("an option of the batch", dict(good, arms=[{"arm": "C", "plugin-version": "1.0"}]),
                  "arms: unknown key 'plugin-version' in "),
                 ("arm PS with no aid", dict(good, arms=[{"arm": "C"}, {"arm": "PS"}]),
                  "arms: {'arm': 'PS'}: arm PS needs -aid skill or -aid rule"),
                 ("a variant on arm PFG", dict(good, arms=[{"arm": "PFG", "variant": "guide"}]),
                  "arms: {'arm': 'PFG', 'variant': 'guide'}: -variant is for the arms P, PS and PF, not for arm PFG")]
        calls, fake = self.fake_run([])
        with mock.patch.object(runner, "run_one", fake):
            for what, plan, problem in cases:
                with self.subTest(what):
                    write(bad, json.dumps(plan))
                    code, out, err = self.main("batch", "-plan", bad, "-batch", "b1")
                    self.assertEqual((2, ""), (code, out))
                    self.assertIn(f"runner: {bad}: {problem}", err)
            for what, plan, text in (("no JSON", bad, "JSONDecodeError"), ("no file", "absent", "FileNotFoundError")):
                with self.subTest(what):
                    write(bad, "{not json")
                    code, out, err = self.main("batch", "-plan", plan, "-batch", "b1")
                    self.assertEqual((2, ""), (code, out))
                    self.assertIn(f"runner: {plan}: no plan ({text}: ", err)
        self.assertEqual(([], []), (calls, self.docker_calls()), "no run, no container")
        self.assertFalse(os.path.exists(self.runs))
        for option in ({"dry-run": True}, {"plugin-version": "1.0"}, {"batch": "b2"}):
            with self.assertRaises(runner.SetupError):
                runner.plan_args({"question": KEY["question"], "model": MODEL, "arm": "C", **option}, "b1")

    def test_batch_refuses_a_folder_that_holds_another_plan(self):
        plan = self.plan({"arm": "C"})
        calls, fake = self.fake_run([])
        with mock.patch.object(runner, "run_one", fake):
            code, _, err = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual((0, 1), (code, len(calls)), err)
        stored = os.path.join(self.runs, "b1", "plan.json")
        with open(stored, encoding="utf-8") as f:
            text = f.read()
        # A record with the outcome api_error that a single run left: a start that goes on would move its folder.
        os.makedirs(self.folder("PF"))
        write(os.path.join(self.folder("PF"), "run.json"), json.dumps({"outcome": "api_error", "reason": "r"}))
        listing = self.listing()
        for what, stored_text in (("another plan", None), ("no JSON", "{not json")):
            with self.subTest(what):
                if stored_text is not None:
                    write(stored, stored_text)
                before = stored_text or text
                other = self.plan({"arm": "C"}, {"arm": "PF"})
                calls.clear()
                with mock.patch.object(runner, "run_one", fake):
                    code, out, err = self.main("batch", "-plan", other, "-batch", "b1", "-jobs", "1")
                self.assertEqual((2, "", []), (code, out, calls))
                self.assertIn(f"runner: batch b1: {stored} holds another plan; use a new batch name", err)
                with open(stored, encoding="utf-8") as f:
                    self.assertEqual(before, f.read(), "no write")
                self.assertEqual(listing, self.listing(), "no folder moves")
        # The same plan (a resume) runs as before, also when the stored plan has another format.
        write(stored, json.dumps(json.loads(text)))
        plan = self.plan({"arm": "C"})
        calls.clear()
        with mock.patch.object(runner, "run_one", fake):
            code, out, err = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
        self.assertEqual((0, []), (code, calls), err)
        self.assertIn("batch b1: 1 runs, 1 finished before, 0 to run", out)
        with open(stored, encoding="utf-8") as f:
            self.assertEqual(text, f.read())

    def test_batch_takes_the_version_of_the_ide(self):
        self.caddy_args("C")  # the tracked question of caddy
        plan = self.plan({"arm": "C"}, {"arm": "P"}, {"arm": "PF"},
                         questions=(KEY["question"], self.GO_KEY["question"]))
        versions = {runner.IDE_URLS["beets"]: "9.9.9-bench.beets", runner.IDE_URLS["caddy"]: "9.9.9-bench.caddy"}
        runs, reads = [], []

        def run_one(args):
            product = "caddy" if args.question == self.GO_KEY["question"] else "beets"
            runs.append((product, args.plugin_version, len(reads)))  # the expected version, the reads before the run
            return self.fake_record(args, 0, "ok", None)

        def version(url):
            reads.append(url)
            return versions[url]

        def no_version(url):
            raise mcp.McpError("transport", "transport_error: connection refused")

        with mock.patch.object(runner, "run_one", run_one), mock.patch.object(runner, "ide_version", version):
            code, out, err = self.main("batch", "-plan", plan, "-batch", "b1", "-jobs", "1")
            self.assertEqual(0, code, err)
            self.assertEqual([runner.IDE_URLS["beets"], runner.IDE_URLS["caddy"]], reads, "one read for each IDE")
            self.assertEqual([("beets", "9.9.9-bench.beets", 2)] * 3 + [("caddy", "9.9.9-bench.caddy", 2)] * 3, runs,
                             "each planned run gets the version of its product, after the reads")
            self.assertIn("plugin version 9.9.9-bench.beets of the IDE of beets", out)
            self.assertIn("plugin version 9.9.9-bench.caddy of the IDE of caddy", out)
            # With the option, the batch reads no version and each run gets the option.
            runs.clear()
            reads.clear()
            code, _, err = self.main("batch", "-plan", plan, "-batch", "b2", "-jobs", "1", "-plugin-version", "1.2.3")
            self.assertEqual(0, code, err)
            self.assertEqual(([("beets", "1.2.3", 0)] * 3 + [("caddy", "1.2.3", 0)] * 3, []), (runs, reads))
        runs.clear()
        with mock.patch.object(runner, "run_one", run_one), mock.patch.object(runner, "ide_version", no_version):
            code, _, err = self.main("batch", "-plan", plan, "-batch", "b3", "-jobs", "1")
        self.assertEqual(2, code)
        self.assertIn("gives no plugin version", err)
        self.assertEqual([], runs, "no run starts")


class HandshakeTest(RunnerCase):
    def test_handshake_has_no_key_and_removes_route(self):
        os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY
        os.environ["FAKE_DOCKER_EXTRA"] = f"{SERVER}: http://172.17.0.1:29380/r/x/mcp (HTTP) - connected"
        with mock.patch.object(runner, "read_key", side_effect=AssertionError("the handshake reads the key")):
            code, out, err = self.main("handshake", "-product", "beets")
        self.assertEqual(0, code, out + err)
        call = self.runs_of_docker()[0]
        self.assertIsNone(call["key"])
        self.assertNotIn("ANTHROPIC_API_KEY", call["argv"])
        self.assertEqual("/bin/bash", call["argv"][call["argv"].index("--entrypoint") + 1])
        self.assertEqual(FLAGS, call["argv"][1:1 + len(FLAGS)])
        self.assertRegex(call["argv"][-1], "^" + ROUTE_URL + "$")
        self.assertEqual(SERVER, call["argv"][-2])
        route = [c["route"] for c in self.docker_calls() if "route" in c][0]
        self.assertEqual(ROOT, route["project"])
        self.assertEqual({}, self.routes_now())
        self.assertIn("handshake beets: PASS", out)
        self.assertIn('"method": "initialize"', out)


if __name__ == "__main__":
    unittest.main()
