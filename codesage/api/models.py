"""
Pydantic v2 request/response models for the CodeSage API.
"""

from pydantic import BaseModel, Field
from typing import Optional


class SubmitTaskRequest(BaseModel):
    """Request body for POST /tasks."""
    raw_task: str = Field(description="The natural-language task to execute")
    repo_path: str = Field(description="Absolute path to the repo to operate on")


class SubmitTaskResponse(BaseModel):
    """Response body for POST /tasks."""
    task_id: str = Field(description="Unique identifier for the submitted task")
    status: str = Field(default="pending", description="Always 'pending' on initial submission")


class TaskResultResponse(BaseModel):
    """Response body for GET /tasks/{task_id}."""
    task_id: str = Field(description="Unique identifier of the task")
    status: str = Field(description="Current task status")
    raw_task: str = Field(description="Original task description")
    diff: str = Field(default="", description="Concatenated diffs from all completed edits")
    test_passed: Optional[bool] = Field(default=None, description="None if tests haven't run yet")
    agent_trace: list[str] = Field(default_factory=list, description="Ordered log of agent actions")
    retry_count: int = Field(default=0, description="Number of self-correction retries")
    error_message: str = Field(default="", description="Error message if task failed")


class SearchRequest(BaseModel):
    """Request body for search queries."""
    query: str = Field(description="The search query string")
    top_k: int = Field(default=5, description="Number of results to return")
    language: Optional[str] = Field(default=None, description="Filter by language: 'python' or 'java'")
    node_type: Optional[str] = Field(default=None, description="Filter by node type: 'function', 'class', 'method'")


class SearchResult(BaseModel):
    """A single search result."""
    chunk_id: str = Field(description="Unique chunk identifier")
    file_path: str = Field(description="Path to the source file")
    node_path: str = Field(description="Dotted AST node path")
    node_type: str = Field(description="Type of AST node")
    signature: str = Field(description="Function/class signature")
    source_text: str = Field(description="Source code text of the chunk")
    score: float = Field(description="Relevance score")


class SearchResponse(BaseModel):
    """Response body for GET /search."""
    results: list[SearchResult] = Field(description="List of search results")
    count: int = Field(description="Number of results returned")
    query: str = Field(description="Original query string")


class IndexRequest(BaseModel):
    """Request body for POST /index."""
    repo_path: str = Field(description="Absolute path to the repo to index")


class IndexResponse(BaseModel):
    """Response body for POST /index."""
    status: str = Field(description="'started' or 'already_running'")
    repo_path: str = Field(description="Path to the repo being indexed")
