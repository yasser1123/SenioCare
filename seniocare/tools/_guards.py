"""
Per-turn re-entrancy guards for tools.

Every data tool guards against being called twice in the same turn (the
Feature Agent prompt says "call each tool only once", and a second call
would only add latency). The original guards stored ``True`` in session
state and never reset it, so from the second turn of a session onward every
guarded tool short-circuited to ``already_called`` and, for example,
drug-food interaction screening silently stopped running (docs/AUDIT.md
C-04; measured by the ``mt-guard-*`` scenarios in evals/cases/06_multiturn.jsonl).

A ``temp:`` prefix is not a fix: ADK never merges ``temp:`` keys into
``session.state`` (``BaseSessionService._update_session_state``), so such a
flag is invisible to the next tool call inside the *same* turn as well.

The guard instead records the **turn number** it was set in
(``conversation_turn_count``, maintained by ``populate_user_data`` in
seniocare/callbacks.py) and only reports ``already_called`` when that number
equals the current turn. Without a turn counter (unit tests with a bare
state dict, ``adk web`` before the root callback ran) it degrades to the
old boolean behaviour within that state object.
"""

from __future__ import annotations

from typing import Any

TURN_KEY = "conversation_turn_count"

GUARD_KEYS = (
    "_meal_tool_called",
    "_recipe_tool_called",
    "_interaction_tool_called",
    "_symptom_tool_called",
    "_exercise_tool_called",
    "_store_report_tool_called",
)


def already_called_this_turn(state: Any, key: str) -> bool:
    """True if `key` was marked during the current turn."""
    mark = state.get(key)
    if not mark:
        return False
    turn = state.get(TURN_KEY)
    if turn is None:
        return bool(mark)          # legacy semantics: no turn counter available
    return mark == turn


def mark_called(state: Any, key: str) -> None:
    """Record that the guarded tool ran in the current turn."""
    turn = state.get(TURN_KEY)
    state[key] = turn if turn is not None else True


def guard(state: Any, key: str) -> bool:
    """Check-and-mark in one step. Returns True when the caller must short-circuit."""
    if already_called_this_turn(state, key):
        return True
    mark_called(state, key)
    return False
