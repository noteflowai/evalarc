"""Exercise patch creation without checking untrusted candidate paths out on the host."""

import io
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.swe_workspace import index_archive, patch, source_path, tree


class PatchTests(unittest.TestCase):
    def test_git_patch_preserves_binary_deletions_and_new_unicode_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "objects.git"
            subprocess.run(
                ["git", "init", "--bare", "--object-format=sha1", str(repository)],
                check=True,
                capture_output=True,
            )

            def snapshot(label, files):
                path = root / (label + ".tar")
                with tarfile.open(path, "w") as archive:
                    for name, data in files.items():
                        info = tarfile.TarInfo("testbed/" + name)
                        info.size = len(data)
                        archive.addfile(info, io.BytesIO(data))
                entries, _ = index_archive(path, repository, ["binary.bin", "old.py"])
                return tree(repository, entries, root / (label + ".index"))

            before = snapshot("before", {"binary.bin": b"\0a", "old.py": b"pass\n"})
            after = snapshot("after", {"binary.bin": b"\0b", "新文件.py": b"x = 2\n"})
            difference = patch(repository, before, after)
            checkout = root / "checkout"
            subprocess.run(
                ["git", "clone", str(repository), str(checkout)], check=True, capture_output=True
            )
            subprocess.run(["git", "read-tree", "--reset", "-u", before], cwd=checkout, check=True)
            subprocess.run(
                ["git", "apply", "--binary", "-"], cwd=checkout, input=difference, check=True
            )
            self.assertEqual((checkout / "binary.bin").read_bytes(), b"\0b")
            self.assertEqual((checkout / "新文件.py").read_bytes(), b"x = 2\n")
            self.assertFalse((checkout / "old.py").exists())

    def test_history_and_untracked_caches_are_excluded_but_tracked_fixtures_remain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "objects.git"
            subprocess.run(
                ["git", "init", "--bare", str(repository)], check=True, capture_output=True
            )
            path = root / "files.tar"
            with tarfile.open(path, "w") as archive:
                for name in [".git/config", "__pycache__/a.pyc", "fixture.pyc"]:
                    info = tarfile.TarInfo("testbed/" + name)
                    info.size = 1
                    archive.addfile(info, io.BytesIO(b"x"))
            entries, removed = index_archive(path, repository, ["fixture.pyc"])
            self.assertEqual(set(entries), {"fixture.pyc"})
            self.assertEqual(set(removed), {".git/config", "__pycache__/a.pyc"})

    def test_path_traversal_and_control_characters_are_rejected(self):
        for name in ["/etc/passwd", "testbed/../outside", "testbed/a\nb", "../testbed/a"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                source_path(name)


if __name__ == "__main__":
    unittest.main()
