"""Long-term memory tool: facts go to user:-scoped state, de-duplicated and capped. No DB."""

from seniocare.profile import KEY_MEMORY_FACTS, render_profile_block
from seniocare.tools.memory import MAX_FACTS, remember_fact


class Ctx:
    def __init__(self, state=None):
        self.state = state if state is not None else {}


def test_fact_is_stored_with_category_and_date():
    ctx = Ctx()
    out = remember_fact("بنتي منى بتزورني كل جمعة", "family", ctx)
    assert out["status"] == "success"
    (fact,) = ctx.state[KEY_MEMORY_FACTS]
    assert fact["fact"] == "بنتي منى بتزورني كل جمعة" and fact["category"] == "family" and len(fact["date"]) == 10


def test_duplicates_are_ignored_and_unknown_category_is_other():
    ctx = Ctx()
    remember_fact("بحب أم كلثوم", "music", ctx)
    remember_fact("  بحب   ام كلثوم ", "likes", ctx)
    assert len(ctx.state[KEY_MEMORY_FACTS]) == 1
    assert ctx.state[KEY_MEMORY_FACTS][0]["category"] == "other"


def test_memory_is_capped_keeping_the_newest():
    ctx = Ctx()
    for i in range(MAX_FACTS + 3):
        remember_fact(f"fact {i}", "other", ctx)
    facts = ctx.state[KEY_MEMORY_FACTS]
    assert len(facts) == MAX_FACTS and facts[-1]["fact"] == f"fact {MAX_FACTS + 2}"


def test_empty_fact_is_rejected():
    assert remember_fact("   ", "family", Ctx())["status"] == "error"


def test_remembered_facts_reach_the_prompt_block():
    ctx = Ctx({"user:user_id": "u"})
    remember_fact("عملت عملية في ركبتي سنة 2020", "health_history", ctx)
    assert "عملت عملية في ركبتي سنة 2020" in render_profile_block(ctx.state)
