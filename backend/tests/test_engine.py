import copy
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from imageaudit.analyzers.image import ImageAnalyzer
from imageaudit.core.cache import AnalysisCache
from imageaudit.core.config import AuditConfig
from imageaudit.core.engine import STAGES, AuditEngine
from imageaudit.core.errors import DatasetError, ScanCancelled
from imageaudit.core.models import AuditResult
from imageaudit.demo import generate_sample_dataset

from .helpers import TempCase, make_clean_dataset, textured, write_img


class SampleDatasetAudit(unittest.TestCase):
    """Runs the engine once over the generated sample dataset and checks every injected defect."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="imageaudit-sample-"))
        cls.manifest = generate_sample_dataset(cls.tmp / "sample")
        cls.d = cls.manifest["defects"]
        cls.result = AuditEngine(AuditConfig(use_cache=False)).run(cls.tmp / "sample")
        cls.t = cls.result.statistics["totals"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def tagged(self, tag):
        return {i.path for i in self.result.images if tag in i.tags}

    def test_integrity_defects(self):
        sc = self.t["status_counts"]
        self.assertEqual(sc["corrupted"], self.d["corrupted_images"])
        self.assertEqual(sc["zero_byte"], self.d["zero_byte_images"])
        self.assertEqual(sc["unsupported"], self.d["unsupported_images"])
        self.assertEqual(self.t["images_invalid"], 4)

    def test_annotation_defects(self):
        self.assertEqual(self.t["annotation_lines_invalid"], self.d["annotation_error_lines"])
        self.assertEqual(self.t["missing_label_images"], self.d["missing_label_files"])
        self.assertEqual(self.t["empty_label_images"], self.d["empty_label_files"])
        self.assertEqual(self.t["orphan_labels"], self.d["orphan_labels"])
        codes = self.result.statistics["issue_counts"]
        for code in ("malformed_line", "invalid_class_id", "negative_coordinate",
                     "coordinate_out_of_range", "zero_area", "tiny_box", "large_box", "duplicate_annotation"):
            self.assertGreaterEqual(codes.get(code, 0), 1, code)

    def test_every_issue_is_attributed_to_a_file_and_line(self):
        for issue in self.result.issues:
            self.assertTrue(issue.label_path, issue)
            if issue.code in ("malformed_line", "zero_area", "invalid_class_id"):
                self.assertGreaterEqual(issue.line, 1)

    def test_quality_defects(self):
        self.assertTrue({p for p in self.tagged("blurry") if "blurry" in p}.__len__() == self.d["blurry_images"])
        self.assertIn("images/train/train_dark.jpg", self.tagged("dark"))
        self.assertIn("images/train/train_bright.jpg", self.tagged("bright"))
        self.assertIn("images/train/train_lowres.jpg", self.tagged("low_resolution"))
        self.assertIn("images/train/train_panorama.jpg", self.tagged("extreme_aspect"))
        self.assertEqual(self.result.statistics["grayscale_images"], self.d["grayscale_images"])

    def test_duplicate_and_leakage_defects(self):
        groups = self.result.duplicates
        key = lambda scope, kind: [g for g in groups if g.scope == scope and g.kind == kind]  # noqa: E731
        self.assertEqual(len(key("within_split", "exact")), self.d["exact_duplicates_within_train"])
        self.assertEqual(len(key("cross_split", "exact")), self.d["exact_leak_train_val"])
        self.assertEqual(len(key("cross_split", "perceptual")), self.d["near_leak_train_test"])
        self.assertEqual(len(key("within_split", "perceptual")), self.d["near_duplicate_within_train"])
        lk = self.result.leakage
        self.assertEqual((lk["exact_groups"], lk["perceptual_groups"]), (1, 1))
        self.assertEqual(lk["leaked_by_split"], {"val": 1, "test": 1})

    def test_class_imbalance_and_unused_class(self):
        cs = {c["name"]: c["count"] for c in self.result.statistics["classes"]}
        self.assertEqual(cs["star"], 0)
        self.assertGreater(cs["square"], 5 * cs["triangle"])
        self.assertGreater(self.result.statistics["class_balance"]["imbalance_ratio"], 10)

    def test_findings_cover_the_important_problems_with_valid_structure(self):
        titles = " | ".join(f.title.lower() for f in self.result.findings)
        for needle in ("exact duplicate images across splits", "near-duplicate images across splits",
                       "corrupted", "malformed annotation", "blurry", "without a label file",
                       "class imbalance"):
            self.assertIn(needle, titles)
        for f in self.result.findings:
            self.assertIn(f.severity, ("critical", "high", "medium", "low", "info"))
            for field in (f.category, f.title, f.description, f.recommendation):
                self.assertTrue(field)
            self.assertGreater(f.affected_count, 0)
        leak = next(f for f in self.result.findings if f.category == "data_leakage" and "exact" in f.title.lower())
        self.assertEqual(leak.severity, "critical")
        sev = [f.severity for f in self.result.findings]
        order = ["critical", "high", "medium", "low", "info"]
        self.assertEqual(sev, sorted(sev, key=order.index), "findings are sorted most severe first")

    def test_health_score_is_low_and_fully_explained(self):
        h = self.result.health
        self.assertLess(h["overall"], 50)
        self.assertEqual(h["grade"], "F")
        self.assertEqual(len(h["components"]), 8)
        self.assertTrue(all(c["applicable"] for c in h["components"]))

    def test_serialisation_roundtrip_is_lossless(self):
        d = self.result.to_dict()
        back = AuditResult.from_dict(json.loads(json.dumps(d)))
        self.assertEqual(back.to_dict(), d)

    def test_image_ids_are_unique_and_stable(self):
        ids = [i.id for i in self.result.images]
        self.assertEqual(len(ids), len(set(ids)))


class EngineBehaviourTests(TempCase):
    def test_clean_dataset_scores_high_with_no_serious_findings(self):
        make_clean_dataset(self.root, n_train=9, n_val=3, n_test=3)
        r = AuditEngine(AuditConfig(use_cache=False)).run(self.root)
        self.assertGreaterEqual(r.health["overall"], 90, r.health)
        self.assertEqual([f.title for f in r.findings if f.severity in ("critical", "high")], [])

    def test_analysis_is_deterministic(self):
        generate_sample_dataset(self.root / "s")
        cfg = AuditConfig(use_cache=False)
        a = AuditEngine(cfg).run(self.root / "s").to_dict()
        b = AuditEngine(copy.deepcopy(cfg)).run(self.root / "s").to_dict()
        for d in (a, b):
            for k in ("id", "created_at", "duration_s"):
                d.pop(k)
        self.assertEqual(a, b)

    def test_cache_skips_reanalysis_and_invalidates_on_change(self):
        make_clean_dataset(self.root)
        cache = AnalysisCache(self.tmp / "c.sqlite")
        self.addCleanup(cache.close)
        cfg = AuditConfig()
        AuditEngine(cfg, cache=cache).run(self.root)
        with mock.patch.object(ImageAnalyzer, "analyze", autospec=True, side_effect=ImageAnalyzer.analyze) as spy:
            AuditEngine(cfg, cache=cache).run(self.root)
            self.assertEqual(spy.call_count, 0)
            write_img(self.root / "images/train/train_0.jpg", textured(999))
            AuditEngine(cfg, cache=cache).run(self.root)
            self.assertEqual(spy.call_count, 1)

    def test_progress_reports_known_stages_in_order(self):
        make_clean_dataset(self.root)
        seen: list[str] = []
        AuditEngine(AuditConfig(use_cache=False)).run(
            self.root, progress=lambda s, d, t: seen.append(s) if not seen or seen[-1] != s else None)
        self.assertEqual(seen[0], "discover")
        self.assertEqual(seen[-1], "done")
        idx = [STAGES.index(s) for s in seen if s in STAGES]
        self.assertEqual(idx, sorted(idx))

    def test_cancellation(self):
        make_clean_dataset(self.root)
        ev = threading.Event()
        ev.set()
        with self.assertRaises(ScanCancelled):
            AuditEngine(AuditConfig(use_cache=False)).run(self.root, cancel=ev)

    def test_validate_mode_does_not_claim_duplicate_or_leakage_results(self):
        generate_sample_dataset(self.root / "s")
        r = AuditEngine(AuditConfig(use_cache=False)).run(self.root / "s", mode="validate")
        comps = {c["key"]: c for c in r.health["components"]}
        for key in ("duplicates", "leakage", "blur"):
            self.assertFalse(comps[key]["applicable"], key)
        self.assertEqual(r.duplicates, [])
        self.assertGreater(r.statistics["totals"]["annotation_lines_invalid"], 0)
        self.assertTrue(all(i.blur_score is None for i in r.images))

    def test_bad_inputs_raise_clear_errors(self):
        with self.assertRaises(Exception) as cm:
            AuditEngine().run(self.tmp / "does-not-exist")
        self.assertIn("does not exist", str(cm.exception))
        (self.root / "images").mkdir()
        (self.root / "labels").mkdir()
        with self.assertRaises(DatasetError):
            AuditEngine().run(self.root)

    def test_dataset_files_are_never_modified(self):
        generate_sample_dataset(self.root / "s")
        before = {p: p.stat().st_mtime_ns for p in (self.root / "s").rglob("*") if p.is_file()}
        AuditEngine(AuditConfig(use_cache=False)).run(self.root / "s")
        after = {p: p.stat().st_mtime_ns for p in (self.root / "s").rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):
            AuditEngine().run(self.root, mode="fast")


if __name__ == "__main__":
    unittest.main()
