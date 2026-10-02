import os
import unittest

from imageaudit.core.config import AnnotationConfig
from imageaudit.core.errors import DatasetError
from imageaudit.datasets.registry import detect_adapter
from imageaudit.datasets.yolo import YoloAdapter

from .helpers import TempCase, make_clean_dataset, textured, write_img, write_label, write_yaml


class YoloAdapterTests(TempCase):
    def discover(self):
        adapter = detect_adapter(self.root)
        return adapter, adapter.discover(self.root)

    def test_standard_layout_with_yaml(self):
        make_clean_dataset(self.root)
        adapter, layout = self.discover()
        self.assertIsInstance(adapter, YoloAdapter)
        self.assertEqual(layout.info.format, "yolo")
        self.assertEqual(layout.info.class_names, ["square", "circle", "triangle"])
        self.assertEqual(layout.info.splits, ["train", "val", "test"])
        self.assertEqual(len(layout.samples), 10)
        self.assertEqual({s.split for s in layout.samples}, {"train", "val", "test"})

    def test_split_first_layout_without_yaml_and_valid_alias(self):
        for split in ("train", "valid"):
            write_img(self.root / split / "images" / "a.jpg", textured(1))
            (self.root / split / "labels").mkdir(parents=True)
            (self.root / split / "labels" / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n")
        _, layout = self.discover()
        self.assertEqual(sorted({s.split for s in layout.samples}), ["train", "val"])
        self.assertTrue(any("No class names" in n for n in layout.info.notes))

    def test_missing_and_orphan_labels(self):
        make_clean_dataset(self.root, n_train=3, n_val=1, n_test=1)
        (self.root / "labels/train/train_0.txt").unlink()
        write_label(self.root, "train", "ghost", "0 0.5 0.5 0.2 0.2\n")
        adapter, layout = self.discover()
        by_name = {s.rel_path: s for s in layout.samples}
        parsed = adapter.read_annotations(by_name["images/train/train_0.jpg"], layout, AnnotationConfig())
        self.assertEqual(parsed.status, "missing")
        names = {p.name for p in layout.label_files}
        self.assertIn("ghost.txt", names)
        tracked = {s.label_path.name for s in layout.samples if s.label_path}
        self.assertNotIn("ghost.txt", tracked)

    def test_unsupported_files_are_listed_not_ignored(self):
        make_clean_dataset(self.root, n_train=1, n_val=1, n_test=1)
        (self.root / "images/train/readme.gif").write_bytes(b"GIF89a")
        _, layout = self.discover()
        flagged = [s for s in layout.samples if s.unsupported]
        self.assertEqual([s.rel_path for s in flagged], ["images/train/readme.gif"])

    def test_yaml_paths_escaping_root_are_ignored(self):
        make_clean_dataset(self.root, n_train=1, n_val=1, n_test=1)
        (self.root / "data.yaml").write_text(
            "train: ../../etc\nval: /tmp\nnames: [a, b, c]\n", encoding="utf-8")
        _, layout = self.discover()  # falls back to folder inference; never reads outside root
        for s in layout.samples:
            self.assertTrue(str(s.path).startswith(str(self.root.resolve())))

    def test_symlink_pointing_outside_root_is_not_followed(self):
        make_clean_dataset(self.root, n_train=1, n_val=1, n_test=1)
        outside = self.tmp / "outside"
        write_img(outside / "secret.jpg", textured(99))
        link = self.root / "images" / "train" / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not permitted on this platform")
        _, layout = self.discover()
        self.assertFalse(any("secret" in s.rel_path for s in layout.samples))

    def test_non_dataset_directory_raises_clear_error(self):
        (self.root / "random.txt").write_text("x")
        with self.assertRaises(DatasetError) as cm:
            detect_adapter(self.root)
        self.assertIn("YOLO", str(cm.exception).upper())

    def test_names_as_list_and_dict_forms(self):
        make_clean_dataset(self.root, n_train=1, n_val=1, n_test=1)
        (self.root / "data.yaml").write_text("train: images/train\nval: images/val\nnames: [x, y]\n")
        self.assertEqual(self.discover()[1].info.class_names, ["x", "y"])
        write_yaml(self.root)
        self.assertEqual(self.discover()[1].info.class_names, ["square", "circle", "triangle"])


if __name__ == "__main__":
    unittest.main()
