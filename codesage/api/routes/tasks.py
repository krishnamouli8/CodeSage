"""
Task submission and polling routes for CodeSage API.
"""

import json
from uuid import uuid4
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException

from api.models import SubmitTaskRequest, SubmitTaskResponse, TaskResultResponse
from api.main import get_db

router = APIRouter(tags=["tasks"])

# Thread pool for background task execution
_executor = ThreadPoolExecutor(max_workers=2)


def _execute_task_background(task_id: str, raw_task: str) -> None:
    """Run the agent graph in a background thread and persist the result."""
    from agents.graph import run_task
    from dataclasses import asdict

    db = get_db()

    try:
        # Update status to running
        db.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            ("running", datetime.now(timezone.utc).isoformat(), task_id)
        )
        db.commit()

        # Execute the full graph
        final_state = run_task(task_id, raw_task)

        # Serialize the result
        # Convert dataclass objects to dicts for JSON serialization
        serializable = {}
        for key, value in final_state.items():
            if hasattr(value, "__dataclass_fields__"):
                serializable[key] = asdict(value)
            elif isinstance(value, list) and value and hasattr(value[0], "__dataclass_fields__"):
                serializable[key] = [asdict(v) for v in value]
            else:
                serializable[key] = value

        result_json = json.dumps(serializable, default=str)
        status = final_state.get("status", "failed")

        db.execute(
            "UPDATE tasks SET status = ?, result_json = ?, updated_at = ? WHERE task_id = ?",
            (status, result_json, datetime.now(timezone.utc).isoformat(), task_id)
        )
        db.commit()

    except Exception as e:
        db.execute(
            "UPDATE tasks SET status = ?, result_json = ?, updated_at = ? WHERE task_id = ?",
            ("failed", json.dumps({"error_message": str(e)}), datetime.now(timezone.utc).isoformat(), task_id)
        )
        db.commit()


@router.post("/tasks", status_code=202, response_model=SubmitTaskResponse)
def submit_task(request: SubmitTaskRequest):
    """Submit a new task for execution. Returns immediately with task_id."""
    task_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db = get_db()
    db.execute(
        "INSERT INTO tasks (task_id, status, raw_task, result_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, "pending", request.raw_task, None, now, now)
    )
    db.commit()

    # Submit to background thread
    _executor.submit(_execute_task_background, task_id, request.raw_task)

    return SubmitTaskResponse(task_id=task_id, status="pending")


@router.get("/tasks/{task_id}", response_model=TaskResultResponse)
def get_task(task_id: str):
    """Poll for task results by task_id."""
    db = get_db()
    row = db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    status = row["status"]
    raw_task = row["raw_task"] or ""
    result_json_str = row["result_json"]

    # Default response for non-terminal statuses
    response = TaskResultResponse(
        task_id=task_id,
        status=status,
        raw_task=raw_task,
        diff="",
        test_passed=None,
        agent_trace=[],
        retry_count=0,
        error_message=""
    )

    # If terminal and we have result data, deserialize it
    if status in ("done", "failed", "partial") and result_json_str:
        try:
            result_data = json.loads(result_json_str)

            # Build diff from completed_edits
            completed_edits = result_data.get("completed_edits", [])
            diffs = [e.get("diff", "") for e in completed_edits if isinstance(e, dict) and e.get("diff")]
            diff_text = "\n---\n".join(diffs)

            # Extract test_passed
            test_result = result_data.get("test_result")
            test_passed = None
            if isinstance(test_result, dict):
                test_passed = test_result.get("passed")

            response = TaskResultResponse(
                task_id=task_id,
                status=status,
                raw_task=raw_task,
                diff=diff_text,
                test_passed=test_passed,
                agent_trace=result_data.get("agent_trace", []),
                retry_count=result_data.get("retry_count", 0),
                error_message=result_data.get("error_message", "")
            )
        except (json.JSONDecodeError, KeyError):
            pass  # Return the default response

    return response
