import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.build_swe_report import ROOT, grade_view, page, verify


class SWENativeInterpretationTests(unittest.TestCase):
    def setUp(self):
        self.spec = {
            "FAIL_TO_PASS": ["defect"],
            "PASS_TO_PASS": [f"regression-{i}" for i in range(30)],
        }
        self.report = {
            "resolved": False,
            "infra_failure": False,
            "tests_status": {
                "FAIL_TO_PASS": {"success": [], "failure": ["defect"]},
                "PASS_TO_PASS": {"success": self.spec["PASS_TO_PASS"], "failure": []},
            },
        }

    def test_aggregate_rule_can_accept_an_unresolved_required_defect(self):
        result = grade_view(self.report, self.spec)
        self.assertEqual(result["disposition"], "not_accepted")
        self.assertEqual(result["f2p_passed"], 0)
        self.assertTrue(result["aggregate_95_accepted"])

    def test_infrastructure_flag_does_not_become_a_confirmed_rejection(self):
        self.report["infra_failure"] = True
        self.report["infra_failure_reason"] = "network_unreachable"
        result = grade_view(self.report, self.spec)
        self.assertEqual(result["disposition"], "unavailable")
        self.assertIsNone(result["aggregate_95_accepted"])
        self.assertFalse(result["upstream_resolved"])
        self.assertEqual(result["infra_failure_reason"], "network_unreachable")

    def test_missing_or_duplicated_test_evidence_cannot_improve_the_score(self):
        for evidence in [
            {"success": [], "failure": []},
            {"success": ["defect"], "failure": ["defect"]},
            {"success": ["defect", "defect"], "failure": []},
        ]:
            with self.subTest(evidence=evidence):
                self.report["tests_status"]["FAIL_TO_PASS"] = evidence
                result = grade_view(self.report, self.spec)
                self.assertEqual(result["disposition"], "unavailable")
                self.assertIsNone(result["aggregate_95_accepted"])

    def test_model_text_cannot_close_the_embedded_json_script(self):
        document = page({}, [], {"text": "</script><img src=x onerror=alert(1)>"})
        self.assertNotIn("</script><img", document)
        self.assertIn("\\u003c/script>", document)


class SWEPresentedReportTests(unittest.TestCase):
    def test_resealed_page_or_methods_cannot_contradict_the_records(self):
        for name in ("index.html", "README.md"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary) / "independent-swe"
                shutil.copytree(ROOT / "examples/independent-swe", folder)
                data = (folder / name).read_bytes() + b"\n31 attempts were accepted.\n"
                (folder / name).write_bytes(data)
                manifest = json.loads((folder / "manifest.json").read_text())
                manifest["files"][name] = {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
                (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
                with self.assertRaisesRegex(ValueError, "presented report differs"):
                    verify(folder)


if __name__ == "__main__":
    unittest.main()
