"""Data Fetcher Agent - Custom agent that fetches user data without LLM.

This is a non-LLM agent that automatically retrieves user profile data from the
database and stores it in the session state for subsequent agents to access.
It initializes the pipeline context with user-specific information.
"""

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai.types import Content, Part
from typing import AsyncIterator

from seniocare.tools.user_data import get_user_profile


class DataFetcherAgent(BaseAgent):
    """
    A non-LLM agent that automatically fetches user data and stores in state.
    
    ================================================================================
                              DATA FETCHER AGENT
                     SenioCare Elderly Healthcare Assistant
    ================================================================================
    
    PURPOSE:
    This agent serves as the data retrieval layer of the SenioCare pipeline.
    It fetches comprehensive user profile information before recommendations
    are generated, ensuring all subsequent agents have access to personalized
    user context.
    
    RESPONSIBILITIES:
    • Retrieve user profile from the data store
    • Store user context in session state for downstream agents
    • Initialize judge critique state for the improvement loop
    • Generate confirmation event for pipeline logging
    
    DATA RETRIEVED:
    • User demographics (name, age, gender)
    • Medical conditions and diagnoses
    • Current medications and schedules
    • Allergies and dietary restrictions
    • Physical limitations and mobility status
    • Health metrics (blood pressure, blood sugar, etc.)
    • Emergency contacts and preferences
    
    OUTPUT:
    • Stores 'user_context' in session state
    • Stores 'judge_critique' initialization in session state
    • Yields confirmation event with user name
    
    ================================================================================
    """
    
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncIterator[Event]:
        """
        Fetch user profile and store in session state.
        
        This method:
        1. Retrieves the user profile using the user_id
        2. Stores the complete profile as 'user_context' in session state
        3. Initializes 'judge_critique' for the improvement loop
        4. Yields a confirmation event
        
        Args:
            ctx: The invocation context containing session state
            
        Yields:
            Event: Confirmation event with user data retrieval status
        """
        # Default user ID - in production, this would be retrieved from session/auth
        user_id = "user_001"
        
        # Call the tool directly (no LLM needed for data fetching)
        user_data = get_user_profile(user_id)
        
        # Store comprehensive user context in state for other agents to access
        # This includes profile, conditions, medications, allergies, etc.
        ctx.session.state["user_context"] = str(user_data)
        
        # Initialize judge_critique for the first iteration of the improvement loop
        # This prevents KeyError in feature_agent which expects this key to exist
        ctx.session.state["judge_critique"] = "No previous feedback (first attempt)."
        
        # Extract user name for confirmation message
        user_name = user_data.get('profile', {}).get('name', 'User')
        
        # Create detailed confirmation message
        message = f"User data successfully retrieved for: {user_name}"
        
        # Create proper Content object for the Event
        content = Content(
            role="model",
            parts=[Part(text=message)]
        )
        
        yield Event(
            author=self.name,
            content=content
        )


# Create the agent instance
data_fetcher_agent = DataFetcherAgent(
    name="data_fetcher_agent",
    description="Automatically retrieves user profile data and stores in session state for personalized recommendations",
)
