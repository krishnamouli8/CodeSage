import logging
from dataclasses import dataclass
import tree_sitter_python as tspython
import tree_sitter_java as tsjava
from tree_sitter import Language, Parser, Node

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

@dataclass
class ParsedNode:
    file_path: str
    node_path: str
    node_type: str
    language: str
    source_text: str
    signature: str
    docstring: str
    line_start: int
    line_end: int

# Initialize tree-sitter languages
try:
    PY_LANGUAGE = Language(tspython.language())
    JAVA_LANGUAGE = Language(tsjava.language())
except Exception:
    PY_LANGUAGE = Language(tspython.language(), "python")
    JAVA_LANGUAGE = Language(tsjava.language(), "java")

def extract_python_docstring(node: Node, source_bytes: bytes) -> str:
    body = None
    for child in node.children:
        if child.type == "block":
            body = child
            break
    if not body or len(body.children) == 0:
        return ""
    
    first_stmt = body.children[0]
    if first_stmt.type == "expression_statement":
        string_node = first_stmt.children[0]
        if string_node.type == "string":
            import ast
            raw_string = source_bytes[string_node.start_byte:string_node.end_byte].decode("utf-8")
            try:
                return ast.literal_eval(raw_string)
            except Exception:
                return raw_string.strip('\'"')
    return ""

def extract_java_docstring(node: Node, source_bytes: bytes) -> str:
    prev = node.prev_sibling
    if prev and prev.type == "block_comment":
        text = source_bytes[prev.start_byte:prev.end_byte].decode("utf-8")
        if text.startswith("/**"):
            return text
    return ""

def get_python_class_header(node: Node, source_bytes: bytes, docstring: str) -> str:
    body_node = None
    for child in node.children:
        if child.type == "block":
            body_node = child
            break
    if body_node:
        header_bytes = source_bytes[node.start_byte:body_node.start_byte]
        header = header_bytes.decode("utf-8").strip()
        if docstring:
            return f"{header}\n    {docstring}"
        return header
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")

def get_java_class_header(node: Node, source_bytes: bytes, docstring: str) -> str:
    body_node = None
    for child in node.children:
        if child.type == "class_body":
            body_node = child
            break
    if body_node:
        header_bytes = source_bytes[node.start_byte:body_node.start_byte]
        header = header_bytes.decode("utf-8").strip()
        if docstring:
            return f"{docstring}\n{header}"
        return header
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")

def walk_ast(node: Node, source_bytes: bytes, lang: str, file_path: str, parent_path: str = "") -> list[ParsedNode]:
    nodes = []
    
    if lang == "python":
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "unknown"
            node_path = f"{parent_path}.{name}" if parent_path else name
            
            node_type = "method" if parent_path else "function"
            docstring = extract_python_docstring(node, source_bytes)
            source_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            signature = source_text.split("\n")[0]
            
            if source_text.strip():
                nodes.append(ParsedNode(
                    file_path=file_path,
                    node_path=node_path,
                    node_type=node_type,
                    language=lang,
                    source_text=source_text,
                    signature=signature,
                    docstring=docstring,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1
                ))
                
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "unknown"
            node_path = f"{parent_path}.{name}" if parent_path else name
            
            docstring = extract_python_docstring(node, source_bytes)
            source_text = get_python_class_header(node, source_bytes, docstring)
            signature = source_text.split("\n")[0]
            
            if source_text.strip():
                nodes.append(ParsedNode(
                    file_path=file_path,
                    node_path=node_path,
                    node_type="class",
                    language=lang,
                    source_text=source_text,
                    signature=signature,
                    docstring=docstring,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1
                ))
            
            body = None
            for child in node.children:
                if child.type == "block":
                    body = child
                    break
            if body:
                for child in body.children:
                    nodes.extend(walk_ast(child, source_bytes, lang, file_path, node_path))
            return nodes
            
    elif lang == "java":
        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "unknown"
            node_path = f"{parent_path}.{name}" if parent_path else name
            
            node_type = "method" if parent_path else "function"
            docstring = extract_java_docstring(node, source_bytes)
            source_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            signature = source_text.split("\n")[0]
            
            if source_text.strip():
                nodes.append(ParsedNode(
                    file_path=file_path,
                    node_path=node_path,
                    node_type=node_type,
                    language=lang,
                    source_text=source_text,
                    signature=signature,
                    docstring=docstring,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1
                ))
                
        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "unknown"
            node_path = f"{parent_path}.{name}" if parent_path else name
            
            docstring = extract_java_docstring(node, source_bytes)
            source_text = get_java_class_header(node, source_bytes, docstring)
            signature = source_text.split("\n")[0]
            
            if source_text.strip():
                nodes.append(ParsedNode(
                    file_path=file_path,
                    node_path=node_path,
                    node_type="class",
                    language=lang,
                    source_text=source_text,
                    signature=signature,
                    docstring=docstring,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1
                ))
            
            body = None
            for child in node.children:
                if child.type == "class_body":
                    body = child
                    break
            if body:
                for child in body.children:
                    nodes.extend(walk_ast(child, source_bytes, lang, file_path, node_path))
            return nodes

    for child in node.children:
        nodes.extend(walk_ast(child, source_bytes, lang, file_path, parent_path))
        
    return nodes

def parse_file(file_path: str, source_text: str) -> list[ParsedNode]:
    """Parse a source file and return all indexable nodes."""
    lang = "python" if file_path.endswith(".py") else "java"
    try:
        parser = Parser(PY_LANGUAGE if lang == "python" else JAVA_LANGUAGE)
        source_bytes = source_text.encode("utf-8")
        tree = parser.parse(source_bytes)
        
        if tree.root_node.has_error:
            logger.warning(f"Syntax error in {file_path}")
            return []
            
        return walk_ast(tree.root_node, source_bytes, lang, file_path)
    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")
        return []
