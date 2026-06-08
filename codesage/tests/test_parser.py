import os
import tempfile
import logging
from indexer.parser import parse_file
from indexer.walker import walk_repo

def test_parse_file_python_nodes():
    source_text = '''
def top_level():
    pass

class MyClass:
    """Class doc"""
    def method_one(self):
        pass
    def method_two(self):
        pass
'''
    nodes = parse_file("test.py", source_text)
    assert len(nodes) == 4
    
    types = [n.node_type for n in nodes]
    assert types.count("function") == 1
    assert types.count("class") == 1
    assert types.count("method") == 2

def test_node_path_method():
    source_text = '''
class MyClass:
    def my_method(self):
        pass
'''
    nodes = parse_file("test.py", source_text)
    method_node = next(n for n in nodes if n.node_type == "method")
    assert method_node.node_path == "MyClass.my_method"

def test_docstring_extraction():
    source_text = '''
def my_func():
    """This is a docstring."""
    pass
'''
    nodes = parse_file("test.py", source_text)
    assert len(nodes) == 1
    assert nodes[0].docstring == "This is a docstring."

def test_syntax_error(caplog):
    source_text = '''
def bad_func(
    pass
'''
    with caplog.at_level(logging.WARNING):
        nodes = parse_file("bad.py", source_text)
        assert len(nodes) == 0
        assert "Syntax error in bad.py" in caplog.text

def test_walk_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .git
        os.makedirs(os.path.join(tmpdir, ".git"))
        with open(os.path.join(tmpdir, ".git", "hidden.py"), "w") as f:
            f.write("pass")
            
        # Create __pycache__
        os.makedirs(os.path.join(tmpdir, "__pycache__"))
        with open(os.path.join(tmpdir, "__pycache__", "cache.py"), "w") as f:
            f.write("pass")
            
        # Create valid dir
        os.makedirs(os.path.join(tmpdir, "src"))
        with open(os.path.join(tmpdir, "src", "main.py"), "w") as f:
            f.write("pass")
            
        files = list(walk_repo(tmpdir))
        assert len(files) == 1
        assert files[0][0].endswith("main.py")
