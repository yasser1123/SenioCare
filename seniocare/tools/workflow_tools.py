"""Workflow Tools - Tools for controlling workflow execution."""

from google.adk.tools import ToolContext


def approve_response(tool_context: ToolContext) -> dict:
    """Call this tool when the recommendation is approved and ready for formatting.
    
    This tool signals the LoopAgent to exit and proceed to the formatter.
    Only call this when the recommendation passes all validation checks.
    
    Args:
        tool_context: The tool context for accessing actions.
        
    Returns:
        A confirmation message.
    """
    # Signal escalation to exit the LoopAgent
    tool_context.actions.escalate = True
    return {"status": "approved", "message": "التوصية تمت الموافقة عليها - جاري التنسيق النهائي"}


def reject_response(critique: str, tool_context: ToolContext) -> dict:
    """Call this tool when the recommendation needs improvement.
    
    This tool stores the critique for the feature agent to use in regeneration.
    The loop will continue and the feature agent will try again.
    
    Args:
        critique: The feedback explaining what needs to be fixed.
        tool_context: The tool context for state access.
        
    Returns:
        A message indicating the loop will continue.
    """
    # Store critique in state for feature agent to read
    tool_context.state["judge_critique"] = critique
    
    # Reset feature agent tool flags for the next iteration
    # This allows the feature agent to call tools again in the next loop iteration
    tool_context.state["_meal_tool_called"] = False
    tool_context.state["_medication_tool_called"] = False
    tool_context.state["_exercise_tool_called"] = False
    tool_context.state["_search_tool_called"] = False
    tool_context.state["_log_medication_tool_called"] = False
    
    return {"status": "rejected", "message": f"مطلوب تحسين: {critique}"}
