import asyncio
import time
from typing import List, Dict, Any
from agents.state import TaskState, ContextBundle, ContextChunk
from tools.search import semantic_search

async def _run_queries(queries: List[str]) -> List[Any]:
    """Run multiple Qdrant queries in parallel."""
    # We use asyncio.to_thread because semantic_search is a sync LangChain tool
    tasks = [
        asyncio.to_thread(semantic_search.invoke, {"query": q, "top_k": 8})
        for q in queries
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

def context_retriever_node(state: TaskState) -> dict:
    """LangGraph node. Reads state['task_spec'], writes state['context_bundle']."""
    task_spec = state.get("task_spec")
    if not task_spec:
        return {
            "status": "failed",
            "error_message": "ContextRetriever: missing task_spec in state",
            "agent_trace": ["ContextRetriever: failed, missing task_spec"]
        }

    # 1. Derive queries
    queries = []
    
    # 1 per target_symbol
    for sym in task_spec.target_symbols:
        queries.append(f"definition or usage of {sym}")
        
    # 1 from raw_task
    if task_spec.raw_task:
        queries.append(task_spec.raw_task)
        
    # up to 2 from acceptance_criteria
    for ac in task_spec.acceptance_criteria[:2]:
        queries.append(ac)
        
    # Cap to max 5 queries (if somehow we have more, but according to rules we just truncate)
    queries = queries[:5]
    if not queries:
        return {
            "status": "failed",
            "error_message": "ContextRetriever: could not derive any queries from task_spec",
            "agent_trace": ["ContextRetriever: failed, could not derive queries"]
        }

    # 2. Run queries in parallel and measure latency
    start_time = time.time()
    try:
        raw_results_list = asyncio.run(_run_queries(queries))
    except Exception as e:
        return {
            "status": "failed",
            "error_message": f"ContextRetriever: Qdrant query execution failed - {str(e)}",
            "agent_trace": [f"ContextRetriever: query execution failed - {str(e)}"]
        }
    
    end_time = time.time()
    latency_ms = (end_time - start_time) * 1000.0

    # 3. Deduplicate results
    # chunk_id -> dict with info and max score
    unique_chunks: Dict[str, dict] = {}
    
    for query_idx, result_obj in enumerate(raw_results_list):
        if isinstance(result_obj, Exception):
            # We can log this to console or trace, but let's just continue with other successful results
            continue
            
        # The tool returns a dict like: {"results": [...], "count": ...}
        # Be resilient to different formats
        if not isinstance(result_obj, dict):
            continue
            
        results = result_obj.get("results", [])
        for chunk in results:
            chunk_id = chunk.get("chunk_id")
            if not chunk_id:
                continue
                
            score = chunk.get("score", 0.0)
            if chunk_id not in unique_chunks:
                unique_chunks[chunk_id] = chunk
            else:
                if score > unique_chunks[chunk_id].get("score", 0.0):
                    unique_chunks[chunk_id] = chunk
                    unique_chunks[chunk_id]["score"] = score

    if not unique_chunks:
        return {
            "status": "failed",
            "error_message": "ContextRetriever: no results from Qdrant",
            "agent_trace": ["ContextRetriever: failed, no results from Qdrant"]
        }

    # 4. Re-rank chunks
    ranked_chunks = []
    for chunk_id, chunk_data in unique_chunks.items():
        semantic_score = chunk_data.get("score", 0.0)
        node_type = chunk_data.get("node_type", "").lower()
        
        if node_type in ["function", "method"]:
            bonus = 1.0
        elif node_type == "class":
            bonus = 0.7
        else:
            bonus = 0.5
            
        final_score = semantic_score * 0.7 + bonus * 0.3
        
        # Build ContextChunk dataclass instance
        context_chunk = ContextChunk(
            chunk_id=chunk_id,
            file_path=chunk_data.get("file_path", ""),
            node_path=chunk_data.get("node_path", ""),
            node_type=chunk_data.get("node_type", ""),
            source_text=chunk_data.get("source_text", ""),
            signature=chunk_data.get("signature", ""),
            score=final_score
        )
        ranked_chunks.append(context_chunk)
        
    # Sort descending by final score
    ranked_chunks.sort(key=lambda x: x.score, reverse=True)
    
    # 5. Take top 15
    top_chunks = ranked_chunks[:15]
    
    context_bundle = ContextBundle(
        chunks=top_chunks,
        query_count=len(queries),
        retrieval_latency_ms=latency_ms
    )
    
    trace_msg = f"ContextRetriever: ran {len(queries)} queries, retrieved {len(top_chunks)} unique chunks, top score={top_chunks[0].score:.4f}"
    
    # We don't set status, we just leave it as is or intent parser set it to 'planning'
    return {
        "context_bundle": context_bundle,
        "agent_trace": [trace_msg]
    }
