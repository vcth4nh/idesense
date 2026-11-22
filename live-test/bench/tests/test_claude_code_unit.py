"""Unit tests of bench/claude_code.py. No test reads a real key file: each key file is a temporary file with a made-up
value."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from bench import claude_code


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class KeyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="claude-code-test-")
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_read_key_refuses_two_lines(self):
        path = os.path.join(self.tmp, "k2")
        write(path, "  sk-one  \n")
        self.assertEqual("sk-one", claude_code.read_key(path))
        for text in ("sk-one\nsk-two\n", "", " \n\t\n"):
            write(path, text)
            with self.assertRaises(claude_code.KeyFileError) as e:
                claude_code.read_key(path)
            self.assertNotIn("sk-", str(e.exception))
        with self.assertRaises(claude_code.KeyFileError):
            claude_code.read_key(os.path.join(self.tmp, "absent"))

    def test_a_message_of_the_default_key_file_names_the_variable_and_not_its_value(self):
        value = os.path.join(self.tmp, "sk-ant-FAKE-value")
        with mock.patch.dict(os.environ, {"BENCH_SECRET_FILE": value}):
            with self.assertRaises(claude_code.KeyFileError) as e:
                claude_code.read_key()
        self.assertIn("BENCH_SECRET_FILE", str(e.exception))
        self.assertNotIn("sk-ant", str(e.exception))


class SecretEnvTest(unittest.TestCase):
    """`secret_env` by the login kind (BENCH_LOGIN), with a temporary secret file (BENCH_SECRET_FILE)."""
    KEY = "sk-fake-api-key-0123456789-test-only"
    TOKEN = "sk-fake-oauth-token-0123456789-test-only"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="claude-code-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = os.path.join(self.tmp, "secret")
        env = mock.patch.dict(os.environ, {"BENCH_SECRET_FILE": self.path})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("BENCH_LOGIN", None)

    def test_no_login_is_the_api_key(self):
        write(self.path, self.KEY + "\n")
        self.assertEqual(("ANTHROPIC_API_KEY", self.KEY), claude_code.secret_env())
        os.environ["BENCH_LOGIN"] = "api-key"
        self.assertEqual(("ANTHROPIC_API_KEY", self.KEY), claude_code.secret_env())

    def test_subscription_is_the_oauth_token(self):
        write(self.path, self.TOKEN + "\n")
        os.environ["BENCH_LOGIN"] = "subscription"
        self.assertEqual(("CLAUDE_CODE_OAUTH_TOKEN", self.TOKEN), claude_code.secret_env())

    def test_empty_file_is_a_value_error(self):
        write(self.path, "")
        for login in ("api-key", "subscription"):
            os.environ["BENCH_LOGIN"] = login
            with self.assertRaises(ValueError, msg=login):
                claude_code.secret_env()


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
        parsed = claude_code.parse_transcript(lines)
        self.assertEqual(2, parsed["result"]["num_turns"])
        self.assertEqual({"Bash": 1, "Read": 1}, parsed["tools"])
        self.assertEqual(["Bash", "Read"], parsed["first_tools"])
        self.assertEqual({"result": None, "tools": {}, "first_tools": [], "mcp_status": None},
                         claude_code.parse_transcript([]))


if __name__ == "__main__":
    unittest.main()
