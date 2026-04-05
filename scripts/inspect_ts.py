"""Inspect QueryCursor in tree-sitter 0.25+."""
import tree_sitter_python as tspy
from tree_sitter import Language, Parser, Query, QueryCursor

lang = Language(tspy.language())
parser = Parser(lang)

src = b"def hello(x):\n    return x + 1\n\nclass Foo:\n    pass\n"
tree = parser.parse(src)

print("QueryCursor attrs:", [a for a in dir(QueryCursor) if not a.startswith("_")])

# Build Query using the new constructor (not lang.query())
q = Query(lang, "(function_definition) @func (class_definition) @cls")

# Use QueryCursor
cursor = QueryCursor(q)
print("\nUsing cursor.matches()...")
cursor.matches(tree.root_node)  # prime it

# Try exec methods
for attr in ["matches", "captures", "exec", "set_point_range", "set_byte_range", "set_match_limit"]:
    print(f"  has {attr}:", hasattr(cursor, attr))

# Try captures
cursor2 = QueryCursor(q)
print("\nCaptures:")
for match in cursor2.matches(tree.root_node):
    print(" match:", match)
