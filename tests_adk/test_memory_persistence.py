"""user:-scoped state (profile, preferences, memory facts) carries over to a NEW session.

Uses ADK's DatabaseSessionService on a temporary SQLite file: the same class the
app uses on Neon PostgreSQL.
"""

import pytest
from google.adk.sessions import DatabaseSessionService

from seniocare.profile import KEY_MEMORY_FACTS


@pytest.mark.asyncio
async def test_facts_written_in_one_session_are_visible_in_the_next(tmp_path):
    svc = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    facts = [{"fact": "بنتي منى بتزورني كل جمعة", "category": "family", "date": "2026-09-25"}]
    await svc.create_session(app_name="a", user_id="u1", session_id="monday", state={KEY_MEMORY_FACTS: facts})
    later = await svc.create_session(app_name="a", user_id="u1", session_id="friday")
    assert later.state[KEY_MEMORY_FACTS] == facts
    other = await svc.create_session(app_name="a", user_id="u2", session_id="x")
    assert KEY_MEMORY_FACTS not in other.state
