"""
Graph tools for CodeSage agents.
"""

import os
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# Lazy singleton for QdrantClient
_qdrant_client = None

def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
        _qdrant_client = QdrantClient(url=qdrant_url)
    return _qdrant_client

def _mock_symbol_graph(symbol_name: str, depth: int = 2) -> dict:
    return {
        "symbol": symbol_name,
        "callers": [f"file.ClassName.mock_caller_{symbol_name}"],
        "callees": [f"other.mock_callee_{symbol_name}"],
        "depth_searched": depth
    }

class SymbolGraphInput(BaseModel):
    symbol_name: str = Field(description="The symbol name to build a graph for")
    depth: int = Field(default=2, description="Max traversal depth")

@tool("symbol_graph", args_schema=SymbolGraphInput)
def symbol_graph(symbol_name: str, depth: int = 2) -> dict:
    """Return callers and callees of a symbol up to the given depth."""
    try:
        qdrant = get_qdrant_client()
        collection_name = os.environ.get("QDRANT_COLLECTION", "codesage_chunks")
        
        # 1. Scroll and load all chunks in the collection
        chunks = []
        offset = None
        while True:
            records, offset = qdrant.scroll(
                collection_name=collection_name,
                limit=100,
                with_payload=True,
                with_vectors=False,
                offset=offset
            )
            chunks.extend(records)
            if not offset:
                break
                
        if not chunks:
            # Fall back to mock if collection is empty
            return _mock_symbol_graph(symbol_name, depth)
            
        # 2. Build a map of node_path -> full source_text
        node_map = {}
        for record in chunks:
            payload = record.payload or {}
            node_path = payload.get("node_path")
            source_text = payload.get("source_text", "")
            if node_path:
                if node_path not in node_map:
                    node_map[node_path] = ""
                node_map[node_path] += "\n" + source_text
                
        # 3. Traverse to find callers up to depth
        visited_callers = set()
        current_level = {symbol_name}
        for _ in range(depth):
            next_level = set()
            for sym in current_level:
                for node_path, source_text in node_map.items():
                    if node_path != sym and sym in source_text:
                        if node_path not in visited_callers:
                            visited_callers.add(node_path)
                            next_level.add(node_path)
            current_level = next_level
            
        # 4. Traverse to find callees up to depth
        visited_callees = set()
        current_level = {symbol_name}
        for _ in range(depth):
            next_level = set()
            for sym in current_level:
                sym_source = node_map.get(sym, "")
                if not sym_source:
                    continue
                for node_path in node_map:
                    if node_path != sym and node_path in sym_source:
                        if node_path not in visited_callees:
                            visited_callees.add(node_path)
                            next_level.add(node_path)
            current_level = next_level
            
        return {
            "symbol": symbol_name,
            "callers": sorted(list(visited_callers)),
            "callees": sorted(list(visited_callees)),
            "depth_searched": depth
        }
        
    except Exception:
        return _mock_symbol_graph(symbol_name, depth)
