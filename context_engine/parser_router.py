"""
context_engine/parser_router.py

Grammar Router: maps file extensions to the correct Tree-sitter parser + Language.
Supports Python, Go, JavaScript, TypeScript, and their variants.

Usage:
    from context_engine.parser_router import get_parser

    parser, language = get_parser("src/main.py")
    if parser is not None:
        tree = parser.parse(source_bytes)
"""

from pathlib import Path
from tree_sitter import Language, Parser

import tree_sitter_python as _tspy
import tree_sitter_go as _tsgo
import tree_sitter_javascript as _tsjs
import tree_sitter_typescript as _tsts

# ---------------------------------------------------------------------------
# Build Language objects once at module load (cheap, just wraps a pointer)
# ---------------------------------------------------------------------------
_LANGUAGES: dict[str, Language] = {
    ".py":  Language(_tspy.language()),
    ".go":  Language(_tsgo.language()),
    ".js":  Language(_tsjs.language()),
    ".jsx": Language(_tsjs.language()),
    ".ts":  Language(_tsts.language_typescript()),
    ".tsx": Language(_tsts.language_tsx()),
}

# Friendly names used in metadata
LANGUAGE_NAMES: dict[str, str] = {
    ".py":  "python",
    ".go":  "go",
    ".js":  "javascript",
    ".jsx": "javascript",
    ".ts":  "typescript",
    ".tsx": "typescript",
}


def get_parser(file_path: str) -> tuple[Parser | None, Language | None]:
    """
    Return an instantiated (Parser, Language) for the given file path.

    Returns (None, None) if the file extension is not supported.
    """
    ext = Path(file_path).suffix.lower()
    language = _LANGUAGES.get(ext)
    if language is None:
        return None, None
    return Parser(language), language


def get_language_name(file_path: str) -> str | None:
    """Return a human-readable language name for a file path, or None."""
    ext = Path(file_path).suffix.lower()
    return LANGUAGE_NAMES.get(ext)
