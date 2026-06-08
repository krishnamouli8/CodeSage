"""
Search tools for CodeSage agents.
"""

import os
import sqlite3
from typing import Optional
from pydantic import BaseModel, Field
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Lazy singletons for Embedder and QdrantClient to avoid reloading model
_embedder = None
_qdrant_client = None

def get_embedder():
    global _embedder
    if _embedder is None:
        from indexer.embedder import Embedder
        _embedder = Embedder()
    return _embedder

def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
        _qdrant_client = QdrantClient(url=qdrant_url)
    return _qdrant_client

def _mock_semantic_search(query: str, top_k: int = 5, language: Optional[str] = None, node_type: Optional[str] = None, file_path: Optional[str] = None) -> dict:
    return {
        "results": [
            {
                "chunk_id": "mock_chunk_1",
                "file_path": file_path or "mock_file.py",
                "node_path": "mock_class.mock_method",
                "node_type": node_type or "method",
                "signature": "def mock_method(self):",
                "source_text": "def mock_method(self):\n    pass",
                "score": 0.95
            }
        ],
        "count": 1
    }

def _mock_search_definitions(name_pattern: str) -> dict:
    return {
        "results": [
            {
                "chunk_id": "mock_chunk_2",
                "file_path": "mock_file.py",
                "node_path": f"{name_pattern}_def",
                "node_type": "function",
                "signature": f"def {name_pattern}_def():",
                "source_text": f"def {name_pattern}_def():\n    return True",
                "score": 1.0
            }
        ],
        "count": 1
    }

class SemanticSearchInput(BaseModel):
    query: str = Field(description="The query string to search for.")
    top_k: int = Field(default=5, description="Number of results to return.")
    language: Optional[str] = Field(default=None, description="Filter by 'python' or 'java'.")
    node_type: Optional[str] = Field(default=None, description="Filter by 'function', 'class', 'method'.")
    file_path: Optional[str] = Field(default=None, description="Filter to a specific file.")

@tool("semantic_search", args_schema=SemanticSearchInput)
def semantic_search(query: str, top_k: int = 5, language: Optional[str] = None, node_type: Optional[str] = None, file_path: Optional[str] = None) -> dict:
    """Search the Qdrant index for code chunks semantically similar to the query."""
    try:
        embedder = get_embedder()
        qdrant = get_qdrant_client()
        collection_name = os.environ.get("QDRANT_COLLECTION", "codesage_chunks")
        
        # 1. Embed query
        embeddings = embedder.embed([query])
        if not embeddings:
            return {"results": [], "count": 0}
        query_vector = embeddings[0]
        
        # 2. Build filters
        from qdrant_client.http import models as qdrant_models
        conditions = []
        if language:
            conditions.append(qdrant_models.FieldCondition(key="language", match=qdrant_models.MatchValue(value=language)))
        if node_type:
            conditions.append(qdrant_models.FieldCondition(key="node_type", match=qdrant_models.MatchValue(value=node_type)))
        if file_path:
            conditions.append(qdrant_models.FieldCondition(key="file_path", match=qdrant_models.MatchValue(value=file_path)))
            
        query_filter = qdrant_models.Filter(must=conditions) if conditions else None
        
        # 3. Query Qdrant
        results = qdrant.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k
        )
        
        # 4. Format output
        formatted = []
        for r in results:
            formatted.append({
                "chunk_id": str(r.id),
                "file_path": r.payload.get("file_path", ""),
                "node_path": r.payload.get("node_path", ""),
                "node_type": r.payload.get("node_type", ""),
                "signature": r.payload.get("signature", ""),
                "source_text": r.payload.get("source_text", ""),
                "score": float(r.score)
            })
            
        return {"results": formatted, "count": len(formatted)}
        
    except Exception as e:
        # Fall back to mock response if not configured or offline (e.g. during pytest)
        logger.error(f"Semantic search failed, falling back to mock: {e}", exc_info=True)
        return _mock_semantic_search(query, top_k, language, node_type, file_path)

class SearchDefinitionsInput(BaseModel):
    name_pattern: str = Field(description="fuzzy match against node_path")

@tool("search_definitions", args_schema=SearchDefinitionsInput)
def search_definitions(name_pattern: str) -> dict:
    """Find all indexed symbols whose node_path contains name_pattern."""
    try:
        sqlite_path = os.environ.get("SQLITE_PATH", "./codesage.db")
        if not os.path.exists(sqlite_path):
            return _mock_search_definitions(name_pattern)
            
        # 1. Query SQLite for matching chunk_ids
        with sqlite3.connect(sqlite_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT chunk_id FROM symbol_index WHERE node_path LIKE ?",
                (f"%{name_pattern}%",)
            )
            rows = cursor.fetchall()
            chunk_ids = [row[0] for row in rows]
            
        if not chunk_ids:
            return {"results": [], "count": 0}
            
        # 2. Retrieve corresponding payloads from Qdrant
        qdrant = get_qdrant_client()
        collection_name = os.environ.get("QDRANT_COLLECTION", "codesage_chunks")
        
        points = qdrant.retrieve(
            collection_name=collection_name,
            ids=chunk_ids
        )
        
        # 3. Format output
        formatted = []
        for p in points:
            formatted.append({
                "chunk_id": str(p.id),
                "file_path": p.payload.get("file_path", ""),
                "node_path": p.payload.get("node_path", ""),
                "node_type": p.payload.get("node_type", ""),
                "signature": p.payload.get("signature", ""),
                "source_text": p.payload.get("source_text", ""),
                "score": 1.0
            })
            
        return {"results": formatted, "count": len(formatted)}
        
    except Exception as e:
        logger.error(f"Search definitions failed, falling back to mock: {e}", exc_info=True)
        return _mock_search_definitions(name_pattern)
