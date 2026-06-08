"""
Agent State Schema for CodeSage LangGraph pipeline.

This file is the single source of truth for the shared state object passed between
all agent nodes. It must not import from any other agents/ modules to avoid circular imports.
"""

from dataclasses import dataclass
from typing import Annotated, TypedDict
import operator

@dataclass
class TaskSpec:
    raw_task: str             # original user input, unchanged
    task_type: str            # "bugfix" | "feature" | "refactor" | "unknown"
    target_symbols: list[str] # symbol names the task likely touches, may be empty
    acceptance_criteria: list[str]  # what "done" looks like, extracted by IntentParser
    constraints: list[str]    # e.g. "do not add new dependencies", may be empty
    confidence: float         # 0.0–1.0, IntentParser's confidence in its own parse

@dataclass
class ContextChunk:
    chunk_id: str
    file_path: str
    node_path: str
    node_type: str
    source_text: str
    signature: str
    score: float              # retrieval similarity score 0.0–1.0

@dataclass
class ContextBundle:
    chunks: list[ContextChunk]
    query_count: int          # how many Qdrant queries were run
    retrieval_latency_ms: float

@dataclass
class EditSpec:
    file_path: str
    node_path: str            # dotted path of the AST node to modify
    operation: str            # "replace" | "insert_after" | "delete"
    rationale: str            # why this edit is needed (from Planner)
    generated_source: str     # filled in by Coder, empty string initially
    applied: bool             # set to True by PatchApplier after successful apply
    diff: str                 # unified diff string, filled after apply

@dataclass
class PlanState:
    edits: list[EditSpec]     # ordered list — apply in sequence
    risk_level: str           # "low" | "medium" | "high"
    edit_count: int           # len(edits), stored separately for quick access

@dataclass
class CorrectionHint:
    failure_type: str         # "syntax_error" | "type_error" | "logic_error" | "missing_import" | "api_violation" | "unknown"
    affected_node_path: str   # which node_path the failure is in
    error_message: str        # raw error text from test runner
    suggested_fix: str        # natural language hint for the Coder
    retry_number: int         # 1, 2, or 3

@dataclass
class TestResult:
    passed: bool
    stdout: str
    stderr: str
    duration_seconds: float
    tests_run: int
    tests_failed: int

class TaskState(TypedDict):
    # Input
    task_id: str
    raw_task: str

    # Set by IntentParser
    task_spec: TaskSpec | None

    # Set by ContextRetriever
    context_bundle: ContextBundle | None

    # Set by Planner
    plan_state: PlanState | None

    # Updated by Coder and PatchApplier across multiple edits
    completed_edits: Annotated[list[EditSpec], operator.add]

    # Set by TestRunner
    test_result: TestResult | None

    # Set by SelfCorrector
    correction_hints: Annotated[list[CorrectionHint], operator.add]

    # Control flow
    retry_count: int
    status: str    # "pending" | "planning" | "coding" | "testing" | "correcting" | "done" | "failed" | "partial"
    error_message: str   # populated on failure, empty string otherwise

    # Observability
    agent_trace: Annotated[list[str], operator.add]   # append-only log of agent actions, human-readable

def initial_state(task_id: str, raw_task: str) -> TaskState:
    """Return a TaskState with all fields at their correct zero values."""
    return {
        "task_id": task_id,
        "raw_task": raw_task,
        "task_spec": None,
        "context_bundle": None,
        "plan_state": None,
        "completed_edits": [],
        "test_result": None,
        "correction_hints": [],
        "retry_count": 0,
        "status": "pending",
        "error_message": "",
        "agent_trace": []
    }
