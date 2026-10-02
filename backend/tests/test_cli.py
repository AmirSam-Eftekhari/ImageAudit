import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from imageaudit.demo import generate_sample_dataset

from .helpers import TempCase, make_clean_dataset

BACKEND = Path(__file__).resolve().parents[1]


class CliTests(TempCase):
    """Runs the real CLI in a subprocess so exit codes are what CI would see."""

    def run_cli(self, *args: str, expect: int | None = None):
        env = {**os.environ, "PYTHONPATH": str(BACKEND), "IMAGEAUDIT_HOME": str(self.home), "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run([sys.executable, "-m", "imageaudit", *args], capture_output=True, text=True,
                              env=env, timeout=120, cwd=self.tmp)
        if expect is not None:
            self.assertEqual(proc.returncode, expect, f"stdout={proc.stdout}\nstderr={proc.stderr}")
        return proc

    def sample(self) -> Path:
        generate_sample_dataset(self.tmp / "sample")
        return self.tmp / "sample"

    def test_help_and_version(self):
        out = self.run_cli("--help", expect=0).stdout
        for cmd in ("scan", "validate", "report", "demo", "serve"):
            self.assertIn(cmd, out)
        self.assertIn("0.1.0", self.run_cli("--version", expect=0).stdout)
        self.assertIn("--fail-under", self.run_cli("validate", "--help", expect=0).stdout)

    def test_scan_prints_summary_and_json_mode_is_machine_readable(self):
        ds = self.sample()
        out = self.run_cli("scan", str(ds), "--no-save", expect=0).stdout
        self.assertIn("health", out)
        self.assertIn("CRITICAL", out)
        data = json.loads(self.run_cli("scan", str(ds), "--json", "--no-save", expect=0).stdout)
        self.assertEqual(data["summary"]["images_total"], 72)
        self.assertIn("components", data["health"])
        self.assertEqual(data["findings"][0]["severity"], "critical")

    def test_scan_output_file_is_a_full_audit(self):
        ds = self.sample()
        self.run_cli("scan", str(ds), "-o", str(self.tmp / "audit.json"), "--no-save", expect=0)
        data = json.loads((self.tmp / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["images"]), 72)

    def test_validate_exit_codes(self):
        ds = self.sample()
        self.assertEqual(self.run_cli("validate", str(ds)).returncode, 1)  # default fail-on high
        self.assertIn("VALIDATION FAILED", self.run_cli("validate", str(ds)).stdout)
        self.run_cli("validate", str(ds), "--fail-on", "critical", expect=0)  # structural mode has none
        self.run_cli("validate", str(ds), "--full", "--fail-on", "critical", expect=1)
        self.run_cli("validate", str(ds), "--fail-on", "high", "--max-corrupt-rate", "0.5", expect=1)
        clean = make_clean_dataset(self.tmp / "clean", 9, 3, 3)
        self.run_cli("validate", str(clean), "--full", "--fail-under", "90", expect=0)
        self.run_cli("validate", str(ds), "--full", "--fail-under", "90", "--fail-on", "low", expect=1)

    def test_validate_thresholds_and_json_verdict(self):
        ds = self.sample()
        p = self.run_cli("validate", str(ds), "--fail-on", "critical", "--max-invalid-annotation-rate", "0.01", "--json")
        self.assertEqual(p.returncode, 1)
        verdict = json.loads(p.stdout)
        self.assertFalse(verdict["passed"])
        self.assertTrue(any("invalid annotation rate" in r for r in verdict["reasons"]))

    def test_config_file_can_relax_ci_policy(self):
        ds = self.sample()
        (self.tmp / "ci.yaml").write_text("ci:\n  fail_on: null\n", encoding="utf-8")
        self.run_cli("validate", str(ds), "--config", str(self.tmp / "ci.yaml"), expect=0)

    def test_usage_and_config_errors_exit_2(self):
        ds = self.sample()
        self.assertEqual(self.run_cli("validate", str(ds), "--fail-under", "80").returncode, 2)
        self.assertEqual(self.run_cli("validate", str(ds), "--max-blur-rate", "0.1").returncode, 2)
        self.assertEqual(self.run_cli("scan", str(self.tmp / "missing")).returncode, 2)
        (self.tmp / "bad.yaml").write_text("quality:\n  nope: 1\n", encoding="utf-8")
        p = self.run_cli("scan", str(ds), "--config", str(self.tmp / "bad.yaml"))
        self.assertEqual(p.returncode, 2)
        self.assertIn("quality.nope", p.stderr)
        empty = self.tmp / "empty"
        empty.mkdir()
        p = self.run_cli("scan", str(empty))
        self.assertEqual(p.returncode, 2)
        self.assertIn("error:", p.stderr)

    def test_report_all_formats_from_dataset_saved_audit_and_json(self):
        ds = self.sample()
        out = self.tmp / "rep"
        self.run_cli("report", str(ds), "-f", "html", "-f", "json", "-f", "csv", "-f", "pdf", "-o", str(out), expect=0)
        names = sorted(p.name for p in out.iterdir())
        self.assertEqual(len(names), 7, names)
        self.assertTrue(any(n.endswith(".html") for n in names))
        audit_id = json.loads(self.run_cli("scan", str(ds), "--json", expect=0).stdout)["summary"]["id"]
        self.run_cli("report", audit_id, "-f", "html", "-o", str(self.tmp / "rep2"), expect=0)
        self.run_cli("scan", str(ds), "-o", str(self.tmp / "a.json"), "--no-save", expect=0)
        self.run_cli("report", str(self.tmp / "a.json"), "-f", "json", "-o", str(self.tmp / "rep3"), expect=0)
        self.assertEqual(self.run_cli("report", "nonexistent-id", "-f", "html").returncode, 2)

    def test_demo_command(self):
        self.run_cli("demo", str(self.tmp / "demo"), expect=0)
        self.assertTrue((self.tmp / "demo" / "data.yaml").is_file())
        self.assertEqual(self.run_cli("demo", str(self.tmp / "demo")).returncode, 2)  # refuses to overwrite

    def test_audits_listing(self):
        self.assertIn("No stored audits", self.run_cli("audits", expect=0).stdout)
        self.run_cli("scan", str(self.sample()), expect=0)
        self.assertIn("score=", self.run_cli("audits", expect=0).stdout)

    def test_dataset_is_not_modified_by_cli(self):
        ds = self.sample()
        before = sorted((str(p.relative_to(ds)), p.stat().st_size) for p in ds.rglob("*") if p.is_file())
        self.run_cli("scan", str(ds), expect=0)
        self.run_cli("validate", str(ds))
        after = sorted((str(p.relative_to(ds)), p.stat().st_size) for p in ds.rglob("*") if p.is_file())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
