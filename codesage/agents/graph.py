"""
LangGraph state machine for CodeSage task execution pipeline.

Wires together all agent nodes into a compiled graph with conditional routing.
This module exports the compiled `graph` and a convenience `run_task` wrapper.
"""

from langgraph.graph import StateGraph, END

from agents.state import TaskState, initial_state
from agents.intent_parser import intent_parser_node
from agents.context_retriever import context_retriever_node
from agents.planner import planner_node
from agents.coder import coder_node
from agents.self_corrector import test_runner_node, self_corrector_node


# ── Routing functions ──────────────────────────────────────────────────────────

def _route_after_intent_parser(state: TaskState) -> str:
    """Route after IntentParser: fail → END, otherwise → context_retriever."""
    if state.get("status") == "failed":
        return END
    return "context_retriever"


def _route_after_context_retriever(state: TaskState) -> str:
    """Route after ContextRetriever: fail → END, otherwise → planner."""
    if state.get("status") == "failed":
        return END
    return "planner"


def _route_after_planner(state: TaskState) -> str:
    """Route after Planner: fail → END, otherwise → coder."""
    if state.get("status") == "failed":
        return END
    return "coder"


def _route_after_test_runner(state: TaskState) -> str:
    """Route after TestRunner: done → END, correcting → self_corrector, else → END."""
    status = state.get("status")
    if status == "done":
        return END
    if status == "correcting":
        return "self_corrector"
    return END


def _route_after_self_corrector(state: TaskState) -> str:
    """Route after SelfCorrector: partial → END, coding → coder, else → END."""
    status = state.get("status")
    if status == "partial":
        return END
    if status == "coding":
        return "coder"
    return END


# ── Graph construction ─────────────────────────────────────────────────────────

builder = StateGraph(TaskState)

# Register nodes
builder.add_node("intent_parser", intent_parser_node)
builder.add_node("context_retriever", context_retriever_node)
builder.add_node("planner", planner_node)
builder.add_node("coder", coder_node)
builder.add_node("test_runner", test_runner_node)
builder.add_node("self_corrector", self_corrector_node)

# Entry point
builder.set_entry_point("intent_parser")

# Conditional edges with fail-fast to END
builder.add_conditional_edges("intent_parser", _route_after_intent_parser)
builder.add_conditional_edges("context_retriever", _route_after_context_retriever)
builder.add_conditional_edges("planner", _route_after_planner)

# Unconditional edges
builder.add_edge("coder", "test_runner")

# Conditional edges for the correction loop
builder.add_conditional_edges("test_runner", _route_after_test_runner)
builder.add_conditional_edges("self_corrector", _route_after_self_corrector)

# Compile
graph = builder.compile()


# ── Convenience wrapper ────────────────────────────────────────────────────────

def run_task(task_id: str, raw_task: str) -> TaskState:
    """Convenience wrapper. Creates initial state, invokes graph, returns final state."""
    state = initial_state(task_id, raw_task)
    final_state = graph.invoke(state)
    return final_state
