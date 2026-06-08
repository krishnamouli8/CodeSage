import os
import sys
from dotenv import load_dotenv
from indexer.walker import walk_repo
from indexer.parser import parse_file
from indexer.chunker import chunk_nodes
from indexer.embedder import Embedder
from indexer.upserter import Upserter

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m indexer.__main__ <repo_path>")
        sys.exit(1)
        
    repo_path = sys.argv[1]
    
    load_dotenv()
    
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    collection_name = os.environ.get("QDRANT_COLLECTION", "codesage_chunks")
    sqlite_path = os.environ.get("SQLITE_PATH", "./codesage.db")
    
    print(f"Starting indexer for repository: {repo_path}")
    print("Initializing embedder and upserter...")
    
    embedder = Embedder()
    upserter = Upserter(qdrant_url, collection_name, sqlite_path)
    upserter.ensure_collection()
    
    stats = {
        "files_processed": 0,
        "nodes_parsed": 0,
        "chunks_created": 0,
        "vectors_upserted": 0
    }
    
    for file_path, source_text in walk_repo(repo_path):
        stats["files_processed"] += 1
        
        nodes = parse_file(file_path, source_text)
        if not nodes:
            continue
        stats["nodes_parsed"] += len(nodes)
        
        chunks = chunk_nodes(nodes)
        if not chunks:
            continue
        stats["chunks_created"] += len(chunks)
        
        chunk_texts = [c.source_text for c in chunks]
        embeddings = embedder.embed(chunk_texts)
        
        upserter.upsert(chunks, embeddings)
        stats["vectors_upserted"] += len(chunks)
        
        print(f"Processed {file_path} ({len(chunks)} chunks)")
        
    print("\n--- Indexing Complete ---")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Nodes parsed:    {stats['nodes_parsed']}")
    print(f"Chunks created:  {stats['chunks_created']}")
    print(f"Vectors upserted:{stats['vectors_upserted']}")

if __name__ == "__main__":
    main()
