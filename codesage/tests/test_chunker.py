from indexer.parser import ParsedNode
from indexer.chunker import chunk_nodes

def create_mock_node(word_count: int) -> ParsedNode:
    words = ["word"] * word_count
    # Split into lines of 10 words each
    lines = []
    for i in range(0, word_count, 10):
        lines.append(" ".join(words[i:i+10]))
    source_text = "\n".join(lines)
    
    return ParsedNode(
        file_path="mock.py",
        node_path="mock_func",
        node_type="function",
        language="python",
        source_text=source_text,
        signature="def mock_func():",
        docstring="",
        line_start=1,
        line_end=len(lines)
    )

def test_chunker_small_node():
    node = create_mock_node(100)
    chunks = chunk_nodes([node], max_tokens=512)
    
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].total_chunks == 1
    assert len(chunks[0].source_text.split()) == 100

def test_chunker_large_node():
    node = create_mock_node(1500)
    chunks = chunk_nodes([node], max_tokens=512)
    
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.source_text.split()) <= 512

def test_chunker_metadata():
    node = create_mock_node(1500)
    chunks = chunk_nodes([node], max_tokens=512)
    
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.file_path == "mock.py"
        assert chunk.node_path == "mock_func"
        
def test_chunker_no_empty_source():
    node = create_mock_node(1500)
    chunks = chunk_nodes([node], max_tokens=512)
    
    for chunk in chunks:
        assert chunk.source_text.strip() != ""
