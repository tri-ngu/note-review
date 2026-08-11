from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Question(BaseModel):
    concept: str
    question_text: str
    options: list[str]
    correct_answers: list[int]
    is_select_all: bool
    explanation: str
    page_number: int
    source_quote: str

    @field_validator("options")
    @classmethod
    def exactly_four_options(cls, v: list[str]) -> list[str]:
        if len(v) != 4:
            raise ValueError("options must have exactly 4 entries")
        return v

    @field_validator("correct_answers")
    @classmethod
    def one_to_four_valid_correct_answers(cls, v: list[int]) -> list[int]:
        if not (1 <= len(v) <= 4):
            raise ValueError("correct_answers must have 1-4 entries")
        if len(set(v)) != len(v):
            raise ValueError("correct_answers must not contain duplicates")
        if any(a not in (1, 2, 3, 4) for a in v):
            raise ValueError("correct_answers values must each be in {1,2,3,4}")
        return v

    @model_validator(mode="after")
    def multiple_choice_has_exactly_one_correct_answer(self) -> "Question":
        # CONTEXT.md: "Multiple-Choice Question: a Question with exactly one correct option"
        if not self.is_select_all and len(self.correct_answers) != 1:
            raise ValueError("Multiple-Choice questions (is_select_all=False) must have exactly 1 correct answer")
        return self


class QuestionSet(BaseModel):
    questions: list[Question]


class PlayerState(BaseModel):
    player_id: str
    nickname: str
    score: int = 0
    connected: bool = True


class Answer(BaseModel):
    player_id: str
    selected: list[int]
    elapsed: float
    correct: bool
    points: int


class RoomState(BaseModel):
    pin: str
    host_session_id: str
    question_set: QuestionSet
    status: Literal["lobby", "question_active", "answer_reveal", "leaderboard", "finished"] = "lobby"
    current_round: int = 0
    question_start_time: float | None = None
    players: dict[str, PlayerState] = Field(default_factory=dict)
    answers: dict[str, Answer] = Field(default_factory=dict)
    terminal_reason: Literal["natural_end", "host_ended", "host_disconnected"] | None = None
    terminal_at: float | None = None
    created_at: float
