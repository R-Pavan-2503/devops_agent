import unittest

from core.rule_engine import run_hard_rules


class TestRuleEngine(unittest.TestCase):
    def test_detects_hardcoded_secret(self):
        files = {"app.py": "API_KEY = 'gsk_1234567890ABCDEF1234'\nprint('x')\n"}
        report = run_hard_rules(files)
        self.assertTrue(report.auto_reject)
        self.assertEqual(report.max_severity, "CRITICAL")
        self.assertGreaterEqual(len(report.findings), 1)

    def test_detects_console_log_low(self):
        files = {"ui.js": "function x(){ console.log('debug'); }\n"}
        report = run_hard_rules(files)
        self.assertIn(report.max_severity, {"LOW", "MEDIUM", "HIGH", "CRITICAL"})
        self.assertGreaterEqual(len(report.findings), 1)


if __name__ == "__main__":
    unittest.main()

