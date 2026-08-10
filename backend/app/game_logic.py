import random

from app.models import PlayerState, Question, QuestionSet


def compute_points(elapsed: float) -> int:
    clamped = max(0.0, min(elapsed, 30.0))
    bracket = min(int(clamped // 5), 5)
    return 100 - bracket * 5


def is_answer_correct(question: Question, selected: list[int]) -> bool:
    return set(selected) == set(question.correct_answers)


def rank_standings(players: dict[str, PlayerState]) -> list[dict]:
    ordered = sorted(players.values(), key=lambda p: p.score, reverse=True)
    standings: list[dict] = []
    rank = 0
    previous_score: int | None = None
    for position, player in enumerate(ordered, start=1):
        if player.score != previous_score:
            rank = position
            previous_score = player.score
        standings.append(
            {
                "player_id": player.player_id,
                "nickname": player.nickname,
                "score": player.score,
                "rank": rank,
            }
        )
    return standings


def shuffle_questions(question_set: QuestionSet) -> QuestionSet:
    shuffled = list(question_set.questions)
    random.shuffle(shuffled)
    return QuestionSet(questions=shuffled)
