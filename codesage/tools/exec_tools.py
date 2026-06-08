"""
Execution tools for CodeSage agents.
"""

from pydantic import BaseModel, Field
from langchain_core.tools import tool
import subprocess
import os

class RunTestsInput(BaseModel):
    scope: str = Field(description="file path or test class name, e.g. 'tests/test_parser.py'")
    language: str = Field(default="python", description="'python' or 'java'")

@tool("run_tests", args_schema=RunTestsInput)
def run_tests(scope: str, language: str = "python") -> dict:
    """Run the test suite scoped to a file or class. 60-second timeout."""
    timeout = int(os.environ.get("TEST_TIMEOUT_SECONDS", "60"))
    
    if language == "python":
        cmd = ["pytest", scope, "-v", "--tb=short"]
    elif language == "java":
        cmd = ["mvn", "test", f"-Dtest={scope}", "-q"]
    else:
        return {"error": f"Unsupported language: {language}"}
        
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        passed = result.returncode == 0
        stdout = result.stdout
        stderr = result.stderr
        
        # Simple parsing for tests run/failed (mocked for simplicity, a real parser would parse pytest output)
        # Here we just look for passed/failed in the last line if possible, or leave it as 0
        tests_run = 1 if "collected" in stdout else 0
        tests_failed = 1 if not passed else 0
        
        return {
            "passed": passed,
            "stdout": stdout,
            "stderr": stderr,
            "tests_run": tests_run,
            "tests_failed": tests_failed,
            "duration_seconds": 0.0 # Could calculate this
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "error": "timeout",
            "stdout": "",
            "stderr": ""
        }
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "stdout": "",
            "stderr": ""
        }
