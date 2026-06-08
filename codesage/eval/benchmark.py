"""
SWE-bench Lite evaluation harness for CodeSage.

Submits tasks to the CodeSage API, polls for results, independently
verifies via test commands, and produces a JSON metrics report.
"""

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import requests

from eval.metrics import (
    EvalResult,
    resolve_rate,
    patch_apply_rate,
    latency_p50,
    latency_p99,
    correction_recovery_rate,
    hallucination_rate,
)


@dataclass
class SWETask:
    """A single task from the SWE-bench Lite dataset."""
    task_id: str
    repo_path: str          # path to a local git repo at the base commit
    task_description: str   # the natural-language task
    test_command: str       # e.g. "pytest tests/test_foo.py"


class SWEBenchRunner:
    """Runs SWE-bench Lite tasks against the CodeSage API and collects metrics."""

    def __init__(self, api_base_url: str = "http://localhost:8000"):
        self.api_base_url = api_base_url.rstrip("/")

    def run_task(self, task: SWETask) -> EvalResult:
        """Submit task to API, poll until done, run test command, return result."""
        start_time = time.time()

        # 1. Submit task
        try:
            resp = requests.post(
                f"{self.api_base_url}/tasks",
                json={"raw_task": task.task_description, "repo_path": task.repo_path},
                timeout=10,
            )
            resp.raise_for_status()
            api_task_id = resp.json()["task_id"]
        except Exception as e:
            elapsed = time.time() - start_time
            return EvalResult(
                task_id=task.task_id,
                resolved=False,
                patch_applied=False,
                retrieval_relevant=False,
                latency_seconds=elapsed,
                retry_count=0,
                tests_run=0,
                tests_failed=0,
                error_message=f"API submission failed: {e}",
            )

        # 2. Poll for completion
        terminal_statuses = {"done", "failed", "partial"}
        poll_interval = 2.0
        max_wait = 180.0
        status = "pending"
        result_data = {}

        while (time.time() - start_time) < max_wait:
            try:
                poll_resp = requests.get(
                    f"{self.api_base_url}/tasks/{api_task_id}", timeout=10
                )
                poll_resp.raise_for_status()
                result_data = poll_resp.json()
                status = result_data.get("status", "pending")
                if status in terminal_statuses:
                    break
            except Exception:
                pass
            time.sleep(poll_interval)

        elapsed = time.time() - start_time

        # 3. If timed out
        if status not in terminal_statuses:
            return EvalResult(
                task_id=task.task_id,
                resolved=False,
                patch_applied=False,
                retrieval_relevant=False,
                latency_seconds=elapsed,
                retry_count=result_data.get("retry_count", 0),
                tests_run=0,
                tests_failed=0,
                error_message="Polling timeout (180s)",
            )

        # 4. Run test command independently to verify
        patch_applied = bool(result_data.get("diff", "").strip())
        tests_run = 0
        tests_failed = 0
        resolved = False

        try:
            test_result = subprocess.run(
                task.test_command.split(),
                cwd=task.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            resolved = test_result.returncode == 0
            # Parse output for counts (best effort)
            if "passed" in test_result.stdout:
                tests_run = 1
            if "failed" in test_result.stdout or "FAILED" in test_result.stdout:
                tests_failed = 1
        except subprocess.TimeoutExpired:
            resolved = False
            tests_failed = 1
        except Exception as e:
            resolved = False

        return EvalResult(
            task_id=task.task_id,
            resolved=resolved,
            patch_applied=patch_applied,
            retrieval_relevant=False,  # manually labelled
            latency_seconds=elapsed,
            retry_count=result_data.get("retry_count", 0),
            tests_run=tests_run,
            tests_failed=tests_failed,
            error_message=result_data.get("error_message", ""),
        )

    def run_suite(self, tasks: list[SWETask], output_path: str) -> None:
        """Run all tasks, compute all metrics, write JSON report to output_path."""
        results: list[EvalResult] = []

        for i, task in enumerate(tasks, 1):
            print(f"[{i}/{len(tasks)}] Running task: {task.task_id}")
            result = self.run_task(task)
            results.append(result)
            print(f"  → resolved={result.resolved}, latency={result.latency_seconds:.1f}s")

        # Compute metrics
        metrics = {
            "resolve_rate": round(resolve_rate(results), 4),
            "patch_apply_rate": round(patch_apply_rate(results), 4),
            "latency_p50": round(latency_p50(results), 2),
            "latency_p99": round(latency_p99(results), 2),
            "correction_recovery_rate": round(correction_recovery_rate(results), 4),
            "hallucination_rate": round(hallucination_rate(results), 4),
        }

        report = {
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "task_count": len(tasks),
            "metrics": metrics,
            "results": [asdict(r) for r in results],
        }

        # Write report
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n{'='*50}")
        print(f"Report written to {output_path}")
        print(f"Tasks: {len(tasks)}")
        for name, value in metrics.items():
            print(f"  {name}: {value}")


def _load_tasks_from_directory(dataset_dir: str) -> list[SWETask]:
    """Load SWETask objects from JSON files in the dataset directory."""
    tasks = []
    dataset_path = Path(dataset_dir)

    if not dataset_path.exists():
        print(f"Warning: Dataset directory {dataset_dir} does not exist")
        return tasks

    for json_file in sorted(dataset_path.glob("*.json")):
        try:
            with open(json_file) as f:
                data = json.load(f)
            tasks.append(SWETask(
                task_id=data["task_id"],
                repo_path=data["repo_path"],
                task_description=data["task_description"],
                test_command=data["test_command"],
            ))
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Skipping {json_file.name}: {e}")

    return tasks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CodeSage SWE-bench Lite Evaluator")
    parser.add_argument(
        "--dataset",
        default="eval/dataset/",
        help="Path to directory containing SWETask JSON files",
    )
    parser.add_argument(
        "--output",
        default="eval/report.json",
        help="Path to write the JSON report",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the CodeSage API",
    )

    args = parser.parse_args()

    tasks = _load_tasks_from_directory(args.dataset)
    if not tasks:
        print("No tasks found. Place SWETask JSON files in the dataset directory.")
        print("Expected format: {task_id, repo_path, task_description, test_command}")
    else:
        runner = SWEBenchRunner(api_base_url=args.api_url)
        runner.run_suite(tasks, args.output)
