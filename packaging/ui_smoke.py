"""Optional browser test of the delete workflow against a *built* executable (needs `pip install playwright`
and a Chromium install). Complements packaging/smoke_test.py, which covers the HTTP/API level.

    python packaging/ui_smoke.py dist/ImageAudit.exe --dataset examples/sample_dataset
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from smoke_test import App, Failure, check, http, jget, wait_job


def main() -> int:
    from playwright.sync_api import expect, sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("exe", type=Path)
    ap.add_argument("--dataset", type=Path, required=True)
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="imageaudit-ui-"))
    ds = work / "dataset"
    shutil.copytree(args.dataset.resolve(), ds)
    (work / "cwd").mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("IMAGEAUDIT_HOME", "IMAGEAUDIT_STATIC_DIR")}
    if sys.platform == "win32":
        env["LOCALAPPDATA"] = str(work / "local")
    else:
        env["IMAGEAUDIT_HOME"] = str(work / "home")
    app = App(args.exe.resolve(), env, work / "cwd")
    try:
        app.start()
        ids = []
        for _ in range(2):
            _, _, b = http("POST", app.base + "/api/scans", json.dumps({"path": str(ds)}).encode(), {"Content-Type": "application/json"})
            ids.append(wait_job(app, json.loads(b)["id"]))
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            requests: list[str] = []
            page.on("request", lambda rq: requests.append(rq.url))
            # Dashboard: must reach the API on its own origin, never on a dev port.
            page.goto(app.base + "/")
            page.wait_for_load_state("networkidle")
            check(page.get_by_text("Cannot reach").count() == 0 and page.get_by_text("API unreachable").count() == 0,
                  "dashboard does not show 'API unreachable'")
            api_calls = [u for u in requests if "/api/" in u]
            check(bool(api_calls) and all(u.startswith(app.base + "/api/") for u in api_calls),
                  f"dashboard made {len(api_calls)} API calls, all same-origin")
            check(not any(":8000" in u for u in requests), "no request went to port 8000")
            page.goto(app.base + "/images/")
            page.wait_for_load_state("networkidle")
            check(page.get_by_text("Cannot reach").count() == 0, "images page loads without API error")
            page.goto(app.base + "/settings/")
            rows = page.locator("tbody tr")
            expect(rows).to_have_count(2)
            check(True, "UI lists both stored audits")

            # 1. confirmation step, cancel keeps the audit
            page.get_by_label("Delete audit dataset").first.click()
            expect(page.get_by_role("alertdialog")).to_be_visible()
            page.get_by_role("button", name="Cancel").click()
            expect(rows).to_have_count(2)
            check(len(jget(app.base + "/api/audits")[1]) == 2, "cancel deletes nothing")

            # 2. API error is surfaced and the row stays
            page.route("**/api/audits/*", lambda r: r.fulfill(status=500, content_type="application/json",
                       body='{"error":{"code":"internal_error","message":"disk on fire"}}') if r.request.method == "DELETE" else r.continue_())
            page.get_by_label("Delete audit dataset").first.click()
            page.get_by_role("button", name="Confirm delete").click()
            expect(page.get_by_text("disk on fire")).to_be_visible()
            expect(rows).to_have_count(2)
            check(True, "server error is shown and the audit remains listed")
            page.unroute("**/api/audits/*")

            # 3. successful delete: row disappears without a page reload, and the delete persisted
            marker = page.evaluate("() => (window.__noReload = 1)")
            page.get_by_label("Delete audit dataset").first.click()
            page.get_by_role("button", name="Confirm delete").click()
            expect(rows).to_have_count(1)
            check(page.evaluate("() => window.__noReload") == 1 and marker == 1, "row removed with no full page reload")
            remaining = [a["id"] for a in jget(app.base + "/api/audits")[1]]
            check(len(remaining) == 1, "backend now holds exactly one audit")

            # 4. reload: still deleted
            page.reload()
            expect(page.locator("tbody tr")).to_have_count(1)
            check(not errors, f"no uncaught page errors {errors}")
            browser.close()
        print("\nUI SMOKE TEST PASSED")
        return 0
    except (Failure, AssertionError) as e:
        print(f"\nUI SMOKE TEST FAILED: {e}")
        return 1
    finally:
        app.stop()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
