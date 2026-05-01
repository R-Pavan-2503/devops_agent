import tempfile
import unittest
from unittest.mock import patch

from context_engine import repo_map_builder


class RepoMapBuilderTests(unittest.TestCase):
    def test_cache_miss_writes_file(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as cache_root:
            with patch.object(repo_map_builder, "REPO_MAPS_DIR", repo_map_builder.Path(cache_root)):
                with patch("context_engine.repo_map_builder.subprocess.run") as mock_run:
                    mock_run.return_value.returncode = 0
                    mock_run.return_value.stdout = "repo map content"
                    mock_run.return_value.stderr = ""

                    result = repo_map_builder.build_repo_map("demo/repo", workspace, "abcdef123456")
                    self.assertFalse(result["cache_hit"])
                    self.assertIn("repo map content", result["repo_map_str"])
                    self.assertTrue(repo_map_builder.Path(result["cache_path"]).exists())

    def test_cache_hit_reuses_file(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as cache_root:
            with patch.object(repo_map_builder, "REPO_MAPS_DIR", repo_map_builder.Path(cache_root)):
                first = repo_map_builder.Path(cache_root) / "demo_repo_abcdef12.txt"
                first.parent.mkdir(parents=True, exist_ok=True)
                first.write_text("cached map", encoding="utf-8")
                result = repo_map_builder.build_repo_map("demo/repo", workspace, "abcdef123456")
                self.assertTrue(result["cache_hit"])
                self.assertEqual(result["repo_map_str"], "cached map")

    def test_repomix_failure_raises(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as cache_root:
            with patch.object(repo_map_builder, "REPO_MAPS_DIR", repo_map_builder.Path(cache_root)):
                with patch("context_engine.repo_map_builder.subprocess.run") as mock_run:
                    mock_run.return_value.returncode = 1
                    mock_run.return_value.stdout = ""
                    mock_run.return_value.stderr = "repomix error"
                    with self.assertRaises(RuntimeError):
                        repo_map_builder.build_repo_map("demo/repo", workspace, "abcdef123456")


if __name__ == "__main__":
    unittest.main()
