import pytest
import os
import subprocess
from unittest.mock import patch

from tools.search import semantic_search
from tools.ast_tools import apply_ast_patch, get_file_content, list_file_symbols
from tools.exec_tools import run_tests

def test_semantic_search():
    result = semantic_search.invoke({"query": "test query", "top_k": 5})
    assert isinstance(result, dict)
    assert "results" in result
    assert isinstance(result["results"], list)

def test_apply_ast_patch_invalid_syntax(tmp_path):
    # Setup dummy file
    test_file = tmp_path / "test.py"
    test_file.write_text("def test():\n    pass")
    
    # Invalid python syntax (missing colon, mismatched braces, etc)
    invalid_source = "def test() pass"
    
    result = apply_ast_patch.invoke({
        "file_path": str(test_file),
        "node_path": "test",
        "new_source": invalid_source
    })
    
    # We should gracefully fail on syntax error
    assert result.get("success") is False
    # Validate the file wasn't modified (assuming it's checked by the tool before write)
    assert test_file.read_text() == "def test():\n    pass"

def test_run_tests_passing(tmp_path):
    # Setup dummy passing pytest file
    test_file = tmp_path / "test_dummy.py"
    test_file.write_text("def test_ok():\n    assert True\n")
    
    result = run_tests.invoke({"scope": str(test_file), "language": "python"})
    assert result.get("passed") is True

@patch("subprocess.run")
def test_run_tests_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=60)
    
    result = run_tests.invoke({"scope": "dummy", "language": "python"})
    assert result.get("passed") is False
    assert result.get("error") == "timeout"

def test_get_file_content(tmp_path):
    # Create file with 20 lines
    test_file = tmp_path / "lines.txt"
    lines = [f"line {i}\n" for i in range(1, 21)]
    test_file.write_text("".join(lines))
    
    # lines 5 to 10 inclusive is 6 lines
    result = get_file_content.invoke({
        "file_path": str(test_file),
        "start_line": 5,
        "end_line": 10
    })
    
    content = result.get("content", "")
    assert len(content.splitlines()) == 6
    assert "line 5" in content
    assert "line 10" in content

def test_list_file_symbols(tmp_path):
    test_file = tmp_path / "symbols.py"
    test_file.write_text("def dummy(): pass\nclass Dummy:\n    pass")
    
    result = list_file_symbols.invoke({"file_path": str(test_file)})
    assert result.get("file_path") == str(test_file)
    assert "symbols" in result
