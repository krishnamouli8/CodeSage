"""
IntentParser agent for LangGraph pipeline.
"""
import os
import json
from pydantic import BaseModel, Field
from agents.state import TaskState, TaskSpec

class IntentParserOutput(BaseModel):
    task_type: str = Field(description="bugfix | feature | refactor | unknown")
    target_symbols: list[str] = Field(description="list of symbol names mentioned or implied")
    acceptance_criteria: list[str] = Field(description="list of conditions that define done")
    constraints: list[str] = Field(description="list of explicit constraints, empty list if none")
    confidence: float = Field(description="confidence score between 0.0 and 1.0")

def get_llm(model_name: str):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=model_name, temperature=0)

def intent_parser_node(state: TaskState) -> dict:
    """LangGraph node. Reads state['raw_task'], writes state['task_spec'] and state['status']."""
    raw_task = state.get("raw_task", "")
    
    # Guard: empty task string should fail immediately
    if not raw_task or not raw_task.strip():
        return {
            "status": "failed",
            "task_spec": None,
            "error_message": "IntentParser: raw_task is empty, nothing to parse",
            "agent_trace": ["IntentParser: received empty task, returning failed"]
        }
    
    # Check env vars for models
    # User requested to ensure Gemini is used, so we default to a gemini model if none provided
    primary_model_name = os.environ.get("MODEL_PRIMARY", "gemini-1.5-pro-latest")
    fallback_model_name = os.environ.get("MODEL_FALLBACK", "gemini-1.5-flash-latest")
    
    llms = [primary_model_name, fallback_model_name]
    
    last_error = None
    output_obj = None
    
    for model_name in llms:
        try:
            llm = get_llm(model_name)
            structured_llm = llm.with_structured_output(IntentParserOutput)
            prompt = (
                "You are an Intent Parser for an autonomous coding agent.\n"
                f"Analyze the following task: {raw_task}\n"
                "Extract the task type, target symbols, acceptance criteria, constraints, and your confidence score."
            )
            output_obj = structured_llm.invoke(prompt)
            # If successful, break out of the retry loop
            break
        except Exception as e:
            last_error = e
            continue
            
    if output_obj is None:
        # Both models failed
        return {
            "status": "failed",
            "error_message": f"IntentParser: failed to parse LLM response. Error: {last_error}",
            "agent_trace": [f"IntentParser: failed to parse LLM response. Error: {last_error}"]
        }
        
    if output_obj.confidence < 0.6:
        return {
            "status": "failed",
            "error_message": f"IntentParser: low confidence, clarification needed. Task was: {raw_task}",
            "agent_trace": [f"IntentParser: low confidence ({output_obj.confidence}), failed"]
        }
        
    task_spec = TaskSpec(
        raw_task=raw_task,
        task_type=output_obj.task_type,
        target_symbols=output_obj.target_symbols,
        acceptance_criteria=output_obj.acceptance_criteria,
        constraints=output_obj.constraints,
        confidence=output_obj.confidence
    )
    
    return {
        "task_spec": task_spec,
        "status": "planning",
        "agent_trace": [f"IntentParser: parsed task as {output_obj.task_type}, confidence={output_obj.confidence}, symbols={output_obj.target_symbols}"]
    }
