import datetime
import json
import os
import tempfile
import unittest
from unittest import mock

from common import lock


class LockTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.path = os.path.join(self.tmp, "state", "lock")

    def test_second_lock_is_busy_and_names_the_holder(self):
        with lock.ide_lock("bench.runner batch b1", self.path):
            with open(self.path, encoding="utf-8") as f:
                held = json.load(f)
            self.assertEqual({"pid", "what", "since"}, set(held))
            self.assertEqual((os.getpid(), "bench.runner batch b1"), (held["pid"], held["what"]))
            datetime.datetime.fromisoformat(held["since"])
            with self.assertRaises(lock.Busy) as e:
                with lock.ide_lock("audit.symbols run x", self.path):
                    self.fail("the second lock is held")
            self.assertIn("bench.runner batch b1", str(e.exception))
            self.assertIn(str(os.getpid()), str(e.exception))
            with open(self.path, encoding="utf-8") as f:
                self.assertEqual(held, json.load(f), "the refused lock changes nothing")
        with lock.ide_lock("audit.symbols run x", self.path):
            with open(self.path, encoding="utf-8") as f:
                self.assertEqual("audit.symbols run x", json.load(f)["what"])

    def test_lock_is_free_after_an_exception(self):
        with self.assertRaises(RuntimeError):
            with lock.ide_lock("first", self.path):
                raise RuntimeError("x")
        with lock.ide_lock("second", self.path):
            pass

    def test_default_path_is_below_the_data_root(self):
        with mock.patch.dict(os.environ, {"BENCH_ROOT": self.tmp}):
            with lock.ide_lock("x"):
                self.assertTrue(os.path.isfile(self.path))
                with self.assertRaises(lock.Busy):
                    with lock.ide_lock("y", self.path):
                        pass


if __name__ == "__main__":
    unittest.main()
