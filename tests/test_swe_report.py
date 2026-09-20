import unittest

from scripts.build_swe_report import grade_view, page


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


if __name__ == "__main__":
    unittest.main()
