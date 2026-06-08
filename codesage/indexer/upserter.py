import sqlite3
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from indexer.chunker import Chunk

class Upserter:
    def __init__(self, qdrant_url: str, collection_name: str, sqlite_path: str):
        self.qdrant = QdrantClient(url=qdrant_url)
        self.collection_name = collection_name
        self.sqlite_path = sqlite_path

    def ensure_collection(self) -> None:
        """Create collection if it doesn't exist. Idempotent."""
        if not self.qdrant.collection_exists(self.collection_name):
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
                on_disk_payload=True
            )
            
        with sqlite3.connect(self.sqlite_path) as conn:
            cursor = conn.cursor()
            # Note: We need a unique constraint for INSERT OR REPLACE to work properly.
            # Usually chunk_id is unique, so we can make it the PRIMARY KEY.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS symbol_index (
                    node_path TEXT,
                    chunk_id TEXT PRIMARY KEY,
                    file_path TEXT
                )
            ''')
            conn.commit()

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Upsert to Qdrant and write symbol map to SQLite."""
        if not chunks:
            return
            
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_embeddings = embeddings[i:i + batch_size]
            
            points = []
            for chunk, embedding in zip(batch_chunks, batch_embeddings):
                points.append(
                    PointStruct(
                        id=chunk.chunk_id,
                        vector=embedding,
                        payload={
                            "file_path": chunk.file_path,
                            "node_path": chunk.node_path,
                            "node_type": chunk.node_type,
                            "language": chunk.language,
                            "signature": chunk.signature,
                            "docstring": chunk.docstring,
                            "line_start": chunk.line_start,
                            "line_end": chunk.line_end,
                            "chunk_index": chunk.chunk_index,
                            "total_chunks": chunk.total_chunks
                        }
                    )
                )
                
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=points
            )

        with sqlite3.connect(self.sqlite_path) as conn:
            cursor = conn.cursor()
            rows = [(c.node_path, c.chunk_id, c.file_path) for c in chunks]
            cursor.executemany('''
                INSERT OR REPLACE INTO symbol_index (node_path, chunk_id, file_path)
                VALUES (?, ?, ?)
            ''', rows)
            conn.commit()
