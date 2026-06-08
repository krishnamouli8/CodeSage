"""
SelfCorrector agent and TestRunner node for CodeSage LangGraph pipeline.

The TestRunner executes tests scoped to files touched by completed edits.
The SelfCorrector diagnoses test failures and produces CorrectionHints for the Coder.
"""

import os
from typing import Dict, Any

from agents.state import TaskState, TestResult, CorrectionHint
from tools.exec_tools import run_tests

from pydantic import BaseModel, Field


def _infer_language(file_path: str) -> str:
    """Infer language from file extension."""
    if file_path.endswith(".py"):
        return "python"
    elif file_path.endswith(".java"):
        return "java"
    return "python"  # default


def test_runner_node(state: TaskState) -> dict:
    """Run tests scoped to files touched by completed_edits."""
    completed_edits = state.get("completed_edits", [])
    
    if not completed_edits:
        return {
            "status": "done",
            "test_result": TestResult(
                passed=True,
                stdout="No edits to test.",
                stderr="",
                duration_seconds=0.0,
                tests_run=0,
                tests_failed=0
            ),
            "agent_trace": ["TestRunner: no completed edits, marking done"]
        }

    # Collect unique file paths
    unique_files = list({edit.file_path for edit in completed_edits if edit.applied})
    
    if not unique_files:
        return {
            "status": "done",
            "test_result": TestResult(
                passed=True,
                stdout="No applied edits to test.",
                stderr="",
                duration_seconds=0.0,
                tests_run=0,
                tests_failed=0
            ),
            "agent_trace": ["TestRunner: no applied edits, marking done"]
        }

    all_passed = True
    total_tests_run = 0
    total_tests_failed = 0
    combined_stdout = []
    combined_stderr = []
    first_failure = None
    
    for file_path in unique_files:
        language = _infer_language(file_path)
        result = run_tests.invoke({"scope": file_path, "language": language})
        
        passed = result.get("passed", False)
        tests_run = result.get("tests_run", 0)
        tests_failed = result.get("tests_failed", 0)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        
        total_tests_run += tests_run
        total_tests_failed += tests_failed
        combined_stdout.append(f"=== {file_path} ===\n{stdout}")
        combined_stderr.append(f"=== {file_path} ===\n{stderr}")
        
        if not passed:
            all_passed = False
            if first_failure is None:
                first_failure = TestResult(
                    passed=False,
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=0.0,
                    tests_run=tests_run,
                    tests_failed=tests_failed
                )

    combined_result = TestResult(
        passed=all_passed,
        stdout="\n".join(combined_stdout),
        stderr="\n".join(combined_stderr),
        duration_seconds=0.0,
        tests_run=total_tests_run,
        tests_failed=total_tests_failed
    )

    if all_passed:
        return {
            "status": "done",
            "test_result": combined_result,
            "agent_trace": [f"TestRunner: passed, {total_tests_run} tests run"]
        }
    else:
        # Use the first failure as test_result for the SelfCorrector
        return {
            "status": "correcting",
            "test_result": first_failure or combined_result,
            "agent_trace": [f"TestRunner: failed, {total_tests_run} tests run, {total_tests_failed} failed"]
        }


class SelfCorrectorOutput(BaseModel):
    failure_type: str = Field(
        description="syntax_error | type_error | logic_error | missing_import | api_violation | unknown"
    )
    affected_node_path: str = Field(
        description="The dotted node_path of the node that caused the failure"
    )
    suggested_fix: str = Field(
        description="A one-paragraph description of the suggested fix"
    )


def get_llm(model_name: str):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=model_name, temperature=0)


def self_corrector_node(state: TaskState) -> dict:
    """LangGraph node. Diagnoses test failure, produces CorrectionHint."""
    retry_count = state.get("retry_count", 0)
    
    # Max retries exceeded — bail out
    if retry_count >= 3:
        return {
            "status": "partial",
            "error_message": "SelfCorrector: max retries (3) reached. Task partially complete.",
            "agent_trace": [f"SelfCorrector: max retries reached (retry_count={retry_count}), status=partial"]
        }

    test_result = state.get("test_result")
    completed_edits = state.get("completed_edits", [])

    # Gather diffs
    diffs = []
    for edit in completed_edits:
        if edit.applied and edit.diff:
            diffs.append(f"--- {edit.file_path} ({edit.node_path}) ---\n{edit.diff}")
    diffs_text = "\n\n".join(diffs) if diffs else "(no diffs available)"

    # Gather test output
    test_stdout = test_result.stdout if test_result else "(no stdout)"
    test_stderr = test_result.stderr if test_result else "(no stderr)"

    # LLM prompt
    system_prompt = (
        "You are a diagnostic agent for an autonomous coding system.\n"
        "You are given failing test output and the unified diffs of all patches applied.\n"
        "Identify which AST node caused the failure, classify the failure type, "
        "and provide a one-paragraph suggested fix.\n"
        "Return ONLY JSON matching the requested schema."
    )

    user_prompt = (
        f"FAILING TEST STDOUT:\n{test_stdout}\n\n"
        f"FAILING TEST STDERR:\n{test_stderr}\n\n"
        f"APPLIED DIFFS:\n{diffs_text}\n\n"
        "Diagnose the root cause and return JSON with failure_type, affected_node_path, and suggested_fix."
    )

    primary_model_name = os.environ.get("MODEL_PRIMARY", "gemini-1.5-pro-latest")
    fallback_model_name = os.environ.get("MODEL_FALLBACK", "gemini-1.5-flash-latest")

    output_obj = None
    last_error = None

    for model_name in [primary_model_name, fallback_model_name]:
        try:
            llm = get_llm(model_name)
            structured_llm = llm.with_structured_output(SelfCorrectorOutput)
            output_obj = structured_llm.invoke(
                f"{system_prompt}\n\n{user_prompt}"
            )
            break
        except Exception as e:
            last_error = e
            continue

    if output_obj is None:
        # LLM failed — still increment retry and produce a generic hint
        hint = CorrectionHint(
            failure_type="unknown",
            affected_node_path="unknown",
            error_message=test_stderr[:500] if test_result else str(last_error),
            suggested_fix="LLM diagnosis failed. Review test output manually.",
            retry_number=retry_count + 1
        )
        return {
            "retry_count": retry_count + 1,
            "correction_hints": [hint],
            "status": "coding",
            "agent_trace": [
                f"SelfCorrector: LLM failed ({last_error}), produced generic hint, retry={retry_count + 1}"
            ]
        }

    hint = CorrectionHint(
        failure_type=output_obj.failure_type,
        affected_node_path=output_obj.affected_node_path,
        error_message=test_stderr[:500] if test_result else "",
        suggested_fix=output_obj.suggested_fix,
        retry_number=retry_count + 1
    )

    return {
        "retry_count": retry_count + 1,
        "correction_hints": [hint],
        "status": "coding",
        "agent_trace": [
            f"SelfCorrector: diagnosed {output_obj.failure_type} in {output_obj.affected_node_path}, retry={retry_count + 1}"
        ]
    }
