"""HTTP-level tests. Skipped unless FastAPI + httpx are installed (pip install -e ".[api,dev]").
"""

import importlib.util
import io
import time
import unittest
import zipfile

from imageaudit.demo import generate_sample_dataset

from .helpers import TempCase

HAVE_API = all(importlib.util.find_spec(m) for m in ("fastapi", "httpx", "multipart"))


@unittest.skipUnless(HAVE_API, "fastapi/httpx/python-multipart not installed")
class RouteTests(TempCase):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient

        from imageaudit.api.app import create_app
        from imageaudit.api.settings import Settings

        generate_sample_dataset(self.tmp / "sample")
        self.app = create_app(Settings(home=self.home, allowed_roots=[]))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def wait_done(self, job_id):
        for _ in range(600):
            j = self.client.get(f"/api/scans/{job_id}").json()
            if j["status"] not in ("queued", "running"):
                return j
            time.sleep(0.1)
        self.fail("scan did not finish")

    def scan(self):
        r = self.client.post("/api/scans", json={"path": str(self.tmp / "sample")})
        self.assertEqual(r.status_code, 202)
        job = self.wait_done(r.json()["id"])
        self.assertEqual(job["status"], "done", job)
        return job["audit_id"]

    def test_health_and_defaults(self):
        h = self.client.get("/api/health").json()
        self.assertEqual((h["status"], h["local_only"]), ("ok", True))
        self.assertIn("quality", self.client.get("/api/config/defaults").json())

    def test_full_flow(self):
        aid = self.scan()
        ov = self.client.get(f"/api/audits/{aid}").json()
        self.assertEqual(ov["statistics"]["totals"]["images_total"], 72)
        imgs = self.client.get(f"/api/audits/{aid}/images", params={"tag": "blurry", "page_size": 5}).json()
        self.assertEqual(imgs["total"], 7)
        iid = imgs["items"][0]["id"]
        self.assertEqual(self.client.get(f"/api/audits/{aid}/images/{iid}").status_code, 200)
        t = self.client.get(f"/api/audits/{aid}/images/{iid}/thumbnail", params={"size": 128})
        self.assertEqual((t.status_code, t.headers["content-type"]), (200, "image/jpeg"))
        self.assertEqual(self.client.get(f"/api/audits/{aid}/leakage").json()["cross_split_groups"], 2)
        self.assertEqual(self.client.get(f"/api/audits/{aid}/duplicates").json()["total"], 5)
        self.assertGreater(self.client.get(f"/api/audits/{aid}/findings", params={"severity": "high"}).json()["total"], 0)
        self.assertGreater(self.client.get(f"/api/audits/{aid}/annotations/issues").json()["total"], 5)
        html = self.client.get(f"/api/audits/{aid}/reports/html", params={"inline": "true"})
        self.assertIn("default-src 'none'", html.headers["content-security-policy"])
        self.assertTrue(self.client.get(f"/api/audits/{aid}/reports/pdf").content.startswith(b"%PDF"))
        self.assertEqual(self.client.delete(f"/api/audits/{aid}").status_code, 204)

    def test_errors_have_a_consistent_shape(self):
        r = self.client.post("/api/scans", json={"path": str(self.tmp / "missing")})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "invalid_path")
        self.assertEqual(self.client.get("/api/audits/unknown-id").json()["error"]["code"], "not_found")
        self.assertEqual(self.client.post("/api/scans", json={}).json()["error"]["code"], "validation_error")
        self.assertEqual(self.client.get("/api/audits/x/images", params={"page": 0}).status_code, 422)

    def test_upload(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for f in (self.tmp / "sample").rglob("*"):
                if f.is_file():
                    zf.write(f, "ds/" + f.relative_to(self.tmp / "sample").as_posix())
        r = self.client.post("/api/scans/upload", files={"file": ("ds.zip", buf.getvalue(), "application/zip")})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(self.wait_done(r.json()["id"])["status"], "done")
        bad = self.client.post("/api/scans/upload", files={"file": ("ds.txt", b"x", "text/plain")})
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
