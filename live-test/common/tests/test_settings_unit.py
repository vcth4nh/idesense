import os
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

    def test_roots_come_from_the_place_of_the_file(self):
        here = os.path.dirname(os.path.abspath(__file__))
        self.assertEqual(os.path.normpath(os.path.join(here, "..", "..")), settings.live_test_root())
        self.assertEqual(os.path.dirname(settings.live_test_root()), settings.repo_root())
        self.assertTrue(os.path.isfile(os.path.join(settings.repo_root(), "live-test", "run.py")))


if __name__ == "__main__":
    unittest.main()
