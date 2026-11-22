import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from common import manifest, settings
from suite import fleet

GOLAND = {"version": "2026.3", "build": "263.7307.211"}
PYCHARM = {"version": "2026.3.0.1", "build": "263.7307.329"}
OTHER = {"version": "2026.2", "build": "262.1"}  # a GoLand pin that the fake machine does not have


def ide_folder(apps, folder, data_dir, pin):
    """A Toolbox app folder with the product-info.json fields that the manifest reads."""
    os.makedirs(os.path.join(apps, folder), exist_ok=True)
    with open(os.path.join(apps, folder, "product-info.json"), "w", encoding="utf-8") as f:
        json.dump({"name": folder, "version": pin["version"], "buildNumber": pin["build"],
                   "dataDirectoryName": data_dir}, f)


def manifest_file(path, ides):
    """A manifest with the `ides` section and the other sections of the tracked manifest."""
    tracked = manifest.load()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({**tracked, "ides": ides}, f)


def fake_machine(test, folder):
    """For the time of the test: an apps folder (BENCH_APPS) with GoLand and PyCharm below `folder`, and a manifest
    (manifest.PATH) that equals them. Return the path of the manifest; `manifest_file` changes it."""
    apps = os.path.join(folder, "apps")
    ide_folder(apps, "goland", "GoLand2026.3", GOLAND)
    ide_folder(apps, "pycharm", "PyCharm2026.3", PYCHARM)
    path = os.path.join(folder, "manifest.json")
    manifest_file(path, {"goland": GOLAND, "pycharm": PYCHARM})
    for patch in (mock.patch.dict(os.environ, {"BENCH_APPS": apps}), mock.patch.object(manifest, "PATH", path)):
        patch.start()
        test.addCleanup(patch.stop)
    return path


class Machine(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.path = fake_machine(self, self.dir)
        self.apps = os.path.join(self.dir, "apps")

    def warned(self):
        out = io.StringIO()
        manifest.warn(out)
        return out.getvalue()


class WarningsTest(unittest.TestCase):
    def test_an_ide_whose_build_differs_gives_one_line_with_both_builds(self):
        machine = {"goland": {"version": "2026.3.1", "build": "263.9000.5"}, "pycharm": PYCHARM}
        lines = manifest.warnings({"ides": {"goland": GOLAND, "pycharm": PYCHARM}}, machine)
        self.assertEqual(1, len(lines), lines)
        self.assertIn("goland", lines[0])
        self.assertIn("263.7307.211", lines[0])
        self.assertIn("263.9000.5", lines[0])

    def test_an_equal_machine_gives_no_line(self):
        self.assertEqual([], manifest.warnings({"ides": {"goland": GOLAND}}, {"goland": dict(GOLAND)}))

    def test_an_ide_that_the_machine_does_not_have_gives_one_line(self):
        lines = manifest.warnings({"ides": {"goland": GOLAND, "pycharm": PYCHARM}}, {"goland": GOLAND})
        self.assertEqual(1, len(lines), lines)
        self.assertIn("pycharm", lines[0])
        self.assertIn("263.7307.329", lines[0])

    def test_an_ide_of_the_machine_that_the_manifest_does_not_list_gives_no_line(self):
        self.assertEqual([], manifest.warnings({"ides": {"goland": GOLAND}}, {"goland": GOLAND, "pycharm": PYCHARM}))


class MachineIdesTest(Machine):
    def test_only_a_readable_product_info_counts(self):
        os.makedirs(os.path.join(self.apps, "webstorm"))  # no product-info.json
        os.makedirs(os.path.join(self.apps, "phpstorm"))
        with open(os.path.join(self.apps, "phpstorm", "product-info.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        with open(os.path.join(self.apps, "a-file"), "w", encoding="utf-8") as f:
            f.write("not a folder")
        self.assertEqual({"goland": GOLAND, "pycharm": PYCHARM}, manifest.machine_ides(self.apps))

    def test_only_the_fleet_ides_count(self):
        ide_folder(self.apps, "clion", "CLion2026.2", {"version": "2026.2.0.1", "build": "262.8665.321"})
        ide_folder(self.apps, "intellij-idea", "IntelliJIdea2026.3", {"version": "2026.3", "build": "263.7307.200"})
        self.assertEqual(["goland", "intellij-idea", "pycharm"], sorted(manifest.machine_ides(self.apps)))
        self.assertEqual({"IntelliJIdea", "PyCharm", "WebStorm", "GoLand", "PhpStorm", "RustRover"},
                         {ide.selector for ide in fleet.IDES.values()}, "the six fleet IDEs")

    def test_the_default_folder_is_the_setting_and_an_absent_folder_is_empty(self):
        self.assertEqual({"goland": GOLAND, "pycharm": PYCHARM}, manifest.machine_ides())
        self.assertEqual({}, manifest.machine_ides(os.path.join(self.dir, "absent")))

    def test_the_command_prints_the_ides_section_of_this_machine(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, manifest.main(["machine"]))
        self.assertEqual({"goland": GOLAND, "pycharm": PYCHARM}, json.loads(out.getvalue()))


class WarnTest(Machine):
    def test_an_equal_machine_prints_nothing(self):
        self.assertEqual("", self.warned())

    def test_a_difference_prints_one_line(self):
        manifest_file(self.path, {"goland": OTHER, "pycharm": PYCHARM})
        text = self.warned()
        self.assertEqual(1, len(text.splitlines()), text)
        self.assertTrue(text.startswith("manifest: goland: "), text)

    def test_warn_never_raises(self):
        os.remove(self.path)
        text = self.warned()
        self.assertEqual(1, len(text.splitlines()), text)
        self.assertTrue(text.startswith("manifest: "), text)
        for content in ("{not json", "[1]", '{"ides": [1]}', '{"ides": {"goland": {}}}'):
            with self.subTest(content):
                with open(self.path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.assertEqual(1, len(self.warned().splitlines()))
        manifest_file(self.path, {"goland": GOLAND})
        with mock.patch.dict(os.environ, {"BENCH_APPS": os.path.join(self.dir, "absent")}):
            self.assertEqual(1, len(self.warned().splitlines()), "goland is absent")
        with mock.patch.dict(os.environ, {"BENCH_APPS": "relative/apps"}):
            self.assertIn("BENCH_APPS", self.warned())
        closed = io.StringIO()
        closed.close()
        manifest.warn(closed)

    def test_the_default_output_is_stderr(self):
        manifest_file(self.path, {"goland": OTHER})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            manifest.warn()
        self.assertIn("manifest: goland: ", err.getvalue())


class RecordedTest(Machine):
    def test_recorded_holds_the_pins_the_machine_the_repository_and_the_extra(self):
        rec = manifest.recorded(plugin="x")
        tracked = manifest.load(self.path)
        for key in ("ides", "agent", "image", "models"):
            self.assertEqual(tracked[key], rec[key], key)
        self.assertEqual({"goland": GOLAND, "pycharm": PYCHARM}, rec["machine_ides"])
        self.assertEqual({"commit", "dirty"}, set(rec["repository"]))
        self.assertRegex(rec["repository"]["commit"], "^[0-9a-f]{40}$")
        self.assertIsInstance(rec["repository"]["dirty"], bool)
        self.assertEqual("x", rec["plugin"])

    def test_recorded_never_raises(self):
        os.remove(self.path)
        with mock.patch.dict(os.environ, {"BENCH_APPS": "relative/apps"}), \
                mock.patch.object(settings, "repo_root", lambda: os.path.join(self.dir, "no-repository")):
            rec = manifest.recorded(plugin="x")
        self.assertIn("FileNotFoundError", rec["manifest_error"])
        self.assertIn("BENCH_APPS", rec["machine_ides"])
        self.assertEqual({"commit": None, "dirty": None}, rec["repository"])
        self.assertEqual("x", rec["plugin"])

    def test_write_writes_the_record_and_never_raises(self):
        path = os.path.join(self.dir, "out", "manifest.json")
        os.makedirs(os.path.dirname(path))
        manifest.write(path, plugin="x", files={"k": manifest.file_sha256(self.path)})
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual(("x", GOLAND), (rec["plugin"], rec["machine_ides"]["goland"]))
        self.assertRegex(rec["files"]["k"], "^[0-9a-f]{64}$")
        self.assertIsNone(manifest.file_sha256(os.path.join(self.dir, "absent")))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            manifest.write(os.path.join(self.dir, "absent", "manifest.json"), plugin="x")
        self.assertTrue(err.getvalue().startswith("manifest: cannot write "), err.getvalue())


class TrackedManifestTest(unittest.TestCase):
    def test_the_tracked_manifest_has_the_pins(self):
        tracked = manifest.load()
        self.assertEqual({"ides", "agent", "image", "models"}, set(tracked))
        self.assertEqual({"goland", "intellij-idea", "phpstorm", "pycharm", "rustrover", "webstorm"},
                         set(tracked["ides"]), "the Toolbox folders of the six fleet IDEs")
        for name, pin in tracked["ides"].items():
            self.assertEqual({"version", "build"}, set(pin), name)
        self.assertEqual({"name": "claude-code", "version": "2.1.326"}, tracked["agent"])
        self.assertEqual({"base", "node", "go", "uv"}, set(tracked["image"]))
        self.assertTrue(tracked["image"]["base"].startswith("ubuntu:24.04"), tracked["image"]["base"])
        for tool in ("node", "go", "uv"):
            self.assertEqual({"version", "sha256"}, set(tracked["image"][tool]), tool)
            self.assertRegex(tracked["image"][tool]["sha256"], "^[0-9a-f]{64}$", tool)
        self.assertEqual(["claude-haiku-5-5", "claude-opus-5-5"], tracked["models"])
        self.assertEqual(os.path.join(settings.live_test_root(), "manifest.json"), manifest.PATH)


if __name__ == "__main__":
    unittest.main()
