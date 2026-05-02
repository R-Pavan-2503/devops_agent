import shutil
import unittest
import uuid
from pathlib import Path

from core.test_quality import evaluate_test_quality


class TestTestQuality(unittest.TestCase):
    def test_high_signal_when_tests_reference_changed_logic(self):
        tmp = Path("tests") / ".tmp" / f"test_quality_{uuid.uuid4().hex}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            root = tmp
            (root / "src").mkdir(parents=True, exist_ok=True)
            (root / "tests").mkdir(parents=True, exist_ok=True)
            (root / "src" / "auth.js").write_text("export const login = () => true;", encoding="utf-8")
            (root / "tests" / "auth.test.js").write_text("import { login } from '../src/auth'; test('x', ()=>login())", encoding="utf-8")
            score, label, coverage = evaluate_test_quality(["src/auth.js"], str(root))
            self.assertGreaterEqual(score, 1.0)
            self.assertEqual(label, "HIGH")
            self.assertTrue(coverage["src/auth.js"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_low_signal_when_no_tests(self):
        tmp = Path("tests") / ".tmp" / f"test_quality_{uuid.uuid4().hex}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            root = tmp
            (root / "src").mkdir(parents=True, exist_ok=True)
            (root / "src" / "payments.py").write_text("def charge():\n    return True\n", encoding="utf-8")
            score, label, _ = evaluate_test_quality(["src/payments.py"], str(root))
            self.assertEqual(label, "LOW")
            self.assertLess(score, 0.4)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
