import unittest

from core.pr_triage import TRIAGE_FULL, TRIAGE_LIGHTWEIGHT, TRIAGE_SKIP, classify_pr


class TestPrTriage(unittest.TestCase):
    def test_skip_for_docs_only(self):
        result = classify_pr(
            changed_files=["README.md", "docs/usage.md"],
            pr_title="docs: update usage",
            diff_stats={"total_lines_changed": 42},
        )
        self.assertEqual(result.mode, TRIAGE_SKIP)

    def test_lightweight_for_small_logic_change(self):
        result = classify_pr(
            changed_files=["api/main.py"],
            pr_title="fix: tiny logic bug",
            diff_stats={"total_lines_changed": 14},
        )
        self.assertEqual(result.mode, TRIAGE_FULL)  # force title token takes precedence

        result2 = classify_pr(
            changed_files=["api/main.py"],
            pr_title="refactor route helper",
            diff_stats={"total_lines_changed": 14},
        )
        self.assertEqual(result2.mode, TRIAGE_LIGHTWEIGHT)

    def test_full_for_infra(self):
        result = classify_pr(
            changed_files=["Dockerfile", "README.md"],
            pr_title="chore: adjust docs and docker",
            diff_stats={"total_lines_changed": 7},
        )
        self.assertEqual(result.mode, TRIAGE_FULL)


if __name__ == "__main__":
    unittest.main()

