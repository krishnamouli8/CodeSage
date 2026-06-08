"""
Index route for CodeSage API.

Triggers the offline indexing pipeline in a background thread.
Uses a threading.Event to prevent concurrent indexing runs.
"""

import os
import threading
from fastapi import APIRouter, Response

from api.models import IndexRequest, IndexResponse

router = APIRouter(tags=["index"])

# Module-level event to track if indexing is running
_indexing_event = threading.Event()


def _run_indexing_pipeline(repo_path: str) -> None:
    """Execute the full indexing pipeline in a background thread."""
    from dotenv import load_dotenv
    load_dotenv()

    from indexer.walker import walk_repo
    from indexer.parser import parse_file
    from indexer.chunker import chunk_nodes
    from indexer.embedder import Embedder
    from indexer.upserter import Upserter

    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    collection_name = os.environ.get("QDRANT_COLLECTION", "codesage_chunks")
    sqlite_path = os.environ.get("SQLITE_PATH", "./codesage.db")

    try:
        embedder = Embedder()
        upserter = Upserter(qdrant_url, collection_name, sqlite_path)
        upserter.ensure_collection()

        for file_path, source_text in walk_repo(repo_path):
            nodes = parse_file(file_path, source_text)
            if not nodes:
                continue

            chunks = chunk_nodes(nodes)
            if not chunks:
                continue

            chunk_texts = [c.source_text for c in chunks]
            embeddings = embedder.embed(chunk_texts)
            upserter.upsert(chunks, embeddings)
    finally:
        _indexing_event.clear()


@router.post("/index", response_model=IndexResponse)
def trigger_index(request: IndexRequest, response: Response):
    """Trigger the indexing pipeline for a repository."""
    if _indexing_event.is_set():
        response.status_code = 200
        return IndexResponse(status="already_running", repo_path=request.repo_path)

    _indexing_event.set()

    thread = threading.Thread(
        target=_run_indexing_pipeline,
        args=(request.repo_path,),
        daemon=True,
    )
    thread.start()

    response.status_code = 202
    return IndexResponse(status="started", repo_path=request.repo_path)
