"""
AST-related tools for CodeSage agents.
"""

import os
import difflib
import tree_sitter
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from indexer.parser import PY_LANGUAGE, JAVA_LANGUAGE, parse_file

class GetAstNodeInput(BaseModel):
    file_path: str = Field(description="The path to the file.")
    node_path: str = Field(description="The dotted node path.")

@tool("get_ast_node", args_schema=GetAstNodeInput)
def get_ast_node(file_path: str, node_path: str) -> dict:
    """Return the source text and metadata for a specific AST node."""
    try:
        if not os.path.exists(file_path):
            return {"found": False, "error": "file_not_found", "node_path": node_path}
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        nodes = parse_file(file_path, content)
        for node in nodes:
            if node.node_path == node_path:
                return {
                    "found": True,
                    "file_path": file_path,
                    "node_path": node_path,
                    "source_text": node.source_text,
                    "signature": node.signature,
                    "line_start": node.line_start,
                    "line_end": node.line_end
                }
        return {"found": False, "node_path": node_path}
    except Exception as e:
        return {"found": False, "error": str(e), "node_path": node_path}

class ListFileSymbolsInput(BaseModel):
    file_path: str = Field(description="The path to the file.")

@tool("list_file_symbols", args_schema=ListFileSymbolsInput)
def list_file_symbols(file_path: str) -> dict:
    """Return all top-level symbols in a file with their signatures."""
    try:
        if not os.path.exists(file_path):
            return {"file_path": file_path, "symbols": [], "error": "file_not_found"}
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        nodes = parse_file(file_path, content)
        symbols = []
        for node in nodes:
            symbols.append({
                "node_path": node.node_path,
                "node_type": node.node_type,
                "signature": node.signature,
                "line_start": node.line_start
            })
        return {
            "file_path": file_path,
            "symbols": symbols
        }
    except Exception as e:
        return {"file_path": file_path, "symbols": [], "error": str(e)}

class ApplyAstPatchInput(BaseModel):
    file_path: str = Field(description="The path to the file.")
    node_path: str = Field(description="The dotted path of the AST node.")
    new_source: str = Field(description="Complete replacement source for this node.")

def find_node_by_path(node: tree_sitter.Node, source_bytes: bytes, lang: str, target_path: str, current_path: str = "") -> Optional[tree_sitter.Node]:
    """Helper to walk the Tree-sitter AST and find the node matching the target path."""
    if lang == "python":
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "unknown"
            node_path = f"{current_path}.{name}" if current_path else name
            if node_path == target_path:
                return node
                
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "unknown"
            node_path = f"{current_path}.{name}" if current_path else name
            if node_path == target_path:
                return node
                
            body = None
            for child in node.children:
                if child.type == "block":
                    body = child
                    break
            if body:
                for child in body.children:
                    res = find_node_by_path(child, source_bytes, lang, target_path, node_path)
                    if res:
                        return res
            return None
            
    elif lang == "java":
        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "unknown"
            node_path = f"{current_path}.{name}" if current_path else name
            if node_path == target_path:
                return node
                
        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "unknown"
            node_path = f"{current_path}.{name}" if current_path else name
            if node_path == target_path:
                return node
                
            body = None
            for child in node.children:
                if child.type == "class_body":
                    body = child
                    break
            if body:
                for child in body.children:
                    res = find_node_by_path(child, source_bytes, lang, target_path, node_path)
                    if res:
                        return res
            return None

    for child in node.children:
        res = find_node_by_path(child, source_bytes, lang, target_path, current_path)
        if res:
            return res
            
    return None

@tool("apply_ast_patch", args_schema=ApplyAstPatchInput)
def apply_ast_patch(file_path: str, node_path: str, new_source: str) -> dict:
    """Replace the source of a specific AST node. Validates syntax first."""
    try:
        lang = "python" if file_path.endswith(".py") else "java"
        lang_obj = PY_LANGUAGE if lang == "python" else JAVA_LANGUAGE
        
        if lang_obj is None:
            return {"success": False, "error": "parser_not_available", "detail": f"Tree-sitter parser not available for {lang}"}
            
        # 1. Validate syntax of the new patch first
        parser = tree_sitter.Parser(lang_obj)
        new_tree = parser.parse(bytes(new_source, "utf8"))
        if new_tree.root_node.has_error:
            return {"success": False, "error": "syntax_error", "detail": "The provided new_source has syntax errors."}
            
        # 2. Read the target file
        if not os.path.exists(file_path):
            return {"success": False, "error": "file_not_found", "detail": f"File not found: {file_path}"}
            
        with open(file_path, "r", encoding="utf-8") as f:
            original_content = f.read()
            
        # 3. Locate the AST node to replace
        source_bytes = original_content.encode("utf-8")
        orig_tree = parser.parse(source_bytes)
        target_node = find_node_by_path(orig_tree.root_node, source_bytes, lang, node_path)
        
        if not target_node:
            return {"success": False, "error": "node_not_found", "detail": f"AST node '{node_path}' not found in {file_path}"}
            
        # 4. Perform AST replacement at node boundaries
        prefix = source_bytes[:target_node.start_byte].decode("utf-8")
        suffix = source_bytes[target_node.end_byte:].decode("utf-8")
        patched_content = prefix + new_source + suffix
        
        # 5. Write changes back to the filesystem
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(patched_content)
            
        # 6. Generate unified diff
        orig_lines = original_content.splitlines(keepends=True)
        patched_lines = patched_content.splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(
                orig_lines,
                patched_lines,
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}"
            )
        )
        
        return {"success": True, "diff": diff}
        
    except Exception as e:
        return {"success": False, "error": "write_error", "detail": str(e)}

class GetFileContentInput(BaseModel):
    file_path: str = Field(description="The path to the file.")
    start_line: int = Field(default=1, description="Start line (1-indexed).")
    end_line: Optional[int] = Field(default=None, description="End line (inclusive). None means read to EOF.")

@tool("get_file_content", args_schema=GetFileContentInput)
def get_file_content(file_path: str, start_line: int = 1, end_line: Optional[int] = None) -> dict:
    """Read a raw slice of a file by line numbers."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line) if end_line is not None else len(lines)
        
        content = "".join(lines[start_idx:end_idx])
        return {
            "file_path": file_path,
            "content": content,
            "start_line": start_line,
            "end_line": end_line if end_line is not None else len(lines)
        }
    except Exception as e:
        return {"error": str(e)}
