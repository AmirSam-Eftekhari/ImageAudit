import csv
import io
import json
import re
import unittest

from imageaudit.core.config import AuditConfig
from imageaudit.core.engine import AuditEngine
from imageaudit.demo import generate_sample_dataset
from imageaudit.reports.exports import csv_frame
from imageaudit.reports.generator import CSV_KINDS, FORMATS, ReportGenerator

from .helpers import TempCase, make_clean_dataset, textured, write_img


class ReportTests(TempCase):
    def setUp(self):
        super().setUp()
        generate_sample_dataset(self.root / "s")
        self.result = AuditEngine(AuditConfig(use_cache=False)).run(self.root / "s")
        self.gen = ReportGenerator()

    def test_json_report_contains_all_analysis_sections(self):
        data = json.loads(self.gen.generate(self.result, "json"))
        for key in ("dataset", "health", "findings", "statistics", "duplicates", "leakage", "issues"):
            self.assertIn(key, data)
        self.assertNotIn("images", data)
        self.assertIn("images", json.loads(self.gen.generate(self.result, "json", include_images=True)))
        self.assertEqual(data["health"]["overall"], self.result.health["overall"])

    def test_csv_reports_parse_and_match_counts(self):
        for kind in CSV_KINDS:
            rows = list(csv.DictReader(io.StringIO(self.gen.generate(self.result, "csv", csv_kind=kind).decode("utf-8"))))
            expected = {"images": len(self.result.images), "findings": len(self.result.findings),
                        "issues": len(self.result.issues),
                        "duplicates": sum(len(g.members) for g in self.result.duplicates)}[kind]
            self.assertEqual(len(rows), expected, kind)
        images = list(csv.DictReader(io.StringIO(self.gen.generate(self.result, "csv").decode("utf-8"))))
        self.assertRegex(images[0]["width"], r"^\d+$")  # integers, not "320.0"

    def test_csv_neutralises_formula_injection(self):
        make_clean_dataset(self.root / "c", n_train=1, n_val=1, n_test=1)
        write_img(self.root / "c/images/train/=HYPERLINK(1).jpg", textured(77))
        r = AuditEngine(AuditConfig(use_cache=False)).run(self.root / "c")
        df = csv_frame(r, "images")
        self.assertTrue(all(not str(p).startswith("=") for p in df["path"]))

    def test_html_report_is_self_contained_and_complete(self):
        html = self.gen.generate(self.result, "html").decode("utf-8")
        self.assertEqual(re.findall(r"""(?:src|href)=["']https?://""", html), [])
        self.assertNotIn("<script", html)
        for section in ("Dataset overview", "Health score", "Findings", "Class distribution",
                        "Duplicate", "leakage", "Recommend"):
            self.assertIn(section.lower(), html.lower(), section)
        self.assertIn(str(int(self.result.health["overall"])), html)
        self.assertIn("Exact duplicate images across splits", html)

    def test_html_escapes_untrusted_names(self):
        # & and ' are legal in Windows filenames (< > " : | ? * are not) yet are HTML-significant, so
        # this runs on every platform. The escaped form must be present (the name really is rendered)
        # and the raw form must be absent.
        make_clean_dataset(self.root / "x", n_train=1, n_val=1, n_test=1)
        name = "a&b'onerror=alert(1)"
        write_img(self.root / f"x/images/train/{name}.jpg", textured(78))
        r = AuditEngine(AuditConfig(use_cache=False)).run(self.root / "x")
        html = self.gen.generate(r, "html").decode("utf-8")
        self.assertIn("a&amp;b&#39;onerror=alert(1)", html)
        self.assertNotIn(f"{name}.jpg", html)

    def test_html_escapes_tag_in_untrusted_name(self):
        # Original, stronger payload. Windows (and some filesystems) cannot create such a file, so skip there.
        make_clean_dataset(self.root / "x", n_train=1, n_val=1, n_test=1)
        try:
            write_img(self.root / "x/images/train/<img src=x onerror=alert(1)>.jpg", textured(78))
        except OSError as exc:
            self.skipTest(f"filesystem cannot create a filename containing '<' or '>': {exc}")
        r = AuditEngine(AuditConfig(use_cache=False)).run(self.root / "x")
        html = self.gen.generate(r, "html").decode("utf-8")
        self.assertNotIn("<img src=x onerror", html)
        self.assertIn("&lt;img src=x onerror", html)

    def test_pdf_report_is_a_valid_multi_section_pdf(self):
        pdf = self.gen.generate(self.result, "pdf")
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        self.assertGreater(len(pdf), 5000)

    def test_write_creates_files_and_filenames_are_safe(self):
        for fmt in FORMATS:
            p = self.gen.write(self.result, fmt, self.tmp / "out" / f"r.{fmt}")
            self.assertGreater(p.stat().st_size, 0)
        self.assertRegex(self.gen.filename(self.result, "html"), r"^imageaudit-[A-Za-z0-9._-]+\.html$")

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            self.gen.generate(self.result, "docx")


if __name__ == "__main__":
    unittest.main()
