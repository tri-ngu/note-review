from app.models import Question, QuestionSet, PlayerState
from app.game_logic import compute_points, is_answer_correct, rank_standings, shuffle_questions


def _mc_question(**overrides):
    kwargs = dict(
        concept="c", question_text="q", options=["A", "B", "C", "D"],
        correct_answers=[1], is_select_all=False, explanation="e",
        page_number=1, source_quote="s",
    )
    kwargs.update(overrides)
    return Question(**kwargs)


def test_compute_points_brackets():
    assert compute_points(0.0) == 100
    assert compute_points(4.9) == 100
    assert compute_points(5.0) == 95
    assert compute_points(9.9) == 95
    assert compute_points(10.0) == 90
    assert compute_points(14.9) == 90
    assert compute_points(15.0) == 85
    assert compute_points(19.9) == 85
    assert compute_points(20.0) == 80
    assert compute_points(24.9) == 80
    assert compute_points(25.0) == 75
    assert compute_points(29.9) == 75
    assert compute_points(30.0) == 75


def test_compute_points_clamps_out_of_range():
    assert compute_points(-1.0) == 100
    assert compute_points(999.0) == 75


def test_is_answer_correct_multiple_choice():
    q = _mc_question(correct_answers=[2], is_select_all=False)
    assert is_answer_correct(q, [2]) is True
    assert is_answer_correct(q, [1]) is False


def test_is_answer_correct_select_all_exact_match_required():
    q = _mc_question(correct_answers=[1, 3], is_select_all=True)
    assert is_answer_correct(q, [1, 3]) is True
    assert is_answer_correct(q, [3, 1]) is True  # order-independent
    assert is_answer_correct(q, [1]) is False  # subset, no partial credit
    assert is_answer_correct(q, [1, 2, 3]) is False  # superset, no partial credit


def test_rank_standings_orders_by_score_descending():
    players = {
        "p1": PlayerState(player_id="p1", nickname="A", score=100),
        "p2": PlayerState(player_id="p2", nickname="B", score=300),
        "p3": PlayerState(player_id="p3", nickname="C", score=200),
    }
    standings = rank_standings(players)
    assert [s["player_id"] for s in standings] == ["p2", "p3", "p1"]
    assert [s["rank"] for s in standings] == [1, 2, 3]


def test_rank_standings_ties_share_rank_and_skip_next():
    players = {
        "p1": PlayerState(player_id="p1", nickname="A", score=200),
        "p2": PlayerState(player_id="p2", nickname="B", score=200),
        "p3": PlayerState(player_id="p3", nickname="C", score=100),
    }
    standings = rank_standings(players)
    by_id = {s["player_id"]: s for s in standings}
    assert by_id["p1"]["rank"] == 1
    assert by_id["p2"]["rank"] == 1
    assert by_id["p3"]["rank"] == 3  # skips rank 2


def test_shuffle_questions_returns_new_object_same_content_different_or_equal_order():
    original = QuestionSet(questions=[_mc_question(question_text=f"q{i}") for i in range(20)])
    shuffled = shuffle_questions(original)
    assert shuffled is not original
    assert len(shuffled.questions) == len(original.questions)
    assert {q.question_text for q in shuffled.questions} == {q.question_text for q in original.questions}
    # original must be untouched
    assert [q.question_text for q in original.questions] == [f"q{i}" for i in range(20)]
