"""Audit deletion (store, service, HTTP) and the packaging-related path/resource helpers."""

import importlib.util
import os
import sys
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from imageaudit.api.service import AuditService, ImageFilter, NotFound
from imageaudit.api.settings import Settings
from imageaudit.core import paths, resources
from imageaudit.core.store import AuditNotFound, AuditStore
from imageaudit.demo import generate_sample_dataset

from .helpers import TempCase

HAVE_API = all(importlib.util.find_spec(m) for m in ("fastapi", "httpx", "multipart"))


class DeletionCase(TempCase):
    def setUp(self):
        super().setUp()
        generate_sample_dataset(self.tmp / "sample")
        self.svc = AuditService(Settings(home=self.home, allowed_roots=[], static_dir=None))
        self.addCleanup(self.svc.close)

    def wait(self, job, timeout=60):
        end = time.time() + timeout
        while job.status in ("queued", "running") and time.time() < end:
            time.sleep(0.05)
        self.assertEqual(job.status, "done", job.error)
        return job

    def scan(self):
        return self.wait(self.svc.submit_path(str(self.tmp / "sample"))).audit_id

    def files_for(self, aid):
        return sorted(p.name for p in (self.home / "audits").glob(f"{aid}*"))


class ServiceDeletionTests(DeletionCase):
    def test_delete_removes_every_persisted_file_and_thumbnails(self):
        aid = self.scan()
        item = self.svc.image_page(aid, ImageFilter())["items"][0]
        thumb = self.svc.thumbnail(aid, item["id"])
        self.assertTrue(thumb.is_file())
        self.assertEqual(self.files_for(aid), [f"{aid}.json", f"{aid}.meta.json"])
        self.svc.delete_audit(aid)
        self.assertEqual(self.files_for(aid), [])
        self.assertFalse((self.home / "thumbs" / aid).exists())
        self.assertEqual(self.svc.audits(), [])
        with self.assertRaises(NotFound):
            self.svc.overview(aid)

    def test_unrelated_audits_survive(self):
        keep, drop = self.scan(), self.scan()
        self.assertNotEqual(keep, drop)
        self.svc.delete_audit(drop)
        self.assertEqual([a["id"] for a in self.svc.audits()], [keep])
        self.assertEqual(self.svc.overview(keep)["statistics"]["totals"]["images_total"], 72)

    def test_deletion_persists_across_service_restart(self):
        keep, drop = self.scan(), self.scan()
        self.svc.delete_audit(drop)
        self.svc.close()
        again = AuditService(Settings(home=self.home, allowed_roots=[], static_dir=None))
        self.addCleanup(again.close)
        self.assertEqual([a["id"] for a in again.audits()], [keep])
        with self.assertRaises(NotFound):
            again.overview(drop)

    def test_nonexistent_and_repeated_delete_raise_not_found(self):
        with self.assertRaises(NotFound):
            self.svc.delete_audit("doesnotexist")
        aid = self.scan()
        self.svc.delete_audit(aid)
        with self.assertRaises(NotFound):
            self.svc.delete_audit(aid)

    def test_malformed_ids_never_touch_anything_outside_the_audit_directory(self):
        aid = self.scan()
        sentinel = self.home / "precious.json"
        sentinel.write_text("{}")
        for bad in ("../precious", "..\\precious", "a/b", "../../etc", "", "x", "id with space", "a" * 65, "..", "%2e%2e"):
            with self.assertRaises(NotFound, msg=repr(bad)):
                self.svc.delete_audit(bad)
        self.assertTrue(sentinel.is_file())
        self.assertEqual(len(self.svc.audits()), 1)
        self.assertEqual(self.svc.audits()[0]["id"], aid)

    def test_scanned_in_place_dataset_is_never_deleted(self):
        aid = self.scan()
        self.svc.delete_audit(aid)
        self.assertTrue((self.tmp / "sample" / "images").is_dir())
        self.assertTrue(any((self.tmp / "sample").rglob("*.jpg")))

    def test_corrupt_result_file_can_still_be_deleted(self):
        aid = self.scan()
        (self.home / "audits" / f"{aid}.json").write_text("{not json")
        self.svc.delete_audit(aid)  # must not raise
        self.assertEqual(self.files_for(aid), [])

    def test_leftover_tmp_files_are_removed_with_the_audit(self):
        aid = self.scan()
        (self.home / "audits" / f"{aid}.json.tmp").write_text("partial")
        self.svc.delete_audit(aid)
        self.assertEqual(self.files_for(aid), [])

    def test_uploaded_archive_data_is_cleaned_but_other_uploads_stay(self):
        def upload(name):
            z = self.tmp / name
            with zipfile.ZipFile(z, "w") as zf:
                for f in (self.tmp / "sample").rglob("*"):
                    if f.is_file():
                        zf.write(f, "ds/" + f.relative_to(self.tmp / "sample").as_posix())
            return self.wait(self.svc.submit_archive(z, name)).audit_id

        a, b = upload("a.zip"), upload("b.zip")
        uploads = self.home / "uploads"
        self.assertEqual(len(list(uploads.iterdir())), 2)
        self.svc.delete_audit(a)
        self.assertEqual(len(list(uploads.iterdir())), 1)
        self.assertEqual(self.svc.overview(b)["statistics"]["totals"]["images_total"], 72)

    def test_store_rejects_traversal_ids_directly(self):
        store = AuditStore(self.home / "audits")
        for bad in ("../x", "a/b", ""):
            with self.assertRaises(AuditNotFound):
                store.delete(bad)
            with self.assertRaises(AuditNotFound):
                store.exists(bad)


@unittest.skipUnless(HAVE_API, "fastapi/httpx/python-multipart not installed")
class RouteDeletionTests(TempCase):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient

        from imageaudit.api.app import create_app

        generate_sample_dataset(self.tmp / "sample")
        self.client = TestClient(create_app(Settings(home=self.home, allowed_roots=[], static_dir=None)))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def scan(self):
        r = self.client.post("/api/scans", json={"path": str(self.tmp / "sample")})
        self.assertEqual(r.status_code, 202)
        for _ in range(600):
            j = self.client.get(f"/api/scans/{r.json()['id']}").json()
            if j["status"] not in ("queued", "running"):
                self.assertEqual(j["status"], "done", j)
                return j["audit_id"]
            time.sleep(0.1)
        self.fail("scan did not finish")

    def test_create_retrieve_delete_flow_and_status_codes(self):
        keep, drop = self.scan(), self.scan()
        self.assertEqual({a["id"] for a in self.client.get("/api/audits").json()}, {keep, drop})
        self.assertEqual(self.client.get(f"/api/audits/{drop}").status_code, 200)
        r = self.client.delete(f"/api/audits/{drop}")
        self.assertEqual((r.status_code, r.content), (204, b""))
        gone = self.client.get(f"/api/audits/{drop}")
        self.assertEqual((gone.status_code, gone.json()["error"]["code"]), (404, "not_found"))
        self.assertEqual([a["id"] for a in self.client.get("/api/audits").json()], [keep])
        self.assertEqual(self.client.get(f"/api/audits/{keep}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/audits/{drop}/reports/html").status_code, 404)

    def test_delete_nonexistent_and_repeat_return_404_with_error_body(self):
        r = self.client.delete("/api/audits/nosuchaudit")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (404, "not_found"))
        aid = self.scan()
        self.assertEqual(self.client.delete(f"/api/audits/{aid}").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/audits/{aid}").status_code, 404)

    def test_malformed_ids_are_rejected_and_delete_nothing(self):
        aid = self.scan()
        for bad in ("..%2Fcache.sqlite", "..%5Ccache.sqlite", "%2e%2e", "x", "a%20b", "a" * 80):
            self.assertEqual(self.client.delete(f"/api/audits/{bad}").status_code, 404, bad)
        self.assertTrue((self.home / "cache.sqlite").is_file())
        self.assertEqual(self.client.get(f"/api/audits/{aid}").status_code, 200)

    def test_reports_still_work_before_deletion(self):
        aid = self.scan()
        self.assertTrue(self.client.get(f"/api/audits/{aid}/reports/pdf").content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(f"/api/audits/{aid}/reports/html").status_code, 200)


@unittest.skipUnless(HAVE_API, "fastapi/httpx/python-multipart not installed")
class StaticUiTests(TempCase):
    def make_client(self, static_dir):
        from fastapi.testclient import TestClient

        from imageaudit.api.app import create_app

        c = TestClient(create_app(Settings(home=self.home, allowed_roots=[], static_dir=static_dir)))
        c.__enter__()
        self.addCleanup(c.__exit__, None, None, None)
        return c

    def test_ui_is_served_and_api_routes_still_win(self):
        ui = self.tmp / "ui"
        (ui / "images").mkdir(parents=True)
        (ui / "index.html").write_text("<html>home</html>")
        (ui / "images" / "index.html").write_text("<html>images</html>")
        c = self.make_client(ui)
        self.assertIn("home", c.get("/").text)
        self.assertIn("images", c.get("/images/").text)
        self.assertEqual(c.get("/api/health").json()["status"], "ok")
        self.assertEqual(c.get("/api/audits").json(), [])
        self.assertEqual(c.get("/missing").status_code, 404)
        # decoded traversal-style ids must not fall through to the static mount (405) or delete anything
        r = c.delete("/api/audits/..%2Fcache.sqlite")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (404, "not_found"))
        self.assertEqual(c.get("/api/nothing").json()["error"]["code"], "not_found")

    def test_without_a_ui_directory_the_server_is_api_only(self):
        c = self.make_client(None)
        self.assertEqual(c.get("/").status_code, 404)
        self.assertEqual(c.get("/api/health").status_code, 200)


class PathAndResourceTests(TempCase):
    def test_env_override_wins_even_when_frozen(self):
        with mock.patch.dict(os.environ, {"IMAGEAUDIT_HOME": str(self.tmp / "h")}), mock.patch.object(sys, "frozen", True, create=True):
            self.assertEqual(paths.imageaudit_home(), self.tmp / "h")

    def test_frozen_windows_uses_localappdata_not_the_extraction_dir(self):
        env = {k: v for k, v in os.environ.items() if k != "IMAGEAUDIT_HOME"}
        env["LOCALAPPDATA"] = str(self.tmp / "LocalAppData")
        meipass = self.tmp / "_MEI12345"
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(sys, "_MEIPASS", str(meipass), create=True),
            mock.patch.object(sys, "platform", "win32"),
        ):
            home = paths.imageaudit_home()
        self.assertEqual(home, self.tmp / "LocalAppData" / "ImageAudit")
        self.assertTrue(home.is_dir())
        self.assertNotIn(str(meipass), str(home))

    def test_unfrozen_default_is_unchanged(self):
        env = {k: v for k, v in os.environ.items() if k != "IMAGEAUDIT_HOME"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(Path, "home", return_value=self.tmp):
            self.assertEqual(paths.imageaudit_home(), self.tmp / ".imageaudit")

    def test_frontend_dir_resolution(self):
        ui = self.tmp / "bundle" / "frontend"
        ui.mkdir(parents=True)
        (ui / "index.html").write_text("x")
        clean = {k: v for k, v in os.environ.items() if k != "IMAGEAUDIT_STATIC_DIR"}
        with mock.patch.dict(os.environ, clean, clear=True):
            self.assertIsNone(resources.frontend_dir())  # source checkout: API only
            with mock.patch.object(sys, "_MEIPASS", str(self.tmp / "bundle"), create=True):
                self.assertEqual(resources.frontend_dir(), ui)
        with mock.patch.dict(os.environ, {"IMAGEAUDIT_STATIC_DIR": str(ui)}):
            self.assertEqual(resources.frontend_dir(), ui)
        with mock.patch.dict(os.environ, {"IMAGEAUDIT_STATIC_DIR": str(self.tmp / "nope")}):
            self.assertIsNone(resources.frontend_dir())

    def test_desktop_version_flag(self):
        from imageaudit import desktop

        self.assertEqual(desktop.main(["--version"]), 0)


if __name__ == "__main__":
    unittest.main()
