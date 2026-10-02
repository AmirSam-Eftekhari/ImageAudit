import unittest

import cv2

from imageaudit.analyzers.image import ImageAnalyzer
from imageaudit.core.config import AuditConfig, DuplicateConfig
from imageaudit.core.models import ImageRecord
from imageaudit.detectors.duplicates import DuplicateDetector, summarize_duplicates
from imageaudit.detectors.leakage import LeakageDetector

from .helpers import TempCase, textured, write_img


class DetectorCase(TempCase):
    def record(self, name: str, split: str, img=None, data: bytes | None = None) -> ImageRecord:
        p = self.tmp / "imgs" / split / name
        if data is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        else:
            write_img(p, img)
        m = ImageAnalyzer(AuditConfig()).analyze(p)
        return ImageRecord(**m.to_dict(), id=f"{split}/{name}", path=f"{split}/{name}", split=split)

    def detect(self, recs, **cfg):
        return DuplicateDetector(DuplicateConfig(**cfg)).detect(recs)


class DuplicateTests(DetectorCase):
    def test_exact_duplicates_within_split(self):
        a = self.record("a.png", "train", textured(1))
        b = self.record("b.png", "train", data=(self.tmp / "imgs/train/a.png").read_bytes())
        c = self.record("c.png", "train", textured(2))
        groups = self.detect([a, b, c])
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual((g.kind, g.scope, g.splits), ("exact", "within_split", ["train"]))
        self.assertEqual({m.image_id for m in g.members}, {a.id, b.id})
        self.assertEqual(g.unique_files, 1)

    def test_exact_duplicate_across_splits_is_cross_split(self):
        a = self.record("a.png", "train", textured(3))
        b = self.record("a_copy.png", "val", data=(self.tmp / "imgs/train/a.png").read_bytes())
        g = self.detect([a, b])[0]
        self.assertEqual((g.kind, g.scope), ("exact", "cross_split"))
        self.assertEqual(g.splits, ["train", "val"])

    def test_perceptual_duplicate_survives_recompression_and_resize(self):
        img = textured(4, 320, 240)
        a = self.record("orig.jpg", "train", img, )
        small = cv2.resize(img, (200, 150), interpolation=cv2.INTER_AREA)
        b = self.record("re.jpg", "test", small, )
        g = self.detect([a, b])[0]
        self.assertEqual((g.kind, g.scope), ("perceptual", "cross_split"))
        self.assertGreater(g.unique_files, 1)
        self.assertLessEqual(g.max_distance, DuplicateConfig().phash_max_distance)

    def test_distinct_images_are_not_grouped(self):
        recs = [self.record(f"{i}.png", "train", textured(20 + i)) for i in range(6)]
        self.assertEqual(self.detect(recs), [])

    def test_flat_images_never_match_perceptually(self):
        import numpy as np
        a = self.record("f1.png", "train", np.full((64, 64, 3), 100, np.uint8))
        b = self.record("f2.png", "val", np.full((64, 64, 3), 101, np.uint8))
        self.assertEqual(self.detect([a, b]), [])

    def test_flat_identical_files_still_match_exactly(self):
        import numpy as np
        a = self.record("f1.png", "train", np.full((64, 64, 3), 100, np.uint8))
        b = self.record("f2.png", "val", data=(self.tmp / "imgs/train/f1.png").read_bytes())
        self.assertEqual([g.kind for g in self.detect([a, b])], ["exact"])

    def test_disabling_perceptual_detection_keeps_exact(self):
        img = textured(5, 320, 240)
        a = self.record("o.jpg", "train", img)
        b = self.record("s.jpg", "val", cv2.resize(img, (200, 150), interpolation=cv2.INTER_AREA))
        self.assertEqual(self.detect([a, b], enabled=False), [])

    def test_invalid_images_are_excluded(self):
        bad = self.record("bad.jpg", "train", data=b"garbage")
        good = self.record("g.png", "train", textured(6))
        self.assertEqual(self.detect([bad, good]), [])

    def test_group_ids_are_deterministic(self):
        def build():
            a = self.record("a.png", "train", textured(7))
            b = self.record("b.png", "train", data=(self.tmp / "imgs/train/a.png").read_bytes())
            return [g.id for g in self.detect([a, b])]
        self.assertEqual(build(), build())

    def test_summary_counts_redundant_copies_per_split(self):
        a = self.record("a.png", "train", textured(8))
        b = self.record("b.png", "train", data=(self.tmp / "imgs/train/a.png").read_bytes())
        c = self.record("c.png", "train", data=(self.tmp / "imgs/train/a.png").read_bytes())
        s = summarize_duplicates(self.detect([a, b, c]))
        self.assertEqual((s["groups"], s["redundant_within_split"]), (1, 2))


class LeakageTests(DetectorCase):
    def test_no_leakage_when_splits_are_disjoint(self):
        recs = [self.record("a.png", "train", textured(30)), self.record("b.png", "val", textured(31)),
                self.record("c.png", "test", textured(32))]
        lk = LeakageDetector().analyze(self.detect(recs), recs)
        self.assertEqual((lk["cross_split_groups"], lk["leaked_images"], lk["leakage_rate"]), (0, 0, 0.0))
        self.assertTrue(lk["applicable"])

    def test_exact_and_perceptual_leakage_are_distinguished(self):
        img = textured(40, 320, 240)
        tr1 = self.record("t1.jpg", "train", img)
        va = self.record("v1.jpg", "val", data=(self.tmp / "imgs/train/t1.jpg").read_bytes())
        tr2 = self.record("t2.jpg", "train", textured(41, 320, 240))
        te = self.record("e1.jpg", "test", cv2.resize(textured(41, 320, 240), (200, 150), interpolation=cv2.INTER_AREA))
        clean = self.record("v2.jpg", "val", textured(42))
        recs = [tr1, va, tr2, te, clean]
        lk = LeakageDetector().analyze(self.detect(recs), recs)
        self.assertEqual((lk["exact_groups"], lk["perceptual_groups"]), (1, 1))
        pairs = {(p["a"], p["b"]): p for p in lk["pairs"]}
        self.assertEqual(pairs[("train", "val")]["exact_groups"], 1)
        self.assertEqual(pairs[("train", "test")]["perceptual_groups"], 1)
        self.assertEqual(lk["leaked_by_split"], {"val": 1, "test": 1})
        self.assertAlmostEqual(lk["leakage_rate"], 2 / 3)  # 2 leaked of 3 eval images

    def test_within_split_duplicates_are_not_leakage(self):
        a = self.record("a.png", "train", textured(50))
        b = self.record("b.png", "train", data=(self.tmp / "imgs/train/a.png").read_bytes())
        v = self.record("v.png", "val", textured(51))
        lk = LeakageDetector().analyze(self.detect([a, b, v]), [a, b, v])
        self.assertEqual(lk["cross_split_groups"], 0)

    def test_single_split_dataset_is_not_applicable(self):
        recs = [self.record("a.png", "train", textured(60))]
        self.assertFalse(LeakageDetector().analyze([], recs)["applicable"])

    def test_report_states_its_limits(self):
        self.assertIn("not detected", LeakageDetector().analyze([], [])["note"].lower())


if __name__ == "__main__":
    unittest.main()
