import unittest

from imageaudit.core.config import AuditConfig, ScoreConfig
from imageaudit.core.models import ImageRecord
from imageaudit.scoring.health import HealthScorer


def rec(i: int, **kw) -> ImageRecord:
    base = dict(id=str(i), path=f"{i}.jpg", split="train", status="ok", width=100, height=100,
                blur_score=500.0, brightness=100.0, contrast=50.0, label_status="ok", tags=[])
    base.update(kw)
    return ImageRecord(**base)


CLEAN_LEAK = {"leakage_rate": 0.0, "applicable": True, "leaked_images": 0, "eval_images": 5}
NO_DUPS = {"redundant_within_split": 0}


def score(images, cfg=None, **kw):
    args = dict(invalid_lines=0, total_lines=10, has_labels=True, class_counts=[5, 5, 5],
                leakage=CLEAN_LEAK, duplicate_summary=NO_DUPS)
    args.update(kw)
    return HealthScorer(cfg or ScoreConfig()).score(images, **args)


def comp(result, key):
    return next(c for c in result["components"] if c["key"] == key)


class HealthScoreTests(unittest.TestCase):
    def test_perfect_dataset_scores_100(self):
        r = score([rec(i) for i in range(10)])
        self.assertEqual(r["overall"], 100.0)
        self.assertEqual(r["grade"], "A")
        self.assertTrue(all(c["score"] == 100.0 for c in r["components"] if c["applicable"]))

    def test_default_weights_sum_to_100(self):
        self.assertAlmostEqual(sum(ScoreConfig().weights.values()), 100.0)

    def test_linear_penalty_reaches_zero_at_zero_at_point(self):
        imgs = [rec(i, status="corrupted") if i < 1 else rec(i) for i in range(20)]  # 5% corrupt
        self.assertEqual(comp(score(imgs), "integrity")["score"], 0.0)
        imgs = [rec(i, status="corrupted") if i < 1 else rec(i) for i in range(40)]  # 2.5% corrupt
        self.assertAlmostEqual(comp(score(imgs), "integrity")["score"], 50.0)

    def test_overall_is_exact_weighted_mean(self):
        imgs = [rec(i, status="corrupted") if i < 1 else rec(i) for i in range(40)]
        r = score(imgs, invalid_lines=1, total_lines=100)  # integrity 50, annotation_validity 80
        expected = (20 * 50 + 20 * 80 + (100 - 40) * 100) / 100
        self.assertAlmostEqual(r["overall"], expected, places=1)

    def test_leakage_drives_component_down(self):
        leak = {**CLEAN_LEAK, "leakage_rate": 0.025, "leaked_images": 1}
        self.assertAlmostEqual(comp(score([rec(i) for i in range(10)], leakage=leak), "leakage")["score"], 50.0)

    def test_not_applicable_components_are_excluded_not_counted_as_perfect(self):
        r = score([rec(i) for i in range(10)], leakage={**CLEAN_LEAK, "applicable": False},
                  total_lines=0, has_labels=False, class_counts=[])
        for key in ("leakage", "annotation_validity", "annotation_coverage", "class_balance"):
            self.assertFalse(comp(r, key)["applicable"])
            self.assertEqual(comp(r, key)["effective_weight"], 0.0)
        self.assertAlmostEqual(sum(c["effective_weight"] for c in r["components"]), 1.0, places=3)

    def test_skipped_duplicate_analysis_is_not_applicable(self):
        r = score([rec(i) for i in range(5)], duplicate_summary={"redundant_within_split": 0, "skipped": True})
        self.assertFalse(comp(r, "duplicates")["applicable"])

    def test_class_imbalance_uses_log_ratio(self):
        r = score([rec(1)], class_counts=[100, 1])  # ratio 100 == zero_at
        self.assertEqual(comp(r, "class_balance")["score"], 0.0)
        r = score([rec(1)], class_counts=[10, 1])  # log(10)/log(100) = 0.5
        self.assertAlmostEqual(comp(r, "class_balance")["score"], 50.0)

    def test_weights_are_configurable(self):
        cfg = AuditConfig().scoring
        cfg.weights = {k: 0.0 for k in cfg.weights} | {"integrity": 1.0}
        imgs = [rec(i, status="corrupted") if i < 1 else rec(i) for i in range(40)]
        self.assertAlmostEqual(score(imgs, cfg=cfg)["overall"], 50.0)

    def test_grade_boundaries(self):
        from imageaudit.scoring.health import _grade
        self.assertEqual([_grade(s) for s in (95, 85, 75, 65, 10)], ["A", "B", "C", "D", "F"])

    def test_every_component_exposes_its_inputs(self):
        for c in score([rec(i) for i in range(5)])["components"]:
            for k in ("key", "label", "description", "weight", "zero_at", "metric", "detail"):
                self.assertIn(k, c)


if __name__ == "__main__":
    unittest.main()
