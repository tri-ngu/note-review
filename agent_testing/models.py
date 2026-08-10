"""Pydantic models mirroring DESIGN.md's Data model, plus a VerifierIssue
model for parsing the Verifier's per-Question output (not part of the
frozen QuestionSet, so not in DESIGN.md's Data model itself)."""

from pydantic import BaseModel, field_validator


class ConceptSnippet(BaseModel):
    quote: str
    page_number: int


class ConceptAllocation(BaseModel):
    concept: str
    weight_percentage: float
    question_count: int
    snippets: list[ConceptSnippet]

    @field_validator("snippets")
    @classmethod
    def at_least_one_snippet(cls, v: list[ConceptSnippet]) -> list[ConceptSnippet]:
        if len(v) < 1:
            raise ValueError("snippets must have at least 1 entry")
        return v


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
            raise ValueError(f"options must have exactly 4 entries, got {len(v)}")
        return v

    @field_validator("correct_answers")
    @classmethod
    def valid_correct_answers(cls, v: list[int]) -> list[int]:
        if not (1 <= len(v) <= 4):
            raise ValueError(f"correct_answers must have 1-4 entries, got {len(v)}")
        if any(a not in (1, 2, 3, 4) for a in v):
            raise ValueError(f"correct_answers entries must be in {{1,2,3,4}}, got {v}")
        if len(set(v)) != len(v):
            raise ValueError(f"correct_answers must not contain duplicates, got {v}")
        return v


class QuestionSet(BaseModel):
    questions: list[Question]


class VerifierIssue(BaseModel):
    """One Question's verdict from a Verifier call. `action` is "keep" or
    "patch"; `critique`/`snippets` are required (non-empty) only when
    action == "patch", per DESIGN.md's Verifier output format."""

    index: int
    action: str
    critique: str
    snippets: list[ConceptSnippet]

    @field_validator("action")
    @classmethod
    def valid_action(cls, v: str) -> str:
        if v not in ("keep", "patch"):
            raise ValueError(f'action must be "keep" or "patch", got {v!r}')
        return v
