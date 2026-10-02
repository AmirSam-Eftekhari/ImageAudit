"""End-to-end smoke test of a *built* ImageAudit executable (stdlib only).

    python packaging/smoke_test.py dist/ImageAudit.exe --dataset examples/sample_dataset

It launches the binary from an empty working directory with an isolated data directory, then
exercises the real UI + API: static assets, a scan, results, HTML/PDF/CSV reports, an archive
upload, deletion, a restart and persistence. Exits non-zero on the first failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

HOST = "127.0.0.1"


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return int(s.getsockname()[1])


class Failure(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        raise Failure(msg)


def http(method: str, url: str, body: bytes | None = None, headers: dict | None = None, timeout: float = 60):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def jget(url: str):
    s, _, b = http("GET", url)
    return s, (json.loads(b) if b else None)


class App:
    def __init__(self, exe: Path, env: dict, cwd: Path):
        self.exe, self.env, self.cwd = exe, env, cwd
        self.proc: subprocess.Popen | None = None
        self.port = 0

    @property
    def base(self) -> str:
        return f"http://{HOST}:{self.port}"

    def start(self) -> None:
        self.port = free_port()
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        self.proc = subprocess.Popen([str(self.exe), "--no-browser", "--port", str(self.port)], cwd=self.cwd,
                                     env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
        deadline = time.time() + 90
        while time.time() < deadline:
            if self.proc.poll() is not None:
                out = self.proc.stdout.read().decode(errors="replace") if self.proc.stdout else ""
                raise Failure(f"executable exited early with code {self.proc.returncode}: {out[-2000:]}")
            try:
                if http("GET", self.base + "/api/health", timeout=2)[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.3)
        raise Failure("executable did not become healthy within 90s")

    def stop(self) -> None:
        if not self.proc:
            return
        if sys.platform == "win32":  # onefile = bootloader + child; kill the whole tree
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True, check=False)
        else:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = None


def scan(app: App, dataset: Path) -> str:
    s, _, b = http("POST", app.base + "/api/scans", json.dumps({"path": str(dataset)}).encode(),
                   {"Content-Type": "application/json"})
    check(s == 202, "POST /api/scans accepted (202)")
    return wait_job(app, json.loads(b)["id"])


def wait_job(app: App, job_id: str) -> str:
    deadline = time.time() + 300
    while time.time() < deadline:
        _, j = jget(f"{app.base}/api/scans/{job_id}")
        if j["status"] not in ("queued", "running"):
            check(j["status"] == "done", f"scan job finished with status {j['status']} {j.get('error') or ''}")
            return j["audit_id"]
        time.sleep(0.3)
    raise Failure("scan did not finish in time")


def multipart_zip(path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: application/zip\r\n\r\n").encode()
    return head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", type=Path)
    ap.add_argument("--dataset", type=Path, required=True, help="dataset directory to audit (e.g. examples/sample_dataset)")
    args = ap.parse_args()
    exe, dataset = args.exe.resolve(), args.dataset.resolve()
    if not exe.is_file():
        print(f"executable not found: {exe}")
        return 2

    work = Path(tempfile.mkdtemp(prefix="imageaudit-smoke-"))
    data_ds = work / "dataset"
    shutil.copytree(dataset, data_ds)
    cwd = work / "empty-cwd"  # proves the source tree is not needed next to / around the binary
    cwd.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "IMAGEAUDIT_HOME", "IMAGEAUDIT_STATIC_DIR")}
    if sys.platform == "win32":  # exercises the *default* data location without touching the real one
        local = work / "LocalAppData"
        local.mkdir()
        env["LOCALAPPDATA"] = str(local)
        home = local / "ImageAudit"
    else:
        env["IMAGEAUDIT_HOME"] = str(work / "home")
        home = work / "home"
    print(f"binary : {exe}\ndata   : {home}")
    app = App(exe, env, cwd)
    try:
        print("[1] startup + UI")
        app.start()
        s, _, html = http("GET", app.base + "/")
        check(s == 200 and b"ImageAudit" in html, "GET / serves the web UI")
        for page in ("/images/", "/settings/", "/duplicates/"):
            check(http("GET", app.base + page)[0] == 200, f"GET {page} serves a UI page")
        assets = re.findall(r'(?:src|href)="(/_next/static/[^"]+)"', html.decode())
        check(len(assets) > 0, "index references bundled static assets")
        check(all(http("GET", app.base + a)[0] == 200 for a in assets), f"all {len(assets)} referenced assets load")
        js = [a for a in assets if a.endswith(".js")]
        chunks = set(js)
        for page in ("/", "/images/", "/settings/"):
            chunks |= set(re.findall(r'/_next/static/[^"\\\s]+?\.js', http("GET", app.base + page)[2].decode()))
        offenders = [c for c in sorted(chunks) if b"127.0.0.1:8000" in http("GET", app.base + c)[2]]
        check(len(chunks) > 0 and not offenders, f"no dev API URL (127.0.0.1:8000) in {len(chunks)} bundled JS files {offenders}")
        s, h = jget(app.base + "/api/health")
        check(s == 200 and h["status"] == "ok", "API health ok (same origin as the UI)")

        print("[2] audit")
        a1 = scan(app, data_ds)
        s, ov = jget(f"{app.base}/api/audits/{a1}")
        check(s == 200 and ov["statistics"]["totals"]["images_total"] > 0, "audit results available")
        s, imgs = jget(f"{app.base}/api/audits/{a1}/images?page_size=3")
        check(s == 200 and imgs["items"], "image explorer returns items")
        s, _, body = http("GET", f"{app.base}/api/audits/{a1}/images/{imgs['items'][0]['id']}/thumbnail?size=128")
        check(s == 200 and body[:2] == b"\xff\xd8", "thumbnail is a JPEG")

        print("[3] reports")
        s, _, body = http("GET", f"{app.base}/api/audits/{a1}/reports/html")
        check(s == 200 and b"<html" in body.lower(), "HTML report (bundled Jinja template)")
        s, _, body = http("GET", f"{app.base}/api/audits/{a1}/reports/pdf")
        check(s == 200 and body.startswith(b"%PDF"), "PDF report")
        s, _, body = http("GET", f"{app.base}/api/audits/{a1}/reports/csv")
        check(s == 200 and len(body) > 20, "CSV report")
        s, _, body = http("GET", f"{app.base}/api/audits/{a1}/reports/json")
        check(s == 200 and json.loads(body), "JSON report")

        print("[4] archive upload")
        z = work / "upload.zip"
        with zipfile.ZipFile(z, "w") as zf:
            for f in data_ds.rglob("*"):
                if f.is_file():
                    zf.write(f, "ds/" + f.relative_to(data_ds).as_posix())
        payload, ctype = multipart_zip(z)
        s, _, b = http("POST", app.base + "/api/scans/upload", payload, {"Content-Type": ctype})
        check(s == 202, "upload accepted (202)")
        a2 = wait_job(app, json.loads(b)["id"])
        check(a2 != a1, "uploaded dataset produced a second audit")

        print("[5] persistence location")
        check((home / "audits" / f"{a1}.json").is_file(), "audit stored in the user data directory")
        check((home / "logs" / "imageaudit.log").is_file(), "log file written to the user data directory")

        print("[6] delete")
        s, _, _ = http("DELETE", f"{app.base}/api/audits/{a1}")
        check(s == 204, "DELETE audit -> 204")
        check(jget(f"{app.base}/api/audits/{a1}")[0] == 404, "deleted audit is gone (404)")
        check(http("DELETE", f"{app.base}/api/audits/{a1}")[0] == 404, "deleting again -> 404")
        check(http("DELETE", f"{app.base}/api/audits/..%2Fcache.sqlite")[0] == 404, "traversal-style id rejected")
        check((home / "cache.sqlite").is_file(), "traversal attempt deleted nothing")
        check(not list((home / "audits").glob(f"{a1}*")), "no orphaned audit files")
        check([a["id"] for a in jget(app.base + "/api/audits")[1]] == [a2], "unrelated audit untouched")

        print("[7] restart + persistence")
        app.stop()
        app.start()
        ids = [a["id"] for a in jget(app.base + "/api/audits")[1]]
        check(ids == [a2], "after restart: deleted audit still deleted, other audit still present")
        check(http("GET", f"{app.base}/api/audits/{a2}/reports/pdf")[2].startswith(b"%PDF"), "report of persisted audit still works")
        check(http("DELETE", f"{app.base}/api/audits/{a2}")[0] == 204, "delete the remaining audit (upload cleanup)")
        check(not any((home / "uploads").iterdir()) if (home / "uploads").exists() else True, "extracted upload data removed")
        app.stop()
        app.start()
        check(jget(app.base + "/api/audits")[1] == [], "after second restart: history is empty")
        print("\nSMOKE TEST PASSED")
        return 0
    except Failure as e:
        print(f"\nSMOKE TEST FAILED: {e}")
        return 1
    finally:
        app.stop()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
