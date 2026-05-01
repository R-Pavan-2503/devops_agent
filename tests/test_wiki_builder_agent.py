import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents import wiki_builder_agent


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def __init__(self, payload: str):
        self.payload = payload

    def invoke(self, _messages):
        return _FakeResponse(self.payload)


class WikiBuilderTests(unittest.TestCase):
    def test_generates_files_and_context(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as vault:
            ws = Path(workspace)
            (ws / "api").mkdir(parents=True, exist_ok=True)
            (ws / "api" / "main.py").write_text("print('ok')", encoding="utf-8")

            payload = (
                "[FILE: index.md]\n```markdown\n---\nsource_commit: abcdef12\n---\n# Knowledge Map\n```\n"
                "[FILE: patterns/auth.md]\n```markdown\n# Auth\n[[index]]\n```\n"
            )
            fake_llm = _FakeLLM(payload)

            with patch.object(wiki_builder_agent, "OBSIDIAN_VAULT_ROOT", Path(vault)):
                result = wiki_builder_agent.generate_knowledge_map(
                    repo_name="repo1",
                    workspace_path=workspace,
                    repo_map_str="repo map",
                    commit_sha="abcdef1234",
                    wiki_builder_llm=fake_llm,
                )
                self.assertGreaterEqual(len(result["written_files"]), 2)
                self.assertIn("Knowledge Map", result["knowledge_context_str"])


if __name__ == "__main__":
    unittest.main()
