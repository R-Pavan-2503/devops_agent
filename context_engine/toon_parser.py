import os
from tree_sitter import Language, Parser

def get_parser(extension: str):
    """Returns a configured tree-sitter Parser for the given extension, or None."""
    parser = Parser()
    try:
        if extension == ".py":
            import tree_sitter_python
            parser.language = Language(tree_sitter_python.language())
        elif extension in [".js", ".jsx"]:
            import tree_sitter_javascript
            parser.language = Language(tree_sitter_javascript.language())
        elif extension == ".ts":
            import tree_sitter_typescript
            parser.language = Language(tree_sitter_typescript.language_typescript())
        elif extension == ".tsx":
            import tree_sitter_typescript
            parser.language = Language(tree_sitter_typescript.language_tsx())
        elif extension == ".go":
            import tree_sitter_go
            parser.language = Language(tree_sitter_go.language())
        else:
            return None
    except ImportError as e:
        print(f"[toon_parser] Missing language binding for {extension}: {e}")
        return None
    return parser

def get_node_name(node):
    """Extracts the identifier (name) of a class or function node."""
    for child in node.children:
        if child.type == "identifier" or child.type == "name":
            return child.text.decode('utf-8', errors='replace')
        if child.type == "property_identifier":
            return child.text.decode('utf-8', errors='replace')
        if child.type == "type_identifier":
            return child.text.decode('utf-8', errors='replace')
    return "<anonymous>"

def walk_tree(node, depth=0) -> str:
    """
    Recursively walks the AST and formats key structural nodes into TOON string.
    """
    out = ""
    indent = "  " * depth
    
    # We only care about structural elements
    relevant_types = {
        # Python
        "import_statement": "import",
        "import_from_statement": "import_from",
        "class_definition": "class",
        "function_definition": "function",
        # JS / TS
        "class_declaration": "class",
        "function_declaration": "function",
        "method_definition": "method",
        "lexical_declaration": "const_var", # For arrow functions
        "variable_declaration": "var",
        "import_statement": "import",
        # Go
        "import_declaration": "import",
        "type_declaration": "type",
        "function_declaration": "function",
        "method_declaration": "method"
    }

    n_type = node.type

    # Keep track of if we should parse children.
    # We generally only recurse into files and classes to find methods/functions.
    should_recurse = False

    if n_type == "program" or n_type == "source_file" or n_type == "module":
        should_recurse = True

    elif n_type in relevant_types:
        mapped_type = relevant_types[n_type]

        if mapped_type in ["import", "import_from"]:
            # Just print the raw line for imports
            text = node.text.decode('utf-8', errors='replace').split('\n')[0]
            out += f"{indent}{text}\n"
        
        elif mapped_type == "class":
            name = get_node_name(node)
            out += f"{indent}class {name}:\n"
            should_recurse = True  # Look for methods inside the class
            depth += 1
            
        elif mapped_type in ["function", "method"]:
            name = get_node_name(node)
            out += f"{indent}method {name}()\n"
            
        elif mapped_type == "type":
            # For Go type structs
            name = get_node_name(node)
            out += f"{indent}type {name}:\n"
            should_recurse = True
            depth += 1
            
        elif mapped_type in ["const_var", "var"]:
            # Check if it's an arrow function assignment
            text = node.text.decode('utf-8', errors='replace')
            if "=>" in text and ("function" in text or "{" in text):
                # Try to extract the variable name
                name = get_node_name(node)
                out += f"{indent}method {name}() [arrow]\n"

    elif n_type == "class_body" or n_type == "block" or n_type == "declaration_list":
        # Recurse into blocks if we are already inside a class
        should_recurse = True

    if should_recurse:
        for child in node.children:
            out += walk_tree(child, depth)

    return out

def generate_toon_skeleton(code: str, filepath: str) -> str:
    """
    Parses source code into a TOON (Token Oriented Object Notation) skeleton.
    Returns the skeleton string. If parsing fails, returns top 50 lines.
    """
    ext = os.path.splitext(filepath)[1].lower()
    parser = get_parser(ext)
    
    if not parser or not code.strip():
        # Fallback: Just return top 50 lines if unsupported or empty
        lines = code.split("\n")
        return "\n".join(lines[:50]) + "\n... [UNSUPPORTED LANG FALLBACK] ..."
        
    try:
        tree = parser.parse(bytes(code, "utf8"))
        skeleton = walk_tree(tree.root_node)
        if not skeleton.strip():
            # If the parser found nothing structural, return top 20 lines
            lines = code.split("\n")
            return "\n".join(lines[:20]) + "\n... [NO STRUCTURE DETECTED] ..."
        return skeleton.strip()
    except Exception as e:
        print(f"[toon_parser] Error parsing {filepath}: {e}")
        lines = code.split("\n")
        return "\n".join(lines[:50]) + f"\n... [PARSING ERROR: {e}] ..."
