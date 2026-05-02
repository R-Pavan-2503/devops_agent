import unittest

from core.verdicts import aggregate_weighted_verdict


class TestWeightedVerdicts(unittest.TestCase):
    def test_veto_blocks_approval(self):
        approvals = {
            "security": "rejected",
            "architecture": "approved",
            "backend": "approved",
            "code_quality": "approved",
            "frontend": "approved",
            "qa": "approved",
        }
        details = {"security": {"severity": "CRITICAL", "confidence": 0.95, "vote": "rejected"}}
        result = aggregate_weighted_verdict(details, approvals)
        self.assertEqual(result.final_verdict, "rejected")
        self.assertEqual(result.vetoed_by, "security")

    def test_weighted_threshold(self):
        approvals = {
            "security": "approved",
            "architecture": "approved",
            "backend": "approved",
            "code_quality": "rejected",
            "frontend": "rejected",
            "qa": "approved",
        }
        details = {
            "security": {"severity": "LOW", "confidence": 0.8, "vote": "approved"},
            "architecture": {"severity": "LOW", "confidence": 0.8, "vote": "approved"},
        }
        result = aggregate_weighted_verdict(details, approvals)
        self.assertEqual(result.final_verdict, "approved")
        self.assertGreaterEqual(result.weighted_score, 0.65)


if __name__ == "__main__":
    unittest.main()

