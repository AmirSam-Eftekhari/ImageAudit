import io
import stat
import unittest
import zipfile
from pathlib import Path

from imageaudit.core.errors import SecurityError
from imageaudit.core.security import (
    find_dataset_root,
    resolve_within,
    safe_extract_zip,
    validate_dataset_path,
)

from .helpers import TempCase


def make_zip(path: Path, entries: dict[str, bytes], symlink: str | None = None) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
    return path


class ArchiveSafetyTests(TempCase):
    def extract(self, zpath, **kw):
        return safe_extract_zip(zpath, self.tmp / "out", **kw)

    def test_normal_archive_extracts_and_wrapper_dir_is_unwrapped(self):
        z = make_zip(self.tmp / "a.zip", {"ds/images/train/a.jpg": b"x", "ds/data.yaml": b"names: [a]"})
        root = self.extract(z)
        self.assertEqual(root.name, "ds")
        self.assertTrue((root / "images/train/a.jpg").is_file())

    def test_path_traversal_rejected(self):
        for name in ("../evil.txt", "a/../../evil.txt", "..\\evil.txt"):
            z = make_zip(self.tmp / "t.zip", {name: b"x"})
            with self.assertRaises(SecurityError, msg=name):
                self.extract(z)
            self.assertFalse((self.tmp / "evil.txt").exists())

    def test_absolute_and_drive_paths_rejected(self):
        for name in ("/etc/evil", "C:/evil.txt"):
            with self.assertRaises(SecurityError, msg=name):
                self.extract(make_zip(self.tmp / "t.zip", {name: b"x"}))

    def test_symlink_entries_rejected(self):
        with self.assertRaises(SecurityError):
            self.extract(make_zip(self.tmp / "s.zip", {"a.txt": b"x"}, symlink="link"))

    def test_too_many_entries_rejected(self):
        z = make_zip(self.tmp / "m.zip", {f"f{i}.txt": b"x" for i in range(20)})
        with self.assertRaises(SecurityError):
            self.extract(z, max_files=10)

    def test_size_limits_use_actual_bytes(self):
        z = make_zip(self.tmp / "big.zip", {"a.bin": bytes(range(256)) * 2000})
        with self.assertRaises(SecurityError):
            self.extract(z, max_member_bytes=1000)
        with self.assertRaises(SecurityError):
            self.extract(z, max_total_bytes=1000)

    def test_zip_bomb_compression_ratio_rejected(self):
        z = make_zip(self.tmp / "bomb.zip", {"zeros.bin": bytes(20 * 1024 * 1024)})
        with self.assertRaises(SecurityError) as cm:
            self.extract(z)
        self.assertIn("compression", str(cm.exception).lower())

    def test_not_a_zip(self):
        p = self.tmp / "x.zip"
        p.write_bytes(b"not a zip")
        with self.assertRaises(SecurityError):
            self.extract(p)

    def test_dataset_layout_dirs_are_not_unwrapped(self):
        (self.tmp / "d" / "images").mkdir(parents=True)
        self.assertEqual(find_dataset_root(self.tmp / "d"), self.tmp / "d")


class PathValidationTests(TempCase):
    def test_valid_directory(self):
        self.assertEqual(validate_dataset_path(self.root, allowed_roots=[]), self.root.resolve())

    def test_rejects_missing_file_empty_and_nul(self):
        f = self.tmp / "f.txt"
        f.write_text("x")
        for bad in (self.tmp / "missing", f, "", "  ", "a\x00b"):
            with self.assertRaises(SecurityError, msg=repr(bad)):
                validate_dataset_path(bad, allowed_roots=[])

    def test_allow_list_enforced(self):
        inside = self.root / "sub"
        inside.mkdir()
        self.assertEqual(validate_dataset_path(inside, allowed_roots=[self.root]), inside.resolve())
        with self.assertRaises(SecurityError):
            validate_dataset_path(self.tmp, allowed_roots=[self.root])
        with self.assertRaises(SecurityError):  # sibling with a common string prefix
            (self.tmp / "dataset-evil").mkdir()
            validate_dataset_path(self.tmp / "dataset-evil", allowed_roots=[self.root])

    def test_resolve_within_blocks_escape(self):
        with self.assertRaises(SecurityError):
            resolve_within(self.root, "../outside.jpg")
        self.assertEqual(resolve_within(self.root, "a/b.jpg"), (self.root / "a/b.jpg").resolve())


if __name__ == "__main__":
    io  # noqa: B018
    unittest.main()
