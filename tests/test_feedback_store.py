import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import core.feedback_store as fs


class TestFeedbackStore(unittest.TestCase):
    def test_history_includes_latest_correction(self):
        tmp = Path("tests") / ".tmp" / f"feedback_{uuid.uuid4().hex}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            db_path = tmp / "feedback.db"
            with patch.object(fs, "_DB_PATH", db_path):
                verdict_id = fs.save_verdict(
                    pr_number=12,
                    repo="org/repo",
                    agent_name="security",
                    vote="rejected",
                    critique_text="possible secret",
                    severity="HIGH",
                    confidence=0.88,
                )
                fs.save_correction(verdict_id, "lead-dev", "false_positive", "benign test fixture")
                rows = fs.get_agent_history("security", "org/repo", n=5)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["correction"], "false_positive")
                self.assertIn("fixture", rows[0]["correction_note"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
