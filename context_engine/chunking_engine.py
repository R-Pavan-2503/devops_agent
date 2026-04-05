"""
context_engine/chunking_engine.py

Chunking Engine: reads source files, parses them into an AST with Tree-sitter,
extracts meaningful top-level code blocks (functions, classes, methods, types),
and returns structured chunks ready for embedding.

Usage:
    from context_engine.chunking_engine import chunk_file

    chunks = chunk_file("src/main.go", repo_name="backend_pandhi")
    # chunks -> list of {text: str, metadata: {...}, id: str}
"""

import hashlib
from pathlib import Path

from tree_sitter import Query, QueryCursor

from context_engine.parser_router import get_parser, get_language_name

# ---------------------------------------------------------------------------
# S-expression queries per language family.
# In tree-sitter 0.25+, each pattern in a query is independent.
# We list them as separate one-per-line entries for clarity.
# ---------------------------------------------------------------------------
# Each entry: list of (s_expression, capture_name) tuples
_QUERY_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "python": [
        ("(function_definition) @function", "function"),
        ("(class_definition) @class",       "class"),
    ],
    "go": [
        ("(function_declaration) @function",   "function"),
        ("(method_declaration) @method",        "method"),
        ("(type_declaration) @type",             "type"),
    ],
    "javascript": [
        ("(function_declaration) @function",     "function"),
        ("(lexical_declaration) @arrow_function", "arrow_function"),
        ("(class_declaration) @class",           "class"),
    ],
    "typescript": [
        ("(function_declaration) @function",      "function"),
        ("(lexical_declaration) @arrow_function",  "arrow_function"),
        ("(class_declaration) @class",            "class"),
        ("(interface_declaration) @interface",    "interface"),
        ("(type_alias_declaration) @type_alias",  "type_alias"),
    ],
}

# Extension → query language family
_EXT_TO_LANG_FAMILY: dict[str, str] = {
    ".py":  "python",
    ".go":  "go",
    ".js":  "javascript",
    ".jsx": "javascript",
    ".ts":  "typescript",
    ".tsx": "typescript",
}

# Minimum block size in characters — skip tiny/trivial nodes
_MIN_BLOCK_CHARS = 30


def _make_chunk_id(repo_name: str, file_path: str, start_byte: int) -> str:
    """Stable unique ID for a chunk based on position in file."""
    raw = f"{repo_name}::{file_path}::{start_byte}"
    return hashlib.md5(raw.encode()).hexdigest()


def chunk_file(file_path: str, repo_name: str) -> list[dict]:
    """
    Parse a source file and return a list of code-chunk dicts.

    Each dict has the shape:
        {
            "id":       str,       # stable MD5 hash of (repo, path, byte_offset)
            "text":     str,       # raw source text of the block
            "metadata": {
                "repo_name":  str,
                "file_path":  str,
                "language":   str,
                "block_type": str, # e.g. "function", "class", "method"
            }
        }

    Returns an empty list if the file is unsupported or unreadable.
    """
    path = Path(file_path)
    ext  = path.suffix.lower()

    # 1. Get parser & language family
    parser, language = get_parser(file_path)
    if parser is None:
        return []

    lang_family = _EXT_TO_LANG_FAMILY.get(ext)
    if lang_family is None:
        return []

    lang_name = get_language_name(file_path) or lang_family

    # 2. Read source bytes
    try:
        source_bytes = path.read_bytes()
    except (OSError, PermissionError) as exc:
        print(f"  [chunker] Could not read {file_path}: {exc}")
        return []

    # 3. Parse into AST
    tree = parser.parse(source_bytes)

    # 4. Build queries and run via QueryCursor (tree-sitter 0.25+ API)
    patterns = _QUERY_PATTERNS.get(lang_family, [])
    if not patterns:
        return []

    chunks: list[dict] = []
    seen_byte_offsets: set[int] = set()

    for s_expr, block_type in patterns:
        try:
            query = Query(language, s_expr)
        except Exception as exc:
            print(f"  [chunker] Query build error for '{block_type}' in {file_path}: {exc}")
            continue

        cursor = QueryCursor(query)
        for _pattern_index, captures_dict in cursor.matches(tree.root_node):
            # captures_dict: {capture_name: [Node, ...]}
            for cap_nodes in captures_dict.values():
                for node in cap_nodes:
                    text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

                    if len(text.strip()) < _MIN_BLOCK_CHARS:
                        continue
                    if node.start_byte in seen_byte_offsets:
                        continue
                    seen_byte_offsets.add(node.start_byte)

                    chunk_id = _make_chunk_id(repo_name, str(file_path), node.start_byte)
                    chunks.append({
                        "id": chunk_id,
                        "text": text,
                        "metadata": {
                            "repo_name":  repo_name,
                            "file_path":  str(file_path),
                            "language":   lang_name,
                            "block_type": block_type,
                        }
                    })

    return chunks
