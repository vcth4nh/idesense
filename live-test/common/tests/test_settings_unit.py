import os
import shutil
import tempfile
import unittest
from unittest import mock

from common import settings


class SettingsTest(unittest.TestCase):
    def test_defaults_come_from_home(self):
        with mock.patch.dict(os.environ, {"HOME": "/h/x"}, clear=True):
            self.assertEqual(settings.data_root(), "/h/x/dev/idesense-bench")
            self.assertEqual(settings.slots_root(), "/h/x/dev/ws")
            self.assertEqual(settings.login(), "api-key")

    def test_variable_wins_and_must_be_absolute(self):
        with mock.patch.dict(os.environ, {"BENCH_ROOT": "/data/b/"}):
            self.assertEqual(settings.data_root(), "/data/b")
        with mock.patch.dict(os.environ, {"BENCH_ROOT": "rel/b"}):
            with self.assertRaisesRegex(ValueError, "BENCH_ROOT"): settings.data_root()

    def test_secret_file_has_no_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "BENCH_SECRET_FILE"): settings.secret_file()

    def test_login_refuses_an_unknown_kind(self):
        with mock.patch.dict(os.environ, {"BENCH_LOGIN": "x"}):
            with self.assertRaisesRegex(ValueError, "BENCH_LOGIN"): settings.login()

    def test_the_other_variables(self):
        env = {"HOME": "/h/x", "BENCH_SLOTS": "/srv/ws", "BENCH_SECRET_FILE": "/srv/secret",
               "BENCH_LOGIN": "subscription"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(settings.slots_root(), "/srv/ws")
            self.assertEqual(settings.ide_apps(), "/h/x/.local/share/JetBrains/Toolbox/apps")
            self.assertEqual(settings.secret_file(), "/srv/secret")
            self.assertEqual(settings.login(), "subscription")
        with mock.patch.dict(os.environ, {"BENCH_APPS": "/opt/apps", "BENCH_SLOTS": "ws"}):
            self.assertEqual(settings.ide_apps(), "/opt/apps")
            with self.assertRaisesRegex(ValueError, "BENCH_SLOTS"): settings.slots_root()
        with mock.patch.dict(os.environ, {"BENCH_SECRET_FILE": "key.txt"}):
            with self.assertRaisesRegex(ValueError, "BENCH_SECRET_FILE"): settings.secret_file()

    def test_an_empty_variable_counts_as_not_set(self):
        # As ${BENCH_ROOT:-...} in bench/ide/bench-ide.sh.
        env = {"HOME": "/h/x", "BENCH_ROOT": "", "BENCH_SLOTS": "", "BENCH_LOGIN": "", "BENCH_SECRET_FILE": ""}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(settings.data_root(), "/h/x/dev/idesense-bench")
            self.assertEqual(settings.slots_root(), "/h/x/dev/ws")
            self.assertEqual(settings.login(), "api-key")
            with self.assertRaisesRegex(ValueError, "BENCH_SECRET_FILE"): settings.secret_file()

    def test_no_message_shows_the_value_of_the_secret_file_or_the_login(self):
        # A person can set the secret itself in place of the path of its file.
        secret = "sk-ant-FAKE-value"
        with mock.patch.dict(os.environ, {"BENCH_SECRET_FILE": secret}):
            with self.assertRaises(ValueError) as e:
                settings.secret_file()
        self.assertIn("BENCH_SECRET_FILE", str(e.exception))
        self.assertNotIn(secret, str(e.exception))
        with mock.patch.dict(os.environ, {"BENCH_LOGIN": secret}):
            with self.assertRaises(ValueError) as e:
                settings.login()
        self.assertIn("BENCH_LOGIN", str(e.exception))
        self.assertIn("api-key, subscription", str(e.exception))
        self.assertNotIn(secret, str(e.exception))

    def test_the_data_root_and_the_slots_root_are_real_paths(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for name in ("bench", "ws"):
            os.makedirs(os.path.join(d, "real", name))
            os.symlink(os.path.join(d, "real", name), os.path.join(d, name))
        with mock.patch.dict(os.environ, {"BENCH_ROOT": os.path.join(d, "bench"), "BENCH_SLOTS": os.path.join(d, "ws")}):
            self.assertEqual(os.path.join(os.path.realpath(d), "real", "bench"), settings.data_root())
            self.assertEqual(os.path.join(os.path.realpath(d), "real", "ws"), settings.slots_root())

    def test_roots_come_from_the_place_of_the_file(self):
        here = os.path.dirname(os.path.abspath(__file__))
        self.assertEqual(os.path.normpath(os.path.join(here, "..", "..")), settings.live_test_root())
        self.assertEqual(os.path.dirname(settings.live_test_root()), settings.repo_root())
        self.assertTrue(os.path.isfile(os.path.join(settings.repo_root(), "live-test", "run.py")))


if __name__ == "__main__":
    unittest.main()
