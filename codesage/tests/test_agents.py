"""
Tests for the CodeSage LangGraph agent pipeline.

These tests exercise the full graph with real LLM calls via the Gemini API.
Requires GOOGLE_API_KEY to be set in the environment (loaded from .env).
"""

import os
import pytest
from dotenv import load_dotenv

# Load environment from .env before any agent imports
load_dotenv()

from agents.state import TaskState, initial_state, EditSpec
from agents.graph import graph, run_task


@pytest.fixture(autouse=True)
def _check_api_key():
    """Skip tests if no API key is configured."""
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set — skipping agent integration tests")


class TestRunTask:
    """Tests for the run_task convenience wrapper and graph execution."""

    def test_run_task_completes_with_valid_status(self):
        """run_task with a trivial task completes and returns a valid terminal status."""
        result = run_task("test-001", "Add a comment to the top of indexer/walker.py")
        
        assert isinstance(result, dict)
        assert result["status"] in {"done", "partial", "failed"}
        assert result["task_id"] == "test-001"

    def test_empty_raw_task_fails(self):
        """If raw_task is empty string, status == 'failed' and task_spec is None."""
        result = run_task("test-002", "")
        
        assert result["status"] == "failed"
        assert result.get("task_spec") is None

    def test_retry_count_never_exceeds_three(self):
        """retry_count never exceeds 3 in the final state."""
        result = run_task("test-003", "Fix a bug in the parser module")
        
        assert result.get("retry_count", 0) <= 3

    def test_agent_trace_is_nonempty(self):
        """agent_trace is a non-empty list after any completed run."""
        result = run_task("test-004", "Refactor the chunker to be more efficient")
        
        assert isinstance(result.get("agent_trace"), list)
        assert len(result["agent_trace"]) > 0

    def test_completed_edits_only_applied(self):
        """completed_edits only contains EditSpec objects where applied == True."""
        result = run_task("test-005", "Add logging to the embedder module")
        
        completed_edits = result.get("completed_edits", [])
        for edit in completed_edits:
            assert isinstance(edit, EditSpec)
            assert edit.applied is True
