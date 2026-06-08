import uuid
from dataclasses import dataclass
from indexer.parser import ParsedNode

@dataclass
class Chunk:
    chunk_id: str
    file_path: str
    node_path: str
    node_type: str
    language: str
    source_text: str
    signature: str
    docstring: str
    line_start: int
    line_end: int
    chunk_index: int
    total_chunks: int

def chunk_nodes(nodes: list[ParsedNode], max_tokens: int = 512) -> list[Chunk]:
    chunks = []
    
    for node in nodes:
        # A simple check first: if it fits entirely, avoid splitting overhead
        if len(node.source_text.split()) <= max_tokens:
            if node.source_text.strip():
                chunks.append(Chunk(
                    chunk_id=str(uuid.uuid4()),
                    file_path=node.file_path,
                    node_path=node.node_path,
                    node_type=node.node_type,
                    language=node.language,
                    source_text=node.source_text,
                    signature=node.signature,
                    docstring=node.docstring,
                    line_start=node.line_start,
                    line_end=node.line_end,
                    chunk_index=0,
                    total_chunks=1
                ))
            continue
            
        # Needs splitting at line boundaries
        lines = node.source_text.split("\n")
        current_chunk_lines = []
        current_chunk_tokens = 0
        node_chunks = []
        
        for line in lines:
            line_tokens = len(line.split())
            if current_chunk_tokens + line_tokens > max_tokens and current_chunk_lines:
                node_chunks.append("\n".join(current_chunk_lines))
                current_chunk_lines = []
                current_chunk_tokens = 0
                
            current_chunk_lines.append(line)
            current_chunk_tokens += line_tokens
            
        if current_chunk_lines:
            node_chunks.append("\n".join(current_chunk_lines))
            
        # In rare cases a single line might be longer than max_tokens, 
        # our logic just puts it in its own chunk.
        
        total_chunks = len(node_chunks)
        for i, chunk_text in enumerate(node_chunks):
            if chunk_text.strip():
                chunks.append(Chunk(
                    chunk_id=str(uuid.uuid4()),
                    file_path=node.file_path,
                    node_path=node.node_path,
                    node_type=node.node_type,
                    language=node.language,
                    source_text=chunk_text,
                    signature=node.signature,
                    docstring=node.docstring,
                    line_start=node.line_start,
                    line_end=node.line_end,
                    chunk_index=i,
                    total_chunks=total_chunks
                ))
                
    return chunks
