import os
import re
from typing import Dict, Any

from agents.state import TaskState, EditSpec
from tools.ast_tools import get_ast_node, get_file_content, apply_ast_patch

def get_llm(model_name: str):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=model_name, temperature=0)

def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences if the model accidentally included them."""
    text = text.strip()
    if text.startswith("```"):
        # Find the first newline after ```
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline+1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()

def coder_node(state: TaskState) -> dict:
    """LangGraph node. Iterates plan_state.edits, generates + applies patches."""
    plan_state = state.get("plan_state")
    if not plan_state:
        return {"status": "failed", "error_message": "Coder: missing plan_state", "agent_trace": ["Coder: failed, missing plan_state"]}

    trace_msgs = []
    
    primary_model_name = os.environ.get("MODEL_PRIMARY", "gemini-1.5-pro-latest")
    fallback_model_name = os.environ.get("MODEL_FALLBACK", "gemini-1.5-flash-latest")
    
    # Pre-fetch LLM, handling errors
    llm = None
    last_error = None
    for model_name in [primary_model_name, fallback_model_name]:
        try:
            llm = get_llm(model_name)
            # Test invocation just to ensure it's initialized correctly
            break
        except Exception as e:
            last_error = e
            continue
            
    if not llm:
        return {
            "status": "failed",
            "error_message": f"Coder: failed to initialize LLM. Error: {last_error}",
            "agent_trace": [f"Coder: failed to initialize LLM. Error: {last_error}"]
        }

    correction_hints = state.get("correction_hints", [])
    
    for edit in plan_state.edits:
        if edit.applied:
            continue
            
        try:
            # 1. Fetch current source
            ast_node_res = get_ast_node.invoke({"file_path": edit.file_path, "node_path": edit.node_path})
            if not ast_node_res.get("found", False):
                trace_msgs.append(f"Coder: failed to apply patch for {edit.node_path} — node not found")
                continue
                
            node_source = ast_node_res.get("source_text", "")
            line_start = ast_node_res.get("line_start", 1)
            line_end = ast_node_res.get("line_end", line_start)
            
            # 2. Fetch context
            ctx_start = max(1, line_start - 20)
            ctx_end = line_end + 20
            ctx_res = get_file_content.invoke({
                "file_path": edit.file_path, 
                "start_line": ctx_start, 
                "end_line": ctx_end
            })
            context_source = ctx_res.get("content", "")
            
            # 3. Look for correction hint
            hint = next((h for h in correction_hints if h.affected_node_path == edit.node_path), None)
            
            # 4. LLM Prompt
            system_prompt = (
                "You are an expert code generator. "
                "You must return ONLY the raw replacement source code for the specified node. "
                "Do NOT provide any explanation, prose, or markdown formatting fences like ```python. "
                "Just output the exact replacement code."
            )
            
            user_prompt = (
                f"CURRENT NODE SOURCE ({edit.node_path}):\n{node_source}\n\n"
                f"FILE CONTEXT ({edit.file_path}, lines {ctx_start}-{ctx_end}):\n{context_source}\n\n"
                f"RATIONALE FOR EDIT:\n{edit.rationale}\n\n"
            )
            
            if hint:
                user_prompt += (
                    f"CORRECTION HINT:\n"
                    f"Error Message: {hint.error_message}\n"
                    f"Suggested Fix: {hint.suggested_fix}\n\n"
                )
                
            user_prompt += "Generate the new replacement source code now:"
            
            # Generate replacement
            ai_msg = llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ])
            
            generated_source = strip_markdown_fences(ai_msg.content)
            
            # 5. Apply Patch
            patch_res = apply_ast_patch.invoke({
                "file_path": edit.file_path,
                "node_path": edit.node_path,
                "new_source": generated_source
            })
            
            # 6. Check results
            if not patch_res.get("success", False):
                err = patch_res.get("error", "unknown error")
                detail = patch_res.get("detail", "")
                trace_msgs.append(f"Coder: failed to apply patch for {edit.node_path} — {err}: {detail}")
            else:
                edit.generated_source = generated_source
                edit.applied = True
                edit.diff = patch_res.get("diff", "")
                trace_msgs.append(f"Coder: applied patch for {edit.node_path}")
                
        except Exception as e:
            trace_msgs.append(f"Coder: failed to process edit for {edit.node_path} — exception: {str(e)}")
            continue
            
    # 8. Collect NEWLY completed edits only (operator.add reducer handles accumulation)
    existing_ids = {id(e) for e in state.get("completed_edits", [])}
    new_edits = [e for e in plan_state.edits if e.applied and id(e) not in existing_ids]
            
    return {
        "plan_state": plan_state,
        "completed_edits": new_edits,
        "status": "testing",
        "agent_trace": trace_msgs
    }

