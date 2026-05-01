import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine import knowledge_map_loader


class KnowledgeMapLoaderTests(unittest.TestCase):
    def test_missing_map(self):
        with tempfile.TemporaryDirectory() as vault:
            with patch.object(knowledge_map_loader, "OBSIDIAN_VAULT_ROOT", Path(vault)):
                result = knowledge_map_loader.load_knowledge_context("repo1", "abcdef12")
                self.assertFalse(result["map_exists"])
                self.assertEqual(result["knowledge_context_str"], "")

    def test_loads_index_and_patterns(self):
        with tempfile.TemporaryDirectory() as vault:
            root = Path(vault) / "projects" / "repo1"
            (root / "patterns").mkdir(parents=True, exist_ok=True)
            (root / "index.md").write_text(
                "---\nsource_commit: abcdef12\n---\n# Index",
                encoding="utf-8",
            )
            (root / "patterns" / "auth.md").write_text("# Auth", encoding="utf-8")
            with patch.object(knowledge_map_loader, "OBSIDIAN_VAULT_ROOT", Path(vault)):
                result = knowledge_map_loader.load_knowledge_context("repo1", "abcdef12")
                self.assertTrue(result["map_exists"])
                self.assertEqual(result["source_commit"], "abcdef12")
                self.assertIn("# Index", result["knowledge_context_str"])
                self.assertIn("# Auth", result["knowledge_context_str"])


if __name__ == "__main__":
    unittest.main()
