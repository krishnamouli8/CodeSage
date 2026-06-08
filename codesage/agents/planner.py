import os
import json
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from agents.state import TaskState, PlanState, EditSpec
from tools.graph_tools import symbol_graph

class PlannerEdit(BaseModel):
    file_path: str = Field(description="Path to the file to edit")
    node_path: str = Field(description="Dotted path of the AST node to modify")
    operation: str = Field(description="replace | insert_after | delete")
    rationale: str = Field(description="Why this edit is needed")

class PlannerOutput(BaseModel):
    edits: List[PlannerEdit] = Field(description="List of edits to make")
    risk_level: str = Field(description="low | medium | high")

def get_llm(model_name: str):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=model_name, temperature=0)

def planner_node(state: TaskState) -> dict:
    """LangGraph node. Reads task_spec + context_bundle, writes plan_state."""
    task_spec = state.get("task_spec")
    context_bundle = state.get("context_bundle")
    
    if not task_spec:
        return {"status": "failed", "error_message": "Planner: missing task_spec", "agent_trace": ["Planner: failed, missing task_spec"]}
    if not context_bundle:
        return {"status": "failed", "error_message": "Planner: missing context_bundle", "agent_trace": ["Planner: failed, missing context_bundle"]}
        
    system_prompt = (
        "You are a software engineering planner for an autonomous coding agent.\n"
        "Your task is to analyze the user's request and the provided code context, "
        "and produce a precise plan of AST-level edits.\n"
        "You must return ONLY JSON matching the requested schema. Do not include markdown formatting or explanation."
    )
    
    ac_list = "\n".join(f"{i+1}. {ac}" for i, ac in enumerate(task_spec.acceptance_criteria))
    
    chunks_text = []
    for chunk in context_bundle.chunks:
        chunks_text.append(f"### {chunk.node_path}\n```python\n{chunk.source_text}\n```")
    chunks_str = "\n\n".join(chunks_text)
    
    prompt = (
        f"{system_prompt}\n\n"
        f"USER TASK:\n{task_spec.raw_task}\n\n"
        f"ACCEPTANCE CRITERIA:\n{ac_list}\n\n"
        f"CODE CONTEXT (Top {len(context_bundle.chunks)} chunks):\n{chunks_str}\n\n"
        "INSTRUCTION: Produce an edit plan as JSON matching the following schema:\n"
        "{\n"
        '  "edits": [\n'
        "    {\n"
        '      "file_path": "...",\n'
        '      "node_path": "...",\n'
        '      "operation": "replace | insert_after | delete",\n'
        '      "rationale": "..."\n'
        "    }\n"
        "  ],\n"
        '  "risk_level": "low | medium | high"\n'
        "}\n"
        "Return ONLY the valid JSON object, no markdown fences."
    )
    
    primary_model_name = os.environ.get("MODEL_PRIMARY", "gemini-1.5-pro-latest")
    fallback_model_name = os.environ.get("MODEL_FALLBACK", "gemini-1.5-flash-latest")
    
    llms = [primary_model_name, fallback_model_name]
    output_obj = None
    last_error = None
    
    for model_name in llms:
        try:
            llm = get_llm(model_name)
            structured_llm = llm.with_structured_output(PlannerOutput)
            output_obj = structured_llm.invoke(prompt)
            break
        except Exception as e:
            last_error = e
            continue
            
    if output_obj is None:
        return {
            "status": "failed",
            "error_message": f"Planner: LLM failed to produce valid plan. Error: {last_error}",
            "agent_trace": [f"Planner: LLM failed to produce valid plan. Error: {last_error}"]
        }
        
    trace_msgs = []
    validated_edits = []
    seen_node_paths = set()
    
    for edit in output_obj.edits:
        # Validate node_path uniqueness
        if edit.node_path in seen_node_paths:
            trace_msgs.append(f"Planner [Warning]: dropped duplicate edit for {edit.node_path}")
            continue
            
        # Validate file existence
        if not os.path.exists(edit.file_path):
            trace_msgs.append(f"Planner [Warning]: dropped edit for non-existent file {edit.file_path}")
            continue
            
        seen_node_paths.add(edit.node_path)
        validated_edits.append(edit)
        
    if not validated_edits:
        return {
            "status": "failed",
            "error_message": "Planner: plan contained 0 valid edits after deduplication and existence checks",
            "agent_trace": trace_msgs
        }
        
    risk_level = output_obj.risk_level.lower()
    
    # Check callers via symbol_graph
    try:
        for edit in validated_edits:
            # symbol_graph is a synchronous langchain tool, invoke directly
            sg_result = symbol_graph.invoke({"symbol_name": edit.node_path.split('.')[-1], "depth": 1})
            # tool returns dict: {"symbol": ..., "callers": [...], "callees": [...]}
            callers = sg_result.get("callers", [])
            if len(callers) > 5:
                risk_level = "high"
                break
    except Exception as e:
        trace_msgs.append(f"Planner [Warning]: symbol_graph check failed: {e}")
        
    if risk_level == "high" and len(validated_edits) > 10:
        return {
            "status": "failed",
            "error_message": "Planner: high-risk plan with >10 edits requires human confirmation",
            "agent_trace": ["Planner: failed, high-risk plan with >10 edits requires human confirmation"]
        }
        
    final_edits = []
    for edit in validated_edits:
        final_edits.append(
            EditSpec(
                file_path=edit.file_path,
                node_path=edit.node_path,
                operation=edit.operation,
                rationale=edit.rationale,
                generated_source="",
                applied=False,
                diff=""
            )
        )
        
    plan_state = PlanState(
        edits=final_edits,
        risk_level=risk_level,
        edit_count=len(final_edits)
    )
    
    trace_msgs.append(f"Planner: produced {plan_state.edit_count} edits, risk={risk_level}")
    
    return {
        "plan_state": plan_state,
        "status": "coding",
        "agent_trace": trace_msgs
    }
