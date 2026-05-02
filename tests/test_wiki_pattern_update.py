import shutil
import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


_fake_lc = types.ModuleType("langchain_core")
_fake_lc_messages = types.ModuleType("langchain_core.messages")


class _Msg:
    def __init__(self, content: str):
        self.content = content


_fake_lc_messages.HumanMessage = _Msg
_fake_lc_messages.SystemMessage = _Msg
_fake_lc.messages = _fake_lc_messages
sys.modules.setdefault("langchain_core", _fake_lc)
sys.modules.setdefault("langchain_core.messages", _fake_lc_messages)

from agents import wiki_builder_agent


class _FakeResp:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def __init__(self, output: str):
        self._output = output

    def invoke(self, _messages):
        return _FakeResp(self._output)


class TestWikiPatternUpdate(unittest.TestCase):
    def test_updates_only_patterns_on_merge(self):
        tmp = Path("tests") / ".tmp" / f"wiki_{uuid.uuid4().hex}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            vault = tmp / "vault"
            repo = "repo1"
            repo_dir = vault / "projects" / repo
            patterns_dir = repo_dir / "patterns"
            patterns_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "index.md").write_text("---\nsource_commit: abcdef12\n---\n# Index\n", encoding="utf-8")
            (patterns_dir / "auth.md").write_text("# Auth\nold", encoding="utf-8")

            llm_output = (
                "[FILE: patterns/auth.md]\n```markdown\n# Auth\nupdated\n```\n"
                "[FILE: patterns/new_pattern.md]\n```markdown\n# New\ncontent\n```\n"
            )
            fake_llm = _FakeLLM(llm_output)

            with patch.object(wiki_builder_agent, "OBSIDIAN_VAULT_ROOT", vault):
                res = wiki_builder_agent.update_patterns_from_merge(
                    repo_name=repo,
                    workspace_path=tmp,
                    commit_sha="1234567890abcdef",
                    changed_files=["api/main.py"],
                    diff_files={"api/main.py": "@@ -1 +1 @@\n-print(1)\n+print(2)"},
                    wiki_builder_llm=fake_llm,
                )

            self.assertGreaterEqual(len(res["written_files"]), 2)
            self.assertIn("updated", (patterns_dir / "auth.md").read_text(encoding="utf-8"))
            self.assertTrue((patterns_dir / "new_pattern.md").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
