"""
SenioCare Root Agent
====================
Defines the 3-agent sequential pipeline.
Callbacks are in seniocare/callbacks.py.
Database is initialized here on import.

Pipeline:
  User Prompt
    → orchestrator_agent  (safety + intent + task plan)
    → feature_agent       (tool calls + decision)
    → formatter_agent     (Egyptian Arabic output)
"""

from google.adk.agents import SequentialAgent

from seniocare.sub_agents.orchestrator_agent import orchestrator_agent
from seniocare.sub_agents.feature_agent import feature_agent
from seniocare.sub_agents.formatter_agent import formatter_agent
from seniocare.callbacks import populate_user_data, auto_save_to_memory
from seniocare.data.database import _initialize_database as _init_db

# Initialize cloud DB tables on startup (idempotent)
_init_db()

# =============================================================================
# ROOT AGENT
# =============================================================================

root_agent = SequentialAgent(
    name="seniocare",
    description="SenioCare Elderly Healthcare Assistant — 3-agent sequential pipeline for safe, personalized health recommendations",
    before_agent_callback=populate_user_data,
    after_agent_callback=auto_save_to_memory,
    sub_agents=[
        orchestrator_agent,  # Step 1: Safety + Intent + Tool-Aware Planning
        feature_agent,       # Step 2: Tool Calling + Decision + Presentation Prep
        formatter_agent,     # Step 3: Format final response in Egyptian Arabic
    ],
)