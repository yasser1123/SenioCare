"""AUDIT C-04: tool re-entrancy guards must reset every turn. No DB, no model."""

from seniocare.tools._guards import GUARD_KEYS, already_called_this_turn, guard, mark_called


def test_second_call_in_same_turn_is_blocked():
    state = {"conversation_turn_count": 1}
    assert guard(state, "_meal_tool_called") is False   # first call runs
    assert guard(state, "_meal_tool_called") is True    # second call short-circuits
    assert state["_meal_tool_called"] == 1


def test_next_turn_runs_again():
    state = {"conversation_turn_count": 1}
    guard(state, "_interaction_tool_called")
    state["conversation_turn_count"] = 2                 # populate_user_data increments per turn
    assert already_called_this_turn(state, "_interaction_tool_called") is False
    assert guard(state, "_interaction_tool_called") is False
    assert state["_interaction_tool_called"] == 2


def test_legacy_boolean_semantics_without_turn_counter():
    state = {}
    assert guard(state, "_symptom_tool_called") is False
    assert state["_symptom_tool_called"] is True
    assert guard(state, "_symptom_tool_called") is True


def test_stale_true_from_old_sessions_does_not_block_a_numbered_turn():
    # A session persisted by the old code holds True; the new code must not
    # treat it as "called in turn 3".
    state = {"conversation_turn_count": 3, "_meal_tool_called": True}
    assert already_called_this_turn(state, "_meal_tool_called") is False


def test_mark_and_keys():
    state = {"conversation_turn_count": 7}
    for key in GUARD_KEYS:
        mark_called(state, key)
        assert state[key] == 7
