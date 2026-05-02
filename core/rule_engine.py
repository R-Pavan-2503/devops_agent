from __future__ import annotations

import ast
import re
from dataclasses import dataclass


SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


@dataclass(frozen=True)
class RuleFinding:
    rule_id: str
    severity: str
    file_path: str
    line: int
    message: str
    evidence: str


@dataclass(frozen=True)
class RuleEngineReport:
    findings: list[RuleFinding]
    max_severity: str
    auto_reject: bool


_KEY_PATTERNS = [
    ("secret.groq", "CRITICAL", re.compile(r"\bgsk_[A-Za-z0-9]{16,}\b")),
    ("secret.aws", "CRITICAL", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]
_GENERIC_SECRET_PATTERN = re.compile(
    r"\b(SECRET|PASSWORD|TOKEN|API_KEY)\b\s*[:=]\s*['\"][^'\"]{4,}['\"]",
    re.IGNORECASE,
)
_HTTP_PATTERN = re.compile(r"http://(?!localhost|127\.0\.0\.1)", re.IGNORECASE)
_SELECT_STAR_PATTERN = re.compile(r"\bSELECT\s+\*\s+FROM\b", re.IGNORECASE)
_CONSOLE_LOG_PATTERN = re.compile(r"\bconsole\.log\s*\(")


def _dominant_severity(findings: list[RuleFinding]) -> str:
    if not findings:
        return "NONE"
    return max(findings, key=lambda x: SEVERITY_ORDER.get(x.severity, 0)).severity


def _push(findings: list[RuleFinding], finding: RuleFinding) -> None:
    findings.append(finding)


def _scan_text_rules(file_path: str, content: str, findings: list[RuleFinding]) -> None:
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        for rule_id, sev, pattern in _KEY_PATTERNS:
            if pattern.search(line):
                _push(
                    findings,
                    RuleFinding(rule_id, sev, file_path, idx, "Hardcoded API key detected.", line.strip()[:220]),
                )
        if _GENERIC_SECRET_PATTERN.search(line):
            _push(
                findings,
                RuleFinding(
                    "secret.generic",
                    "CRITICAL",
                    file_path,
                    idx,
                    "Hardcoded secret/token style assignment detected.",
                    line.strip()[:220],
                ),
            )
        if _HTTP_PATTERN.search(line):
            _push(
                findings,
                RuleFinding("insecure.http", "HIGH", file_path, idx, "Non-localhost http:// usage detected.", line.strip()[:220]),
            )
        if _SELECT_STAR_PATTERN.search(line):
            _push(
                findings,
                RuleFinding("sql.select_star", "MEDIUM", file_path, idx, "SELECT * found in SQL string.", line.strip()[:220]),
            )
        if _CONSOLE_LOG_PATTERN.search(line):
            _push(
                findings,
                RuleFinding("debug.console_log", "LOW", file_path, idx, "console.log left in code.", line.strip()[:220]),
            )


def _python_ast_checks(file_path: str, content: str, findings: list[RuleFinding]) -> None:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                _push(
                    findings,
                    RuleFinding("python.dangerous_exec", "HIGH", file_path, node.lineno, f"Use of {node.func.id}() detected.", ast.unparse(node)[:220] if hasattr(ast, "unparse") else node.func.id),
                )
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "system":
                    _push(
                        findings,
                        RuleFinding("python.os_system", "HIGH", file_path, node.lineno, "os.system() detected.", "os.system(...)"),
                    )
                if node.func.attr in {"execute", "query"} and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.BinOp) and isinstance(first.op, ast.Add):
                        _push(
                            findings,
                            RuleFinding(
                                "python.sql_concat",
                                "CRITICAL",
                                file_path,
                                node.lineno,
                                "Potential SQL concatenation with variable.",
                                "execute/query with concatenated string",
                            ),
                        )
            self.generic_visit(node)

    Visitor().visit(tree)


def _js_heuristics(file_path: str, content: str, findings: list[RuleFinding]) -> None:
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if re.search(r"\b(eval|exec)\s*\(", stripped):
            _push(
                findings,
                RuleFinding("js.dangerous_eval", "HIGH", file_path, idx, "eval/exec usage detected.", stripped[:220]),
            )
        if re.search(r"\b(\w+\.)?(query|execute)\s*\(\s*['\"`].*['\"`]\s*\+\s*\w+", stripped):
            _push(
                findings,
                RuleFinding("js.sql_concat", "CRITICAL", file_path, idx, "Potential SQL concatenation with variable.", stripped[:220]),
            )
        if "await" not in stripped and re.search(r"\b(db|database|repo)\.\w+\(", stripped) and "async " in content:
            _push(
                findings,
                RuleFinding("js.missing_await", "HIGH", file_path, idx, "Possible missing await on async DB call.", stripped[:220]),
            )


def run_hard_rules(current_files: dict[str, str]) -> RuleEngineReport:
    findings: list[RuleFinding] = []
    for file_path, content in (current_files or {}).items():
        if not isinstance(content, str):
            continue
        _scan_text_rules(file_path, content, findings)
        lower = file_path.lower()
        if lower.endswith(".py"):
            _python_ast_checks(file_path, content, findings)
        if lower.endswith((".js", ".jsx", ".ts", ".tsx")):
            _js_heuristics(file_path, content, findings)

    max_severity = _dominant_severity(findings)
    auto_reject = max_severity == "CRITICAL"
    return RuleEngineReport(findings=findings, max_severity=max_severity, auto_reject=auto_reject)

