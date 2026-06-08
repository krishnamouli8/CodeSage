"""
FastAPI application for CodeSage.

Provides the HTTP API for task submission, search, indexing, and health checks.
Uses a lifespan context manager for startup/shutdown lifecycle.
"""

import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Module-level SQLite connection (shared across the app lifetime)
_db_connection: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    """Return the module-level SQLite connection."""
    assert _db_connection is not None, "Database not initialized. Is the app running?"
    return _db_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the FastAPI app."""
    global _db_connection

    # ── Startup ────────────────────────────────────────────────────────────
    db_path = os.environ.get("SQLITE_PATH", "./codesage_tasks.db")
    _db_connection = sqlite3.connect(db_path, check_same_thread=False)
    _db_connection.row_factory = sqlite3.Row

    # Create tasks table
    _db_connection.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            status TEXT,
            raw_task TEXT,
            result_json TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    _db_connection.commit()

    # Try to confirm Qdrant is reachable (non-fatal if not)
    try:
        from indexer.upserter import Upserter
        qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
        collection_name = os.environ.get("QDRANT_COLLECTION", "codesage_chunks")
        sqlite_path = os.environ.get("SQLITE_PATH", "./codesage.db")
        upserter = Upserter(qdrant_url, collection_name, sqlite_path)
        upserter.ensure_collection()
    except Exception:
        # Qdrant not available — the app can still serve non-search routes
        pass

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────
    if _db_connection:
        _db_connection.close()
        _db_connection = None


# ── App creation ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="CodeSage",
    version="0.1.0",
    description="Autonomous multi-agent software engineering system",
    lifespan=lifespan,
)

# CORS — allow all origins for local VS Code extension access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz():
    """Health check endpoint. No auth, no DB call."""
    return {"status": "ok"}


# ── Include routers ───────────────────────────────────────────────────────────

from api.routes.tasks import router as tasks_router
from api.routes.search import router as search_router
from api.routes.index import router as index_router

app.include_router(tasks_router)
app.include_router(search_router)
app.include_router(index_router)
