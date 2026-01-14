"""
================================================================================
                            SENIOCARE ROOT AGENT
                  Sequential Pipeline with Self-Correction Loop
                     Specialized for Elderly Healthcare
================================================================================

Architecture Overview:
━━━━━━━━━━━━━━━━━━━━━━

This is the main orchestrator for the SenioCare elderly healthcare assistant.
It implements a sequential pipeline with an embedded improvement loop to ensure
high-quality, safe, and personalized health recommendations for elderly users.

Pipeline Flow:
─────────────
    ┌─────────────────┐
    │  User Message   │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │  Intent Agent   │ ─── Step 1: Classify user intent
    └────────┬────────┘     (meal, medication, exercise, medical_qa, emergency, emotional, routine)
             │
             ▼
    ┌─────────────────┐
    │  Safety Agent   │ ─── Step 2: Verify request safety
    └────────┬────────┘     (ALLOWED, BLOCKED, EMERGENCY)
             │
             ▼
    ┌─────────────────┐
    │  Data Fetcher   │ ─── Step 3: Retrieve user profile
    └────────┬────────┘     (conditions, medications, allergies, etc.)
             │
             ▼
    ╔═════════════════╗
    ║ Improvement     ║
    ║     Loop        ║ ─── Step 4: Generate & validate recommendation
    ║  ┌───────────┐  ║
    ║  │ Feature   │──╫──► Generate personalized recommendation
    ║  │  Agent    │  ║
    ║  └─────┬─────┘  ║
    ║        │        ║
    ║        ▼        ║
    ║  ┌───────────┐  ║
    ║  │  Judge    │──╫──► Validate quality & safety
    ║  │  Agent    │  ║    - If approved: exit loop
    ║  └─────┬─────┘  ║    - If rejected: loop with feedback
    ║        │        ║
    ║   (max 3 iters) ║
    ╚════════╪════════╝
             │
             ▼
    ┌─────────────────┐
    │ Formatter Agent │ ─── Step 5: Format in Egyptian Arabic
    └────────┬────────┘     (warm, respectful, elderly-friendly)
             │
             ▼
    ┌─────────────────┐
    │ Final Response  │
    └─────────────────┘

Agent Responsibilities:
━━━━━━━━━━━━━━━━━━━━━━
1. Intent Agent      → Classifies user's request into predefined categories
2. Safety Agent      → Screens for emergencies and blocks unsafe requests  
3. Data Fetcher      → Retrieves personalized user health profile
4. Feature Agent     → Generates health recommendations using tools
5. Judge Agent       → Validates recommendation quality and safety
6. Formatter Agent   → Converts to warm Egyptian Arabic for delivery

Key Features:
━━━━━━━━━━━━━
• Self-correction loop ensures high-quality recommendations
• Maximum 3 iterations prevents infinite loops
• Safety-first approach with emergency detection
• Personalized recommendations based on user health profile
• Warm, respectful Egyptian Arabic output for elderly users

================================================================================
"""

from google.adk.agents import SequentialAgent, LoopAgent, LlmAgent
from google.adk.models.lite_llm import LiteLlm

# Import sub-agents
from seniocare.sub_agents.intent_agent import intent_agent
from seniocare.sub_agents.safety_agent import safety_agent
from seniocare.sub_agents.data_fetcher_agent import data_fetcher_agent
from seniocare.sub_agents.feature_agent import feature_agent
from seniocare.sub_agents.judge_agent import judge_agent
from seniocare.sub_agents.formatter_agent import formatter_agent


# =============================================================================
# IMPROVEMENT LOOP
# =============================================================================
# This loop implements the self-correction mechanism:
# - Feature Agent generates a recommendation
# - Judge Agent validates it
# - If approved: loop exits, recommendation proceeds to formatter
# - If rejected: loop continues with judge's feedback for improvement
# - Maximum 3 iterations to prevent infinite loops

improvement_loop = LoopAgent(
    name="improvement_loop",
    description="Recommendation improvement loop - iterates until judge approves or max iterations reached",
    sub_agents=[feature_agent, judge_agent],
    max_iterations=3,  # Safety limit to prevent infinite loops
)


# =============================================================================
# MAIN PIPELINE (ROOT AGENT)
# =============================================================================
# Sequential execution ensures each step has access to outputs from previous steps:
# 1. Intent Agent → outputs intent_result
# 2. Safety Agent → outputs safety_status (uses intent_result)
# 3. Data Fetcher → outputs user_context
# 4. Improvement Loop → outputs raw_recommendation (uses all above)
# 5. Formatter Agent → outputs final_response (uses raw_recommendation)

root_agent = SequentialAgent(
    name="seniocare",
    description="SenioCare Elderly Healthcare Assistant - Sequential pipeline with self-correction for safe, personalized health recommendations",
    sub_agents=[
        intent_agent,       # Step 1: Classify user intent
        safety_agent,       # Step 2: Verify safety
        data_fetcher_agent, # Step 3: Retrieve user profile
        improvement_loop,   # Step 4: Generate & validate recommendation
        formatter_agent,    # Step 5: Format final response
    ],
)