"""
SenioCare Root Agent
====================
Defines the 3-agent sequential pipeline.
Callbacks are in seniocare/callbacks.py.
Database is initialized here on import.

Pipeline (seniocare/pipeline.py):
  User Prompt
    → orchestrator_agent  (safety + intent + task plan)
    → route()             (code, not prose: BLOCKED/EMERGENCY skip stage 2)
    → feature_agent       (tool calls + decision)   [ALLOWED only]
    → formatter_agent     (Egyptian Arabic output)
"""

from seniocare.pipeline import SenioCarePipeline

from seniocare.sub_agents.orchestrator_agent import orchestrator_agent
from seniocare.sub_agents.feature_agent import feature_agent
from seniocare.sub_agents.formatter_agent import formatter_agent
from seniocare.callbacks import populate_user_data, auto_save_to_memory
from seniocare.data.database import _initialize_database as _init_db

# Initialize cloud DB tables on startup (idempotent).
# Guarded so importing this module (tests, CI, adk web without a configured
# DB) never crashes — the first actual DB query raises a clear error instead.
try:
    _init_db()
except Exception as e:
    print(f"[SenioCare] Database initialization deferred: {e}")

# =============================================================================
# ROOT AGENT
# =============================================================================

root_agent = SenioCarePipeline(
    name="seniocare",
    description="SenioCare Elderly Healthcare Assistant — safety-routed 3-stage pipeline for safe, personalized health recommendations",
    before_agent_callback=populate_user_data,
    after_agent_callback=auto_save_to_memory,
    orchestrator=orchestrator_agent,  # Step 1: Safety + Intent + Tool-Aware Planning
    feature=feature_agent,            # Step 2: Tool Calling + Decision (skipped when BLOCKED/EMERGENCY)
    formatter=formatter_agent,        # Step 3: Format final response in Egyptian Arabic
)