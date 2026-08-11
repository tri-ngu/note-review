from app.fixture import WATER_CYCLE_QUESTION_SET


def test_fixture_has_at_least_five_questions():
    assert len(WATER_CYCLE_QUESTION_SET.questions) >= 5


def test_fixture_mixes_multiple_choice_and_select_all():
    flags = {q.is_select_all for q in WATER_CYCLE_QUESTION_SET.questions}
    assert flags == {True, False}


def test_fixture_every_question_has_four_options_and_valid_answers():
    for q in WATER_CYCLE_QUESTION_SET.questions:
        assert len(q.options) == 4
        assert 1 <= len(q.correct_answers) <= 4
        assert all(a in (1, 2, 3, 4) for a in q.correct_answers)
