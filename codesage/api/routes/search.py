"""
Semantic search route for CodeSage API.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from api.models import SearchResponse, SearchResult
from tools.search import semantic_search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Search query string"),
    top_k: int = Query(5, description="Number of results to return"),
    language: Optional[str] = Query(None, description="Filter by language"),
    node_type: Optional[str] = Query(None, description="Filter by node type"),
):
    """Search the Qdrant index for semantically similar code chunks."""
    try:
        raw_result = semantic_search.invoke({
            "query": q,
            "top_k": top_k,
            "language": language,
            "node_type": node_type,
        })
    except Exception:
        raise HTTPException(status_code=503, detail="Search index unavailable")

    # Transform raw tool results into SearchResult models
    results = []
    for item in raw_result.get("results", []):
        results.append(SearchResult(
            chunk_id=item.get("chunk_id", ""),
            file_path=item.get("file_path", ""),
            node_path=item.get("node_path", ""),
            node_type=item.get("node_type", ""),
            signature=item.get("signature", ""),
            source_text=item.get("source_text", ""),
            score=item.get("score", 0.0),
        ))

    return SearchResponse(
        results=results,
        count=len(results),
        query=q,
    )
