"""Tests the framework-free API service (jobs, queries, thumbnails, uploads, reports).

These run without FastAPI. The HTTP layer itself is covered by test_api_routes.py, which is
skipped automatically when FastAPI is not installed.
"""

import time
import unittest
import zipfile
from io import BytesIO

from PIL import Image

from imageaudit.api.service import AuditService, BadRequest, ImageFilter, NotFound
from imageaudit.api.settings import Settings
from imageaudit.core.errors import ConfigError, SecurityError
from imageaudit.demo import generate_sample_dataset

from .helpers import TempCase


class ServiceCase(TempCase):
    def setUp(self):
        super().setUp()
        generate_sample_dataset(self.tmp / "sample")
        self.svc = AuditService(Settings(home=self.home, allowed_roots=[]))
        self.addCleanup(self.svc.close)

    def wait(self, job, timeout=60):
        end = time.time() + timeout
        while job.status in ("queued", "running") and time.time() < end:
            time.sleep(0.05)
        return job

    def scan(self):
        job = self.wait(self.svc.submit_path(str(self.tmp / "sample")))
        self.assertEqual(job.status, "done", job.error)
        return job.audit_id


class JobTests(ServiceCase):
    def test_scan_job_completes_and_is_persisted(self):
        job = self.svc.submit_path(str(self.tmp / "sample"))
        self.assertIn(job.status, ("queued", "running", "done"))
        self.wait(job)
        self.assertEqual((job.status, job.progress), ("done", 1.0))
        self.assertEqual(self.svc.audits()[0]["id"], job.audit_id)
        self.assertEqual(self.svc.job(job.id).public()["audit_id"], job.audit_id)

    def test_progress_is_monotonic_within_stage_span(self):
        seen = []
        job = self.svc.submit_path(str(self.tmp / "sample"))
        while job.status in ("queued", "running"):
            seen.append(job.progress)
            time.sleep(0.005)
        self.assertEqual(seen, sorted(seen))

    def test_failed_scan_reports_reason(self):
        (self.tmp / "empty").mkdir()
        job = self.wait(self.svc.submit_path(str(self.tmp / "empty")))
        self.assertEqual(job.status, "failed")
        self.assertIn("YOLO", job.error.upper())

    def test_bad_requests_rejected_synchronously(self):
        with self.assertRaises(SecurityError):
            self.svc.submit_path(str(self.tmp / "missing"))
        with self.assertRaises(ConfigError):
            self.svc.submit_path(str(self.tmp / "sample"), config={"quality": {"bogus": 1}})
        with self.assertRaises(BadRequest):
            self.svc.submit_path(str(self.tmp / "sample"), mode="fast")

    def test_allowed_roots_enforced(self):
        svc = AuditService(Settings(home=self.tmp / "h2", allowed_roots=[self.tmp / "sample"]))
        self.addCleanup(svc.close)
        (self.tmp / "other").mkdir()
        with self.assertRaises(SecurityError):
            svc.submit_path(str(self.tmp / "other"))

    def test_config_override_changes_analysis(self):
        job = self.wait(self.svc.submit_path(str(self.tmp / "sample"), config={"quality": {"blur_threshold": 0.001}}))
        ov = self.svc.overview(job.audit_id)
        self.assertEqual(ov["statistics"]["quality"]["flag_counts"]["blurry"], 0)

    def test_unknown_job_and_audit(self):
        with self.assertRaises(NotFound):
            self.svc.job("nope")
        with self.assertRaises(NotFound):
            self.svc.overview("nope-nope")
        with self.assertRaises(NotFound):
            self.svc.overview("../../etc/passwd")


class QueryTests(ServiceCase):
    def setUp(self):
        super().setUp()
        self.aid = self.scan()

    def page(self, **kw):
        return self.svc.image_page(self.aid, ImageFilter(**kw))

    def test_overview_contains_real_metrics(self):
        ov = self.svc.overview(self.aid)
        self.assertEqual(ov["statistics"]["totals"]["images_total"], 72)
        self.assertEqual(ov["dataset"]["format"], "yolo")
        self.assertEqual(ov["findings"][0]["severity"], "critical")
        self.assertNotIn("images", ov)

    def test_pagination_and_totals(self):
        p = self.page(page_size=10, page=2)
        self.assertEqual((p["total"], len(p["items"]), p["page"]), (72, 10, 2))
        self.assertEqual(len(self.page(page_size=1000)["items"]), 72)  # clamped to MAX_PAGE_SIZE (200)

    def test_filters(self):
        self.assertEqual(self.page(split="val")["total"], 11)
        self.assertEqual(self.page(tags=["blurry"])["total"], 7)
        self.assertEqual(self.page(tags=["missing_label"])["total"], 4)
        self.assertEqual(self.page(tags=["cross_split_leak"])["total"], 4)  # both sides of 2 groups
        self.assertEqual(self.page(tags=["error"], split="train")["total"] >= 4, True)
        self.assertEqual(self.page(status="corrupted")["total"], 2)
        self.assertEqual(self.page(q="blurry")["total"], 4)
        self.assertEqual(self.page(tags=["blurry"], split="val")["total"], 1)
        self.assertGreater(self.page(class_name="triangle")["total"], 0)
        self.assertEqual(self.page(max_width=100)["total"], 1)  # the low-res image
        with self.assertRaises(BadRequest):
            self.page(class_name="unicorn")
        with self.assertRaises(BadRequest):
            self.page(sort="nonsense")

    def test_duplicate_tag_filter_and_finding_filter(self):
        self.assertGreaterEqual(self.page(tags=["duplicate"])["total"], 6)
        f = next(f for f in self.svc.findings(self.aid)["items"] if "Corrupted" in f["title"])
        self.assertEqual(self.page(finding=f["id"])["total"], f["affected_count"])
        with self.assertRaises(NotFound):
            self.page(finding="nope")

    def test_sorting(self):
        p = self.page(sort="blur", order="asc", page_size=5)
        scores = [i["blur_score"] for i in p["items"]]
        self.assertEqual(scores, sorted(scores))
        d = self.page(sort="size", order="desc", page_size=5)["items"]
        self.assertEqual([i["file_size"] for i in d], sorted((i["file_size"] for i in d), reverse=True))

    def test_image_detail_has_boxes_issues_and_duplicates(self):
        target = next(i for i in self.page(q="train_010")["items"])
        d = self.svc.image_detail(self.aid, target["id"])
        self.assertTrue(d["boxes"])
        self.assertTrue(all("class_name" in b for b in d["boxes"]))
        self.assertGreaterEqual(len(d["issues"]), 6)
        self.assertEqual(len(d["sha256"]), 64)
        dup = self.svc.image_detail(self.aid, self.page(q="val_leak_exact")["items"][0]["id"])
        self.assertEqual(dup["duplicate_groups"][0]["scope"], "cross_split")
        with self.assertRaises(NotFound):
            self.svc.image_detail(self.aid, "unknown")

    def test_issues_duplicates_leakage_findings(self):
        self.assertEqual(self.svc.issues_page(self.aid, code="malformed_line")["total"], 2)
        self.assertGreater(self.svc.issues_page(self.aid, level="error")["total"], 5)
        d = self.svc.duplicates_page(self.aid, scope="cross_split")
        self.assertEqual(d["total"], 2)
        self.assertEqual(d["items"][0]["kind"], "exact")
        self.assertEqual(self.svc.duplicates_page(self.aid, kind="perceptual")["total"], 2)
        lk = self.svc.leakage(self.aid)
        self.assertEqual({(p["a"], p["b"]) for p in lk["pairs"]}, {("train", "val"), ("train", "test")})
        self.assertNotIn("leaked_image_ids", lk)
        fs = self.svc.findings(self.aid, severity="critical")
        self.assertEqual(fs["total"], 1)
        self.assertEqual(self.svc.findings(self.aid, class_name="star")["total"] >= 1, True)
        with self.assertRaises(BadRequest):
            self.svc.findings(self.aid, severity="apocalyptic")

    def test_thumbnails_are_real_bounded_jpegs_and_cached(self):
        item = self.page(q="train_000")["items"][0]
        p = self.svc.thumbnail(self.aid, item["id"], 128)
        with Image.open(p) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertLessEqual(max(im.size), 128)
        self.assertEqual(self.svc.thumbnail(self.aid, item["id"], 128), p)
        bad = self.page(status="corrupted")["items"][0]
        with self.assertRaises(NotFound):
            self.svc.thumbnail(self.aid, bad["id"])

    def test_thumbnail_never_reads_outside_dataset_root(self):
        loaded = self.svc._load(self.aid)
        rec = next(iter(loaded.by_id.values()))
        secret = self.tmp / "secret.jpg"
        Image.new("RGB", (8, 8)).save(secret)
        rec.path = "../secret.jpg"
        with self.assertRaises(NotFound):
            self.svc.thumbnail(self.aid, rec.id)

    def test_reports_via_service(self):
        for fmt, magic in (("html", b"<!"), ("json", b"{"), ("pdf", b"%PDF"), ("csv", b"id,")):
            data, ctype, name = self.svc.report(self.aid, fmt)
            self.assertTrue(data.startswith(magic) or magic in data[:20], fmt)
            self.assertTrue(name.endswith(fmt))
        with self.assertRaises(BadRequest):
            self.svc.report(self.aid, "docx")
        with self.assertRaises(BadRequest):
            self.svc.report(self.aid, "csv", csv_kind="../../x")

    def test_delete_audit(self):
        self.svc.delete_audit(self.aid)
        self.assertEqual(self.svc.audits(), [])
        with self.assertRaises(NotFound):
            self.svc.overview(self.aid)


class UploadTests(ServiceCase):
    def make_zip(self, name="ds.zip"):
        p = self.tmp / name
        with zipfile.ZipFile(p, "w") as zf:
            for f in (self.tmp / "sample").rglob("*"):
                if f.is_file():
                    zf.write(f, "ds/" + f.relative_to(self.tmp / "sample").as_posix())
        return p

    def test_uploaded_archive_is_extracted_scanned_and_cleaned_up(self):
        z = self.make_zip()
        job = self.wait(self.svc.submit_archive(z, "ds.zip"))
        self.assertEqual(job.status, "done", job.error)
        self.assertFalse(z.exists(), "temp archive must be deleted")
        ov = self.svc.overview(job.audit_id)
        self.assertEqual(ov["statistics"]["totals"]["images_total"], 72)
        self.assertEqual(ov["dataset"]["name"], "ds")
        item = self.svc.image_page(job.audit_id, ImageFilter(q="train_000"))["items"][0]
        self.assertTrue(self.svc.thumbnail(job.audit_id, item["id"]).is_file())
        self.assertTrue(any((self.home / "uploads").iterdir()))
        self.svc.delete_audit(job.audit_id)
        self.assertFalse(any((self.home / "uploads").iterdir()))

    def test_malicious_archive_fails_the_job_without_writing_outside(self):
        p = self.tmp / "evil.zip"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("../../evil.txt", "x")
        job = self.wait(self.svc.submit_archive(p, "evil.zip"))
        self.assertEqual(job.status, "failed")
        self.assertIn("traversal", job.error.lower())
        self.assertFalse((self.tmp.parent / "evil.txt").exists())
        self.assertFalse(p.exists())

    def test_non_zip_upload_fails_cleanly(self):
        p = self.tmp / "x.zip"
        BytesIO()
        p.write_bytes(b"nope")
        job = self.wait(self.svc.submit_archive(p, "x.zip"))
        self.assertEqual(job.status, "failed")


if __name__ == "__main__":
    unittest.main()
