"""Reject changed native evaluation code and an unreviewed execution base."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.record_swe_control import (
    WHEEL_EXCLUSIONS,
    RecordedContainer,
    verify_installed_source,
)


class SourceInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source, self.installed = self.root / "source", self.root / "installed"
        for name in [*WHEEL_EXCLUSIONS, "harness/run_evaluation.py"]:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("pass\n")
        target = self.installed / "harness/run_evaluation.py"
        target.parent.mkdir(parents=True)
        target.write_text("pass\n")

    def test_expected_wheel_omissions_are_disclosed(self):
        record = verify_installed_source(self.source, self.installed)
        self.assertEqual(set(record["wheel_omitted_collection_utilities"]), WHEEL_EXCLUSIONS)
        self.assertEqual(set(record["installed_python_files"]), {"harness/run_evaluation.py"})

    def test_changed_grader_is_rejected(self):
        (self.installed / "harness/run_evaluation.py").write_text("raise RuntimeError()\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            verify_installed_source(self.source, self.installed)

    def test_missing_grader_is_rejected(self):
        (self.installed / "harness/run_evaluation.py").unlink()
        with self.assertRaisesRegex(ValueError, "omitted"):
            verify_installed_source(self.source, self.installed)

    def test_injected_python_is_rejected(self):
        (self.installed / "injected.py").write_text("pass\n")
        with self.assertRaisesRegex(ValueError, "unexpected Python"):
            verify_installed_source(self.source, self.installed)


class BaseIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.attrs = {
            "Image": "sha256:reviewed",
            "Config": {"User": "root"},
            "Mounts": [],
            "HostConfig": {
                "NetworkMode": "none",
                "CapAdd": None,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Binds": None,
                "Privileged": False,
                "Memory": 8 * 1024**3,
                "PidsLimit": 512,
            },
        }

    def container(self, *, head=b"reviewed-head\n", dirty=b"", ancestor=0):
        def execute(command, **kwargs):
            if command[1] == "rev-parse":
                return SimpleNamespace(output=head, exit_code=0)
            if command[1] == "status":
                return SimpleNamespace(output=dirty, exit_code=0)
            if command[1] == "merge-base":
                return SimpleNamespace(output=b"", exit_code=ancestor)
            return SimpleNamespace(output=b"upstream environment delta\n", exit_code=0)

        return RecordedContainer(
            SimpleNamespace(
                id="container-id",
                attrs=copy.deepcopy(self.attrs),
                start=lambda: None,
                reload=lambda: None,
                exec_run=execute,
            ),
            self.output,
            "dataset-base",
            "sha256:reviewed",
            "reviewed-head",
        )

    def test_separate_reviewed_image_head_preserves_base_delta(self):
        self.container().start()
        self.assertEqual(
            (self.output / "image-base.diff").read_bytes(), b"upstream environment delta\n"
        )

    def test_changed_or_dirty_initial_tree_is_rejected(self):
        for options in [{"head": b"other\n"}, {"dirty": b" M grader.py"}, {"ancestor": 1}]:
            with self.subTest(options=options), self.assertRaises(RuntimeError):
                self.container(**options).start()

    def test_weakened_container_policy_is_rejected(self):
        changes = [
            ("NetworkMode", "bridge"),
            ("CapAdd", ["SYS_ADMIN"]),
            ("CapDrop", []),
            ("SecurityOpt", []),
            ("Binds", ["/tmp:/host"]),
            ("Privileged", True),
            ("Memory", 0),
            ("PidsLimit", 0),
        ]
        for key, value in changes:
            container = self.container()
            container.container.attrs["HostConfig"][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                container.start()
        mounted = self.container()
        mounted.container.attrs["Mounts"] = [{"Type": "volume", "Destination": "/data"}]
        with self.assertRaises(RuntimeError):
            mounted.start()


if __name__ == "__main__":
    unittest.main()
