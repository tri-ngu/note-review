import pytest
from pydantic import ValidationError

from app.models import Answer, PlayerState, Question, QuestionSet, RoomState


def _valid_question_kwargs(**overrides):
    kwargs = dict(
        concept="Evaporation",
        question_text="What drives evaporation?",
        options=["The sun", "Wind", "Salinity", "Pressure"],
        correct_answers=[1],
        is_select_all=False,
        explanation="The sun's heat drives evaporation.",
        page_number=1,
        source_quote="The sun's heat drives evaporation.",
    )
    kwargs.update(overrides)
    return kwargs


def test_question_requires_exactly_four_options():
    with pytest.raises(ValidationError):
        Question(**_valid_question_kwargs(options=["A", "B", "C"]))


def test_question_correct_answers_must_be_one_to_four_entries():
    with pytest.raises(ValidationError):
        Question(**_valid_question_kwargs(correct_answers=[]))
    with pytest.raises(ValidationError):
        Question(**_valid_question_kwargs(correct_answers=[1, 2, 3, 4, 1]))


def test_question_correct_answers_values_must_be_one_to_four():
    with pytest.raises(ValidationError):
        Question(**_valid_question_kwargs(correct_answers=[5]))


def test_question_correct_answers_rejects_duplicates():
    with pytest.raises(ValidationError):
        Question(**_valid_question_kwargs(correct_answers=[1, 1], is_select_all=True))


def test_question_accepts_valid_data():
    q = Question(**_valid_question_kwargs())
    assert q.is_select_all is False


def test_multiple_choice_must_have_exactly_one_correct_answer():
    with pytest.raises(ValidationError):
        Question(**_valid_question_kwargs(is_select_all=False, correct_answers=[1, 2]))


def test_select_all_may_have_a_single_correct_answer():
    # a Select-All question can legitimately have only one correct option
    # (CONTEXT.md: distinguished by is_select_all, not by len(correct_answers))
    q = Question(**_valid_question_kwargs(is_select_all=True, correct_answers=[1]))
    assert q.is_select_all is True
    assert q.correct_answers == [1]


def test_select_all_may_have_all_four_correct_answers():
    q = Question(**_valid_question_kwargs(is_select_all=True, correct_answers=[1, 2, 3, 4]))
    assert len(q.correct_answers) == 4


def test_question_set_holds_a_list_of_questions():
    qs = QuestionSet(questions=[Question(**_valid_question_kwargs())])
    assert len(qs.questions) == 1


def test_player_state_defaults():
    p = PlayerState(player_id="p1", nickname="Alice")
    assert p.score == 0
    assert p.connected is True


def test_answer_model():
    a = Answer(player_id="p1", selected=[1], elapsed=2.5, correct=True, points=100)
    assert a.points == 100


def test_room_state_defaults_and_required_fields():
    qs = QuestionSet(questions=[Question(**_valid_question_kwargs())])
    room = RoomState(pin="0042", host_session_id="s1", question_set=qs, created_at=100.0)
    assert room.status == "lobby"
    assert room.current_round == 0
    assert room.players == {}
    assert room.answers == {}
    assert room.terminal_reason is None


def test_room_state_rejects_invalid_status():
    qs = QuestionSet(questions=[Question(**_valid_question_kwargs())])
    with pytest.raises(ValidationError):
        RoomState(pin="0042", host_session_id="s1", question_set=qs, created_at=100.0, status="not_a_real_status")
