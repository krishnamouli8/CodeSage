"""
Evaluation metrics for CodeSage benchmark results.

Provides six metric functions that each take a list of EvalResult
and return a float, plus the EvalResult dataclass.
"""

from dataclasses import dataclass
import statistics


@dataclass
class EvalResult:
    """Result of a single evaluation task."""
    task_id: str
    resolved: bool              # True if all tests passed after patch
    patch_applied: bool         # True if patch applied without syntax error
    retrieval_relevant: bool    # manually labelled for a subset
    latency_seconds: float
    retry_count: int
    tests_run: int
    tests_failed: int
    error_message: str


def resolve_rate(results: list[EvalResult]) -> float:
    """% of tasks where resolved=True."""
    if not results:
        return 0.0
    return sum(1 for r in results if r.resolved) / len(results)


def patch_apply_rate(results: list[EvalResult]) -> float:
    """% of tasks where patch_applied=True."""
    if not results:
        return 0.0
    return sum(1 for r in results if r.patch_applied) / len(results)


def latency_p50(results: list[EvalResult]) -> float:
    """Median latency in seconds."""
    if not results:
        return 0.0
    latencies = sorted(r.latency_seconds for r in results)
    return statistics.median(latencies)


def latency_p99(results: list[EvalResult]) -> float:
    """99th-percentile latency in seconds."""
    if not results:
        return 0.0
    latencies = sorted(r.latency_seconds for r in results)
    # For small samples, use the max as p99 approximation
    idx = int(len(latencies) * 0.99)
    idx = min(idx, len(latencies) - 1)
    return latencies[idx]


def correction_recovery_rate(results: list[EvalResult]) -> float:
    """% of tasks that initially failed but resolved within 3 retries."""
    if not results:
        return 0.0
    # Tasks that used retries (retry_count > 0) and still resolved
    retried = [r for r in results if r.retry_count > 0]
    if not retried:
        return 0.0
    recovered = sum(1 for r in retried if r.resolved)
    return recovered / len(retried)


def hallucination_rate(results: list[EvalResult]) -> float:
    """Proxy: % of tasks where patch_applied=False and error contains 'NameError' or 'AttributeError'."""
    if not results:
        return 0.0
    hallucinated = sum(
        1 for r in results
        if not r.patch_applied and (
            "NameError" in r.error_message or "AttributeError" in r.error_message
        )
    )
    return hallucinated / len(results)
