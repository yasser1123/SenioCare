"""AUDIT C-05: preference conflict handling. No DB."""

from seniocare.tools.preferences import OPPOSITE_KEY, save_user_preference


class Ctx:
    def __init__(self, state=None):
        self.state = state if state is not None else {}


def test_like_then_dislike_removes_the_like():
    ctx = Ctx()
    save_user_preference("food", ["الكشري"], True, ctx)
    assert "كشري" in ctx.state["user:preferences"]["food_likes"][0]
    save_user_preference("food", ["الكشري"], False, ctx)
    prefs = ctx.state["user:preferences"]
    assert any("كشري" in x for x in prefs["food_dislikes"])
    assert not any("كشري" in x for x in prefs["food_likes"])   # was left in place before the fix


def test_dislike_then_like_removes_the_dislike():
    ctx = Ctx()
    save_user_preference("exercise", ["Swimming"], False, ctx)
    save_user_preference("exercise", ["swimming"], True, ctx)
    prefs = ctx.state["user:preferences"]
    assert prefs["exercise_likes"] == ["swimming"] and prefs["exercise_dislikes"] == []


def test_opposite_map_is_complete_and_symmetric():
    for k, v in OPPOSITE_KEY.items():
        assert OPPOSITE_KEY[v] == k
    assert set(OPPOSITE_KEY) == {"food_likes", "food_dislikes", "exercise_likes", "exercise_dislikes", "general_likes", "general_dislikes"}


def test_dedupe_and_order_preserved():
    ctx = Ctx({"user:preferences": {"food_likes": ["fish"], "food_dislikes": []}})
    r = save_user_preference("food", ["Fish", "meat", "meat", " "], True, ctx)
    assert ctx.state["user:preferences"]["food_likes"] == ["fish", "meat"]
    assert r["items"] == ["fish", "meat"] and r["status"] == "success"


def test_general_type_and_arabic_normalisation():
    ctx = Ctx()
    save_user_preference("general", ["القراءة"], True, ctx)
    save_user_preference("general", ["القراءه"], False, ctx)   # taa-marbuta/haa variant of the same word
    prefs = ctx.state["user:preferences"]
    assert prefs["general_likes"] == [] and len(prefs["general_dislikes"]) == 1
