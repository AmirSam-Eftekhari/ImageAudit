import os
import unittest
from unittest import mock

from imageaudit.core.config import AuditConfig, ScoreConfig, load_config
from imageaudit.core.errors import ConfigError

from .helpers import TempCase


class ConfigTests(TempCase):
    def write(self, text: str):
        p = self.tmp / "imageaudit.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_defaults_are_valid(self):
        cfg = load_config()
        self.assertEqual(cfg.quality.blur_threshold, 100.0)
        self.assertEqual(cfg.ci.fail_on, "high")

    def test_yaml_overrides_and_partial_weight_merge(self):
        cfg = load_config(self.write("quality:\n  blur_threshold: 42\nscoring:\n  weights:\n    blur: 1\nci:\n  fail_under: 80\n"))
        self.assertEqual(cfg.quality.blur_threshold, 42.0)
        self.assertEqual(cfg.scoring.weights["blur"], 1.0)
        self.assertEqual(cfg.scoring.weights["integrity"], ScoreConfig().weights["integrity"])
        self.assertEqual(cfg.ci.fail_under, 80.0)

    def test_unknown_keys_fail_loudly_with_the_path(self):
        with self.assertRaises(ConfigError) as cm:
            load_config(self.write("quality:\n  blur_treshold: 1\n"))
        self.assertIn("quality.blur_treshold", str(cm.exception))
        with self.assertRaises(ConfigError):
            load_config(self.write("scoring:\n  weights:\n    nonsense: 1\n"))

    def test_wrong_types_and_invalid_values(self):
        for text in ("workers: many\n", "use_cache: 3\n", "ci:\n  fail_on: catastrophic\n",
                     "scoring:\n  zero_at:\n    blur: 0\n", "duplicates:\n  phash_max_distance: 8\n"):
            with self.assertRaises(ConfigError, msg=text):
                load_config(self.write(text))

    def test_invalid_yaml_and_missing_file(self):
        with self.assertRaises(ConfigError):
            load_config(self.write("quality: [unclosed\n"))
        with self.assertRaises(ConfigError):
            load_config(self.tmp / "nope.yaml")

    def test_env_overrides(self):
        with mock.patch.dict(os.environ, {"IMAGEAUDIT_WORKERS": "3", "IMAGEAUDIT_NO_CACHE": "1"}):
            cfg = load_config()
        self.assertEqual((cfg.workers, cfg.use_cache), (3, False))
        with mock.patch.dict(os.environ, {"IMAGEAUDIT_WORKERS": "x"}), self.assertRaises(ConfigError):
            load_config()

    def test_effective_workers_is_bounded(self):
        self.assertEqual(AuditConfig(workers=5).effective_workers(), 5)
        self.assertTrue(1 <= AuditConfig().effective_workers() <= 8)

    def test_overrides_argument(self):
        self.assertEqual(load_config(None, {"quality": {"min_side_px": 10}}).quality.min_side_px, 10)


if __name__ == "__main__":
    unittest.main()
