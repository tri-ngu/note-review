# Game Room Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v2 Game Room backend (PROGRESS.md parts 1-5: data model/store, HTTP endpoints, WebSocket protocol, state machine/game logic, one hardcoded fixture) as a new FastAPI service under `backend/`, entered directly from one hardcoded `QuestionSet` fixture — no v1 upload/Analyzer/Generator/Verifier pipeline involved.

**Architecture:** FastAPI app with a PIN-keyed, `asyncio.Lock`-guarded in-memory `RoomStore` (mirrors v1's `SessionStore` pattern). Pure game-logic functions (scoring, ranking, shuffling) are separated from the stateful store and WebSocket layer so they're trivially unit-testable. A single WebSocket endpoint per Room drives the LOBBY → QUESTION_ACTIVE → ANSWER_REVEAL → LEADERBOARD → FINISHED state machine with a server-authoritative timer.

**Tech Stack:** Python 3.14, FastAPI (native Starlette WebSocket support, no extra WS library), Pydantic v2, pytest + FastAPI `TestClient` (HTTP and WebSocket tests), `httpx` (TestClient dependency).

## Global Constraints

- Source of truth for all behavior is `DESIGN.md`'s Room sections (Room pipeline, Room states, Room join flow, Room answer submission, Room scoring, Room cleanup, Room WebSocket message protocol, Room data model, API contract) in the docs working directory (`bai tap 4/DESIGN.md`) — **read-only**, never edit it from this clone.
- Room capped at 10 Players (`requirements.md`).
- 4-digit zero-padded PIN, string not int (`DESIGN.md` Room data model).
- 30-second server-authoritative question timer; scoring brackets: 0-5s=100, 5-10s=95, 10-15s=90, 15-20s=85, 20-25s=80, 25-30s=75; incorrect/timeout=0 (`requirements.md`, `DESIGN.md` Room scoring).
- Select-All scoring is all-or-nothing (selected set must exactly equal `correct_answers`) — no partial credit (`DESIGN.md` Room scoring).
- Standard/skip ranking ("1224") by score alone, no tie-break (`DESIGN.md` Room scoring).
- 5-minute TTL cleanup for all terminal Rooms and abandoned (never-started) Lobbies alike (`DESIGN.md` Room cleanup).
- No `remove`/`split`/resize of `QuestionSet.questions` anywhere — fixed length throughout (`DESIGN.md` Data model).
- Host auth this phase: minimal HTTP-only session cookie, same mechanism v1 describes but set on first `POST /rooms` instead of first `/upload` (agreed with Tri 2026-08-10, since v1's `/upload` isn't being built this session).
- One hardcoded fixture only — no agent-generated pipeline, no multiple selectable fixtures (`DESIGN.md` Room mode — deferred/out of scope).
- This clone lives at `bai tap 4/game-room-build`, isolated from the docs working directory at `bai tap 4/` itself — never touch files outside this clone.

---

## File Structure

```
backend/
  requirements.txt              # fastapi, uvicorn[standard], pydantic, pytest, httpx
  app/
    __init__.py
    main.py                     # FastAPI app factory, router wiring, TTL sweep background task
    models.py                   # Question, QuestionSet, PlayerState, Answer, RoomState (Pydantic)
    fixture.py                  # WATER_CYCLE_QUESTION_SET hardcoded fixture
    game_logic.py                # compute_points, is_answer_correct, rank_standings, shuffle_questions (pure functions)
    store.py                     # RoomStore: PIN generation, create/get/mutate/sweep_expired
    session.py                    # minimal HTTP-only session cookie helper (Host identity)
    rooms_http.py                  # POST /rooms, POST /rooms/{pin}/join, GET /rooms/{pin}
    rooms_ws.py                     # WS /ws/room/{pin}, message protocol, state machine, timer
  tests/
    __init__.py
    test_models.py
    test_game_logic.py
    test_store.py
    test_rooms_http.py
    test_rooms_ws.py
```

---

### Task 1: Backend scaffold

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_main.py`

**Interfaces:**
- Produces: `app.main.create_app() -> FastAPI` — factory used by every later HTTP/WS test via `TestClient(create_app())`.

- [ ] **Step 1: Create `backend/requirements.txt`**

```
fastapi>=0.115
uvicorn[standard]>=0.30
pydantic>=2.0
pytest>=8.0
httpx>=0.27
```

- [ ] **Step 2: Install dependencies**

Run: `cd backend && pip install -r requirements.txt`
Expected: install completes without errors.

- [ ] **Step 3: Write the failing test**

```python
# backend/tests/test_main.py
from fastapi.testclient import TestClient
from app.main import create_app

def test_health_check():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'` or similar.

- [ ] **Step 5: Write minimal implementation**

```python
# backend/app/__init__.py
```

```python
# backend/app/main.py
from fastapi import FastAPI

def create_app() -> FastAPI:
    app = FastAPI(title="Game Room Backend")

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    return app

app = create_app()
```

```python
# backend/tests/__init__.py
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/app/__init__.py backend/app/main.py backend/tests/__init__.py backend/tests/test_main.py
git commit -m "feat: scaffold FastAPI backend with health check"
```

---

### Task 2: Data model

**Files:**
- Create: `backend/app/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Question`, `QuestionSet`, `PlayerState`, `Answer`, `RoomState` (all `pydantic.BaseModel`, importable from `app.models`). `RoomState` fields: `pin: str`, `host_session_id: str`, `question_set: QuestionSet`, `status: Literal["lobby","question_active","answer_reveal","leaderboard","finished"]` (default `"lobby"`), `current_round: int` (default `0`), `question_start_time: float | None` (default `None`), `players: dict[str, PlayerState]` (default `{}`), `answers: dict[str, Answer]` (default `{}`), `terminal_reason: Literal["natural_end","host_ended","host_disconnected"] | None` (default `None`), `terminal_at: float | None` (default `None`), `created_at: float` (required — implementation detail not named in `DESIGN.md`'s Room data model snippet but required to implement the abandoned-Lobby TTL rule from Room cleanup; set to `time.monotonic()` at creation by `RoomStore.create_room`, see Task 4).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_models.py
import pytest
from pydantic import ValidationError
from app.models import Question, QuestionSet, PlayerState, Answer, RoomState

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

def test_question_accepts_valid_data():
    q = Question(**_valid_question_kwargs())
    assert q.is_select_all is False

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models.py
from typing import Literal
from pydantic import BaseModel, Field, field_validator


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat: add Room data model (Question, QuestionSet, PlayerState, Answer, RoomState)"
```

---

### Task 3: Hardcoded fixture

**Files:**
- Create: `backend/app/fixture.py`
- Test: `backend/tests/test_fixture.py`

**Interfaces:**
- Consumes: `Question`, `QuestionSet` from `app.models` (Task 2).
- Produces: `WATER_CYCLE_QUESTION_SET: QuestionSet` — module-level constant, 8 questions, mixing `is_select_all` True/False, grounded in the water cycle. New content, not copied from the frontend's Build 1 flashcard fixture (`frontend/src/fixtures/fixture.ts`) — same topic, different wording, per PROGRESS.md's "new content" note. Never mutated (`shuffle_questions` from Task 4 returns a copy; Task 7's `POST /rooms` is where Room creation actually calls it).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_fixture.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_fixture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.fixture'`.

- [ ] **Step 3: Write the fixture**

```python
# backend/app/fixture.py
from app.models import Question, QuestionSet

WATER_CYCLE_QUESTION_SET = QuestionSet(
    questions=[
        Question(
            concept="Evaporation",
            question_text="Where does most of the water that evaporates into the atmosphere come from?",
            options=["Oceans", "Puddles", "Underground aquifers", "Melting glaciers"],
            correct_answers=[1],
            is_select_all=False,
            explanation="Oceans hold the vast majority of Earth's water, so they supply most evaporated water.",
            page_number=1,
            source_quote="The ocean, covering most of Earth's surface, is the single largest source of evaporated water.",
        ),
        Question(
            concept="Evaporation",
            question_text="Which of these are ways water enters the atmosphere as vapor? (Select all that apply)",
            options=["Evaporation from open water", "Transpiration from plants", "Sublimation from ice and snow", "Infiltration into soil"],
            correct_answers=[1, 2, 3],
            is_select_all=True,
            explanation="Water enters the atmosphere via evaporation, transpiration, and sublimation. Infiltration moves water into soil, not into the air.",
            page_number=1,
            source_quote="Water vapor enters the atmosphere through evaporation, transpiration, and sublimation.",
        ),
        Question(
            concept="Transpiration",
            question_text="What is transpiration?",
            options=["Water vapor released from plant leaves", "Rain falling through a forest canopy", "Water pooling on leaf surfaces", "Roots absorbing groundwater"],
            correct_answers=[1],
            is_select_all=False,
            explanation="Transpiration is the release of water vapor from plant leaves into the atmosphere.",
            page_number=1,
            source_quote="Plants release water vapor from their leaves in a process called transpiration.",
        ),
        Question(
            concept="Condensation",
            question_text="What atmospheric change causes water vapor to condense into cloud droplets?",
            options=["Rising air cools below its dew point", "Air pressure at sea level increases", "Sunlight heats the vapor further", "Wind speed decreases near the ground"],
            correct_answers=[1],
            is_select_all=False,
            explanation="As moist air rises it cools; once it drops below the dew point, vapor condenses into tiny droplets that form clouds.",
            page_number=2,
            source_quote="As air rises and cools below its dew point, water vapor condenses into the tiny droplets that make up clouds.",
        ),
        Question(
            concept="Precipitation",
            question_text="Which of these are forms precipitation can take? (Select all that apply)",
            options=["Rain", "Snow", "Hail", "Fog"],
            correct_answers=[1, 2, 3],
            is_select_all=True,
            explanation="Rain, snow, and hail are all forms of precipitation. Fog is condensation near ground level, not precipitation.",
            page_number=2,
            source_quote="Precipitation reaches the ground as rain, snow, sleet, or hail, depending on temperature.",
        ),
        Question(
            concept="Runoff",
            question_text="What is surface runoff?",
            options=["Water flowing over land into streams and rivers", "Water seeping directly into an aquifer", "Water vapor cooling into clouds", "Water absorbed by plant roots"],
            correct_answers=[1],
            is_select_all=False,
            explanation="Surface runoff is water flowing over the land surface into streams, rivers, and eventually larger bodies of water.",
            page_number=3,
            source_quote="Runoff is water that flows across the land surface into streams and rivers rather than soaking into the ground.",
        ),
        Question(
            concept="Groundwater",
            question_text="Groundwater is stored underground in formations called what?",
            options=["Aquifers", "Deltas", "Watersheds", "Reservoirs"],
            correct_answers=[1],
            is_select_all=False,
            explanation="Aquifers are underground rock and soil formations that store groundwater, sometimes for thousands of years.",
            page_number=3,
            source_quote="Groundwater accumulates in underground formations known as aquifers.",
        ),
        Question(
            concept="Water cycle overview",
            question_text="Which of these processes are part of the water cycle? (Select all that apply)",
            options=["Evaporation", "Condensation", "Precipitation", "Photosynthesis"],
            correct_answers=[1, 2, 3],
            is_select_all=True,
            explanation="Evaporation, condensation, and precipitation are core water cycle stages. Photosynthesis is a separate biological process.",
            page_number=1,
            source_quote="The water cycle consists of evaporation, condensation, and precipitation, repeating continuously.",
        ),
    ]
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_fixture.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/fixture.py backend/tests/test_fixture.py
git commit -m "feat: add hardcoded water-cycle QuestionSet fixture for Room mode"
```

---

### Task 4: Game logic (pure functions)

**Files:**
- Create: `backend/app/game_logic.py`
- Test: `backend/tests/test_game_logic.py`

**Interfaces:**
- Consumes: `Question`, `QuestionSet`, `PlayerState` from `app.models` (Task 2).
- Produces:
  - `compute_points(elapsed: float) -> int`
  - `is_answer_correct(question: Question, selected: list[int]) -> bool`
  - `rank_standings(players: dict[str, PlayerState]) -> list[dict]` — each dict: `{"player_id": str, "nickname": str, "score": int, "rank": int}`, sorted by score descending, standard/skip ranking.
  - `shuffle_questions(question_set: QuestionSet) -> QuestionSet` — returns a **new** `QuestionSet` with a shuffled copy of `questions`; never mutates the input.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_game_logic.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_game_logic.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.game_logic'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/game_logic.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_game_logic.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/game_logic.py backend/tests/test_game_logic.py
git commit -m "feat: add pure game logic (scoring, ranking, shuffling)"
```

---

### Task 5: Room store

**Files:**
- Create: `backend/app/store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `RoomState`, `QuestionSet`, `PlayerState` from `app.models` (Task 2).
- Produces:
  - `class RoomNotFoundError(Exception)`
  - `class RoomStore:`
    - `async def create_room(self, host_session_id: str, question_set: QuestionSet, now: float | None = None) -> RoomState` — generates a unique 4-digit zero-padded PIN (retried on collision), stores a new `RoomState(status="lobby", created_at=now or time.monotonic())`.
    - `async def get(self, pin: str) -> RoomState` — raises `RoomNotFoundError` if absent.
    - `def mutate(self, pin: str) -> AbstractAsyncContextManager[RoomState]` — `async with store.mutate(pin) as room:` yields the live `RoomState` under the store's lock for in-place mutation; raises `RoomNotFoundError` if absent.
    - `async def delete(self, pin: str) -> None` — no-op if absent.
    - `async def sweep_expired(self, ttl_seconds: float = 300.0, now: float | None = None) -> list[str]` — evicts and returns the PINs of every Room where (`terminal_at` is set and `now - terminal_at > ttl_seconds`) or (`status == "lobby"` and `now - created_at > ttl_seconds`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_store.py
import pytest
from app.models import Question, QuestionSet
from app.store import RoomStore, RoomNotFoundError


def _question_set():
    q = Question(
        concept="c", question_text="q", options=["A", "B", "C", "D"],
        correct_answers=[1], is_select_all=False, explanation="e",
        page_number=1, source_quote="s",
    )
    return QuestionSet(questions=[q])


@pytest.mark.asyncio
async def test_create_room_assigns_four_digit_zero_padded_pin():
    store = RoomStore()
    room = await store.create_room(host_session_id="host-1", question_set=_question_set(), now=0.0)
    assert len(room.pin) == 4
    assert room.pin.isdigit()
    assert room.status == "lobby"
    assert room.created_at == 0.0


@pytest.mark.asyncio
async def test_create_room_retries_on_pin_collision(monkeypatch):
    store = RoomStore()
    # force the first two PIN candidates to collide, third succeeds
    candidates = iter(["0001", "0001", "0002"])
    monkeypatch.setattr(store, "_random_pin", lambda: next(candidates))
    room1 = await store.create_room(host_session_id="host-1", question_set=_question_set(), now=0.0)
    room2 = await store.create_room(host_session_id="host-2", question_set=_question_set(), now=0.0)
    assert room1.pin == "0001"
    assert room2.pin == "0002"


@pytest.mark.asyncio
async def test_get_raises_when_missing():
    store = RoomStore()
    with pytest.raises(RoomNotFoundError):
        await store.get("9999")


@pytest.mark.asyncio
async def test_get_returns_created_room():
    store = RoomStore()
    room = await store.create_room(host_session_id="host-1", question_set=_question_set(), now=0.0)
    fetched = await store.get(room.pin)
    assert fetched.pin == room.pin


@pytest.mark.asyncio
async def test_mutate_persists_in_place_changes():
    store = RoomStore()
    room = await store.create_room(host_session_id="host-1", question_set=_question_set(), now=0.0)
    async with store.mutate(room.pin) as mutable_room:
        mutable_room.status = "question_active"
        mutable_room.current_round = 1
    fetched = await store.get(room.pin)
    assert fetched.status == "question_active"
    assert fetched.current_round == 1


@pytest.mark.asyncio
async def test_mutate_raises_when_missing():
    store = RoomStore()
    with pytest.raises(RoomNotFoundError):
        async with store.mutate("9999"):
            pass


@pytest.mark.asyncio
async def test_delete_is_noop_when_missing():
    store = RoomStore()
    await store.delete("9999")  # must not raise


@pytest.mark.asyncio
async def test_sweep_expired_evicts_terminal_rooms_past_ttl():
    store = RoomStore()
    room = await store.create_room(host_session_id="host-1", question_set=_question_set(), now=0.0)
    async with store.mutate(room.pin) as mutable_room:
        mutable_room.status = "finished"
        mutable_room.terminal_at = 0.0
    evicted = await store.sweep_expired(ttl_seconds=300.0, now=301.0)
    assert evicted == [room.pin]
    with pytest.raises(RoomNotFoundError):
        await store.get(room.pin)


@pytest.mark.asyncio
async def test_sweep_expired_leaves_terminal_rooms_within_ttl():
    store = RoomStore()
    room = await store.create_room(host_session_id="host-1", question_set=_question_set(), now=0.0)
    async with store.mutate(room.pin) as mutable_room:
        mutable_room.status = "finished"
        mutable_room.terminal_at = 0.0
    evicted = await store.sweep_expired(ttl_seconds=300.0, now=100.0)
    assert evicted == []
    await store.get(room.pin)  # still present


@pytest.mark.asyncio
async def test_sweep_expired_evicts_abandoned_lobby_by_created_at():
    store = RoomStore()
    room = await store.create_room(host_session_id="host-1", question_set=_question_set(), now=0.0)
    # still "lobby", never started, never terminal
    evicted = await store.sweep_expired(ttl_seconds=300.0, now=301.0)
    assert evicted == [room.pin]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.store'` (and `pytest-asyncio` not installed yet).

- [ ] **Step 3: Add `pytest-asyncio` and configure it**

```
# append to backend/requirements.txt
pytest-asyncio>=0.24
```

Run: `cd backend && pip install -r requirements.txt`

```ini
# backend/pytest.ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 4: Write minimal implementation**

```python
# backend/app/store.py
import asyncio
import random
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.models import QuestionSet, RoomState


class RoomNotFoundError(Exception):
    def __init__(self, pin: str):
        super().__init__(f"no Room found for PIN {pin!r}")
        self.pin = pin


class RoomStore:
    def __init__(self) -> None:
        self._rooms: dict[str, RoomState] = {}
        self._lock = asyncio.Lock()

    def _random_pin(self) -> str:
        return f"{random.randint(0, 9999):04d}"

    async def create_room(
        self, host_session_id: str, question_set: QuestionSet, now: float | None = None
    ) -> RoomState:
        created_at = now if now is not None else time.monotonic()
        async with self._lock:
            pin = self._random_pin()
            while pin in self._rooms:
                pin = self._random_pin()
            room = RoomState(
                pin=pin,
                host_session_id=host_session_id,
                question_set=question_set,
                created_at=created_at,
            )
            self._rooms[pin] = room
            return room

    async def get(self, pin: str) -> RoomState:
        async with self._lock:
            room = self._rooms.get(pin)
            if room is None:
                raise RoomNotFoundError(pin)
            return room

    @asynccontextmanager
    async def mutate(self, pin: str) -> AsyncIterator[RoomState]:
        async with self._lock:
            room = self._rooms.get(pin)
            if room is None:
                raise RoomNotFoundError(pin)
            yield room

    async def delete(self, pin: str) -> None:
        async with self._lock:
            self._rooms.pop(pin, None)

    async def sweep_expired(self, ttl_seconds: float = 300.0, now: float | None = None) -> list[str]:
        current = now if now is not None else time.monotonic()
        evicted: list[str] = []
        async with self._lock:
            for pin, room in list(self._rooms.items()):
                expired = (
                    room.terminal_at is not None and current - room.terminal_at > ttl_seconds
                ) or (
                    room.terminal_at is None
                    and room.status == "lobby"
                    and current - room.created_at > ttl_seconds
                )
                if expired:
                    evicted.append(pin)
                    del self._rooms[pin]
        return evicted
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_store.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/store.py backend/tests/test_store.py backend/requirements.txt backend/pytest.ini
git commit -m "feat: add RoomStore with PIN generation, mutation, and TTL sweep"
```

---

### Task 6: Session cookie helper (Host identity)

**Files:**
- Create: `backend/app/session.py`
- Test: `backend/tests/test_session.py`

**Interfaces:**
- Produces:
  - `SESSION_COOKIE_NAME: str = "session_id"`
  - `def get_or_create_session_id(request: Request, response: Response) -> str` — reads `SESSION_COOKIE_NAME` from `request.cookies`; if absent, generates a new `uuid4().hex`, sets it on `response` as an HTTP-only cookie, and returns it either way.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_session.py
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from app.session import get_or_create_session_id, SESSION_COOKIE_NAME


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(request: Request, response: Response):
        session_id = get_or_create_session_id(request, response)
        return {"session_id": session_id}

    return app


def test_first_request_sets_a_session_cookie():
    client = TestClient(_build_test_app())
    response = client.get("/whoami")
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies
    assert response.json()["session_id"] == response.cookies[SESSION_COOKIE_NAME]


def test_subsequent_request_reuses_existing_cookie():
    client = TestClient(_build_test_app())
    first = client.get("/whoami")
    session_id = first.json()["session_id"]
    second = client.get("/whoami")
    assert second.json()["session_id"] == session_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.session'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/session.py
import uuid

from fastapi import Request, Response

SESSION_COOKIE_NAME = "session_id"


def get_or_create_session_id(request: Request, response: Response) -> str:
    existing = request.cookies.get(SESSION_COOKIE_NAME)
    if existing:
        return existing
    new_session_id = uuid.uuid4().hex
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_session_id,
        httponly=True,
        samesite="lax",
    )
    return new_session_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_session.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/session.py backend/tests/test_session.py
git commit -m "feat: add minimal HTTP-only session cookie helper for Host identity"
```

---

### Task 7: HTTP endpoints

**Files:**
- Create: `backend/app/rooms_http.py`
- Modify: `backend/app/main.py` — wire the router in, attach a `RoomStore` instance to `app.state.room_store`
- Test: `backend/tests/test_rooms_http.py`

**Interfaces:**
- Consumes: `RoomStore`, `RoomNotFoundError` (Task 5), `get_or_create_session_id` (Task 6), `WATER_CYCLE_QUESTION_SET` (Task 3), `shuffle_questions` (Task 4).
- Produces: `rooms_router: APIRouter` with:
  - `POST /rooms` → `200 {"pin": str}`, sets session cookie, creates a Room with `question_set = shuffle_questions(WATER_CYCLE_QUESTION_SET)`.
  - `POST /rooms/{pin}/join` → body `{"nickname": str}` → `200 {"player_id": str, "nickname": str}` (auto-suffixed on collision), `404 {"detail": "room_not_found"}`, `409 {"detail": "room_full"}`, `409 {"detail": "already_started"}`.
  - `GET /rooms/{pin}` → `200 {"status": "lobby"|"in_progress"|"finished", "player_count": int}`, `404 {"detail": "room_not_found"}`.
- `app.state.room_store` is read by Task 8's WS endpoint too — same store instance for the whole app.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_rooms_http.py
from fastapi.testclient import TestClient
from app.main import create_app


def test_create_room_sets_cookie_and_returns_pin():
    client = TestClient(create_app())
    response = client.post("/rooms")
    assert response.status_code == 200
    body = response.json()
    assert len(body["pin"]) == 4
    assert body["pin"].isdigit()
    assert "session_id" in response.cookies


def test_join_room_returns_player_id():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    assert response.status_code == 200
    body = response.json()
    assert body["nickname"] == "Alice"
    assert body["player_id"]


def test_join_room_auto_suffixes_duplicate_nicknames():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    assert response.json()["nickname"] == "Alice (1)"


def test_join_nonexistent_room_returns_404():
    client = TestClient(create_app())
    response = client.post("/rooms/0000/join", json={"nickname": "Alice"})
    assert response.status_code == 404
    assert response.json()["detail"] == "room_not_found"


def test_join_full_room_returns_409():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    for i in range(10):
        response = client.post(f"/rooms/{pin}/join", json={"nickname": f"Player{i}"})
        assert response.status_code == 200
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "OneTooMany"})
    assert response.status_code == 409
    assert response.json()["detail"] == "room_full"


def test_get_room_status_lobby():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    response = client.get(f"/rooms/{pin}")
    assert response.status_code == 200
    assert response.json() == {"status": "lobby", "player_count": 1}


def test_get_nonexistent_room_returns_404():
    client = TestClient(create_app())
    response = client.get("/rooms/0000")
    assert response.status_code == 404
    assert response.json()["detail"] == "room_not_found"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_rooms_http.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.rooms_http'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/rooms_http.py
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.fixture import WATER_CYCLE_QUESTION_SET
from app.game_logic import shuffle_questions
from app.models import PlayerState
from app.session import get_or_create_session_id
from app.store import RoomNotFoundError, RoomStore

rooms_router = APIRouter()

ROOM_CAPACITY = 10


class JoinRequest(BaseModel):
    nickname: str


def _room_store(request: Request) -> RoomStore:
    return request.app.state.room_store


@rooms_router.post("/rooms")
async def create_room(request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    store = _room_store(request)
    room = await store.create_room(
        host_session_id=session_id,
        question_set=shuffle_questions(WATER_CYCLE_QUESTION_SET),
    )
    return {"pin": room.pin}


def _unique_nickname(existing_nicknames: set[str], requested: str) -> str:
    if requested not in existing_nicknames:
        return requested
    suffix = 1
    while f"{requested} ({suffix})" in existing_nicknames:
        suffix += 1
    return f"{requested} ({suffix})"


@rooms_router.post("/rooms/{pin}/join")
async def join_room(pin: str, body: JoinRequest, request: Request):
    store = _room_store(request)
    try:
        async with store.mutate(pin) as room:
            if room.status != "lobby":
                raise HTTPException(status_code=409, detail="already_started")
            if len(room.players) >= ROOM_CAPACITY:
                raise HTTPException(status_code=409, detail="room_full")
            existing_nicknames = {p.nickname for p in room.players.values()}
            nickname = _unique_nickname(existing_nicknames, body.nickname)
            player_id = uuid.uuid4().hex
            room.players[player_id] = PlayerState(player_id=player_id, nickname=nickname)
            return {"player_id": player_id, "nickname": nickname}
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="room_not_found")


_PUBLIC_STATUS = {
    "lobby": "lobby",
    "question_active": "in_progress",
    "answer_reveal": "in_progress",
    "leaderboard": "in_progress",
    "finished": "finished",
}


@rooms_router.get("/rooms/{pin}")
async def get_room(pin: str, request: Request):
    store = _room_store(request)
    try:
        room = await store.get(pin)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="room_not_found")
    return {
        "status": _PUBLIC_STATUS[room.status],
        "player_count": len(room.players),
    }
```

- [ ] **Step 4: Wire the router and store into the app**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.rooms_http import rooms_router
from app.store import RoomStore


def create_app() -> FastAPI:
    app = FastAPI(title="Game Room Backend")
    app.state.room_store = RoomStore()

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    app.include_router(rooms_router)

    return app


app = create_app()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_rooms_http.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `cd backend && pytest -v`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/rooms_http.py backend/app/main.py backend/tests/test_rooms_http.py
git commit -m "feat: add Room HTTP endpoints (create, join, status)"
```

---

### Task 8: WebSocket protocol and state machine

**Files:**
- Create: `backend/app/rooms_ws.py`
- Modify: `backend/app/main.py` — mount the WS route
- Test: `backend/tests/test_rooms_ws.py`

**Interfaces:**
- Consumes: `RoomStore`, `RoomNotFoundError` (Task 5), `compute_points`, `is_answer_correct`, `rank_standings` (Task 4), `Answer`, `RoomState` (Task 2), `SESSION_COOKIE_NAME` (Task 6).
- Produces:
  - `QUESTION_TIMEOUT_SECONDS: float = 30.0` — module-level, read at call time so tests can `monkeypatch.setattr(rooms_ws, "QUESTION_TIMEOUT_SECONDS", ...)`.
  - `async def rooms_websocket_endpoint(websocket: WebSocket, pin: str) -> None` — mounted at `WS /ws/room/{pin}`. Host connects via the `session_id` cookie matching `RoomState.host_session_id`; Player connects via `?player_id=...` query param matching an existing `PlayerState`. Rejects (closes with code 4403) anything that doesn't match.
  - Server → client message shapes exactly as `DESIGN.md`'s Room WebSocket message protocol: `player_joined`, `player_left`, `question_start`, `answered_count`, `answer_reveal`, `leaderboard`, `game_over`, `error` — each `{"type": <name>, **payload}`.
  - Client → server message shapes: `submit_answer` (`{round, selected}`, Player only), `advance` (`{}`, Host only), `end_game` (`{}`, Host only).

This task is the largest — split into three sub-steps (connect/auth, LOBBY→QUESTION_ACTIVE→ANSWER_REVEAL→LEADERBOARD happy path, End Game / Host-disconnect / timeout edge cases) but committed as one task since the WS handler is one cohesive unit that isn't meaningfully testable in smaller pieces (the state machine only makes sense end-to-end).

- [ ] **Step 1: Write the failing tests — connection auth**

```python
# backend/tests/test_rooms_ws.py
from fastapi.testclient import TestClient
from app.main import create_app


def _create_room_and_host_client():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    return client, pin


def test_host_can_connect_with_session_cookie():
    client, pin = _create_room_and_host_client()
    with client.websocket_connect(f"/ws/room/{pin}") as ws:
        ws.send_json({"type": "advance"})
        # LOBBY -> QUESTION_ACTIVE broadcasts question_start to the Host too
        message = ws.receive_json()
        assert message["type"] == "question_start"


def test_host_connect_rejected_without_matching_session():
    client, pin = _create_room_and_host_client()
    other_client = TestClient(create_app())  # fresh client, no cookie for this room's host
    # reuse the same app instance so the room actually exists for other_client
    other_client.app = client.app
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with other_client.websocket_connect(f"/ws/room/{pin}"):
            pass


def test_player_can_connect_with_player_id():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as ws:
        message = ws.receive_json()
        assert message["type"] == "player_joined"
        assert message["player_id"] == player_id


def test_player_connect_rejected_with_unknown_player_id():
    import pytest
    from starlette.websockets import WebSocketDisconnect

    client, pin = _create_room_and_host_client()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/room/{pin}?player_id=not-a-real-id"):
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_rooms_ws.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.rooms_ws'`.

- [ ] **Step 3: Write the WS endpoint — connection, auth, and broadcast plumbing**

```python
# backend/app/rooms_ws.py
import asyncio
import time

from fastapi import WebSocket, WebSocketDisconnect

from app.game_logic import compute_points, is_answer_correct, rank_standings
from app.models import Answer
from app.session import SESSION_COOKIE_NAME
from app.store import RoomNotFoundError, RoomStore

QUESTION_TIMEOUT_SECONDS = 30.0


class _RoomConnections:
    """Tracks live WebSocket connections for one Room's broadcast fan-out."""

    def __init__(self) -> None:
        self.host: WebSocket | None = None
        self.players: dict[str, WebSocket] = {}

    def all_sockets(self):
        sockets = list(self.players.values())
        if self.host is not None:
            sockets.append(self.host)
        return sockets


_connections: dict[str, _RoomConnections] = {}


def _connections_for(pin: str) -> _RoomConnections:
    return _connections.setdefault(pin, _RoomConnections())


async def _broadcast(pin: str, message: dict) -> None:
    conns = _connections_for(pin)
    for socket in conns.all_sockets():
        await socket.send_json(message)


async def rooms_websocket_endpoint(websocket: WebSocket, pin: str) -> None:
    store: RoomStore = websocket.app.state.room_store
    try:
        room = await store.get(pin)
    except RoomNotFoundError:
        await websocket.close(code=4404)
        return

    player_id = websocket.query_params.get("player_id")
    conns = _connections_for(pin)

    if player_id is not None:
        if player_id not in room.players:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        conns.players[player_id] = websocket
        await _broadcast(pin, {"type": "player_joined", "player_id": player_id, "nickname": room.players[player_id].nickname})
        role = "player"
    else:
        session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
        if session_id != room.host_session_id:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        conns.host = websocket
        role = "host"

    try:
        while True:
            message = await websocket.receive_json()
            await _handle_message(store, pin, role, player_id, message)
    except WebSocketDisconnect:
        await _handle_disconnect(store, pin, role, player_id)


async def _handle_message(store: RoomStore, pin: str, role: str, player_id: str | None, message: dict) -> None:
    message_type = message.get("type")
    if role == "host" and message_type == "advance":
        await _handle_advance(store, pin)
    elif role == "host" and message_type == "end_game":
        await _end_game(store, pin, reason="host_ended")
    elif role == "player" and message_type == "submit_answer":
        await _handle_submit_answer(store, pin, player_id, message)
    # any other role/message_type combination is silently ignored —
    # DESIGN.md says "rejected", enforced here by simply not acting on it


async def _handle_disconnect(store: RoomStore, pin: str, role: str, player_id: str | None) -> None:
    conns = _connections_for(pin)
    if role == "host":
        conns.host = None
        await _end_game(store, pin, reason="host_disconnected")
        return

    conns.players.pop(player_id, None)
    async with store.mutate(pin) as room:
        if room.status == "lobby":
            room.players.pop(player_id, None)
            lobby_still_open = True
        else:
            room.players[player_id].connected = False
            lobby_still_open = False
    if lobby_still_open:
        await _broadcast(pin, {"type": "player_left", "player_id": player_id})
```

- [ ] **Step 4: Run connection tests to verify they pass**

Run: `cd backend && pytest tests/test_rooms_ws.py -v -k "connect"`
Expected: `test_player_can_connect_with_player_id` and the two rejection tests PASS; `test_host_can_connect_with_session_cookie` still FAILS (no `advance`/`question_start` handling yet — written next).

- [ ] **Step 5: Write the failing tests — happy-path state machine**

```python
# append to backend/tests/test_rooms_ws.py

def test_advance_from_lobby_starts_first_question_and_broadcasts_to_player():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        player_ws.receive_json()  # player_joined
        host_ws.send_json({"type": "advance"})
        host_question = host_ws.receive_json()
        player_question = player_ws.receive_json()
        assert host_question["type"] == "question_start"
        assert player_question["type"] == "question_start"
        assert "correct_answers" not in player_question
        assert "explanation" not in player_question
        assert host_question["round"] == 1


def test_submit_answer_from_all_players_triggers_answer_reveal():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        player_ws.receive_json()  # player_joined
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
        question = player_ws.receive_json()  # question_start

        player_ws.send_json({"type": "submit_answer", "round": question["round"], "selected": [1]})

        host_answered_count = host_ws.receive_json()
        assert host_answered_count["type"] == "answered_count"
        assert host_answered_count["answered"] == 1
        assert host_answered_count["total_connected"] == 1

        host_reveal = host_ws.receive_json()
        player_reveal = player_ws.receive_json()
        assert host_reveal["type"] == "answer_reveal"
        assert player_reveal["type"] == "answer_reveal"
        assert "correct_answers" in host_reveal


def test_advance_after_reveal_moves_to_leaderboard_then_next_question():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        player_ws.receive_json()
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()
        question = player_ws.receive_json()
        player_ws.send_json({"type": "submit_answer", "round": question["round"], "selected": [1]})
        host_ws.receive_json()  # answered_count
        host_ws.receive_json()  # answer_reveal
        player_ws.receive_json()  # answer_reveal

        host_ws.send_json({"type": "advance"})
        host_leaderboard = host_ws.receive_json()
        assert host_leaderboard["type"] == "leaderboard"
        assert host_leaderboard["standings"][0]["player_id"] == player_id

        host_ws.send_json({"type": "advance"})
        next_question = host_ws.receive_json()
        assert next_question["type"] == "question_start"
        assert next_question["round"] == 2


def test_end_game_from_leaderboard_broadcasts_game_over():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        player_ws.receive_json()
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()
        question = player_ws.receive_json()
        player_ws.send_json({"type": "submit_answer", "round": question["round"], "selected": [1]})
        host_ws.receive_json()  # answered_count
        host_ws.receive_json()  # answer_reveal
        player_ws.receive_json()  # answer_reveal
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # leaderboard

        host_ws.send_json({"type": "end_game"})
        game_over = host_ws.receive_json()
        assert game_over["type"] == "game_over"
        assert game_over["reason"] == "host_ended"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_rooms_ws.py -v`
Expected: FAIL — `advance` currently does nothing (`_handle_advance` not yet defined).

- [ ] **Step 7: Implement the state machine handlers**

```python
# append to backend/app/rooms_ws.py

def _question_start_payload(room, round_index: int) -> dict:
    question = room.question_set.questions[round_index]
    return {
        "type": "question_start",
        "round": round_index + 1,
        "total_rounds": len(room.question_set.questions),
        "question_text": question.question_text,
        "options": question.options,
        "is_select_all": question.is_select_all,
        "page_number": question.page_number,
        "concept": question.concept,
        "server_time": time.monotonic(),
    }


async def _handle_advance(store: RoomStore, pin: str) -> None:
    async with store.mutate(pin) as room:
        if room.status == "lobby":
            round_index = 0
            room.status = "question_active"
            room.current_round = round_index
            room.question_start_time = time.monotonic()
            room.answers = {}
            payload = _question_start_payload(room, round_index)
        elif room.status == "leaderboard" and room.current_round + 1 < len(room.question_set.questions):
            round_index = room.current_round + 1
            room.status = "question_active"
            room.current_round = round_index
            room.question_start_time = time.monotonic()
            room.answers = {}
            payload = _question_start_payload(room, round_index)
        elif room.status == "leaderboard":
            await _finish_game(store, pin, reason="natural_end")
            return
        else:
            return  # advance is a no-op outside lobby/leaderboard
    await _broadcast(pin, payload)
    asyncio.create_task(_run_question_timer(store, pin, payload["round"]))


async def _run_question_timer(store: RoomStore, pin: str, round_number: int) -> None:
    await asyncio.sleep(QUESTION_TIMEOUT_SECONDS)
    try:
        async with store.mutate(pin) as room:
            if room.status != "question_active" or room.current_round + 1 != round_number:
                return  # already advanced by all-answered path
    except RoomNotFoundError:
        return
    await _reveal_answers(store, pin)


async def _handle_submit_answer(store: RoomStore, pin: str, player_id: str, message: dict) -> None:
    now = time.monotonic()
    should_reveal = False
    async with store.mutate(pin) as room:
        if room.status != "question_active":
            return
        if player_id in room.answers:
            return  # one-shot: already answered
        if room.current_round != message.get("round", 0) - 1:
            return
        question = room.question_set.questions[room.current_round]
        elapsed = now - (room.question_start_time or now)
        if elapsed > QUESTION_TIMEOUT_SECONDS:
            return  # arrived after server cutoff — treated as timeout, no answer recorded
        selected = message.get("selected", [])
        correct = is_answer_correct(question, selected)
        points = compute_points(elapsed) if correct else 0
        room.answers[player_id] = Answer(
            player_id=player_id, selected=selected, elapsed=elapsed, correct=correct, points=points
        )
        room.players[player_id].score += points
        connected_players = [p for p in room.players.values() if p.connected]
        answered_count = len(room.answers)
        total_connected = len(connected_players)
        should_reveal = answered_count >= total_connected and total_connected > 0
    await _broadcast(pin, {"type": "answered_count", "answered": answered_count, "total_connected": total_connected})
    if should_reveal:
        await _reveal_answers(store, pin)


async def _reveal_answers(store: RoomStore, pin: str) -> None:
    async with store.mutate(pin) as room:
        if room.status != "question_active":
            return
        room.status = "answer_reveal"
        question = room.question_set.questions[room.current_round]
        results = {
            player_id: {"correct": answer.correct, "points": answer.points}
            for player_id, answer in room.answers.items()
        }
        payload = {
            "type": "answer_reveal",
            "round": room.current_round + 1,
            "correct_answers": question.correct_answers,
            "explanation": question.explanation,
            "results": results,
        }
    await _broadcast(pin, payload)
    await _show_leaderboard(store, pin)


async def _show_leaderboard(store: RoomStore, pin: str) -> None:
    async with store.mutate(pin) as room:
        room.status = "leaderboard"
        standings = rank_standings(room.players)
        is_final = room.current_round + 1 >= len(room.question_set.questions)
        payload = {
            "type": "leaderboard",
            "round": room.current_round + 1,
            "total_rounds": len(room.question_set.questions),
            "standings": standings,
            "is_final": is_final,
        }
    await _broadcast(pin, payload)


async def _finish_game(store: RoomStore, pin: str, reason: str) -> None:
    async with store.mutate(pin) as room:
        room.status = "finished"
        room.terminal_reason = reason
        room.terminal_at = time.monotonic()
        standings = rank_standings(room.players)
        payload = {"type": "game_over", "reason": reason, "final_standings": standings}
    await _broadcast(pin, payload)


async def _end_game(store: RoomStore, pin: str, reason: str) -> None:
    try:
        await _finish_game(store, pin, reason)
    except RoomNotFoundError:
        pass
```

`_handle_message` (already written in Step 3) already calls `_handle_advance`, `_end_game`, and `_handle_submit_answer` by name — no changes needed now that Step 7 defines them; Step 3's version was failing only because those names didn't exist yet.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_rooms_ws.py -v`
Expected: PASS (all connection + happy-path tests)

- [ ] **Step 9: Write the failing tests — timeout and Host-disconnect edge cases**

```python
# append to backend/tests/test_rooms_ws.py
import app.rooms_ws as rooms_ws


def test_question_times_out_and_reveals_with_zero_points_for_non_answerer(monkeypatch):
    monkeypatch.setattr(rooms_ws, "QUESTION_TIMEOUT_SECONDS", 0.05)
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        player_ws.receive_json()
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
        player_ws.receive_json()  # question_start
        # nobody answers — wait for the shortened timer to fire
        reveal = host_ws.receive_json()
        assert reveal["type"] == "answer_reveal"
        assert reveal["results"] == {}


def test_host_disconnect_ends_game_for_remaining_players(monkeypatch):
    monkeypatch.setattr(rooms_ws, "QUESTION_TIMEOUT_SECONDS", 30.0)
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        player_ws.receive_json()  # player_joined
        with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
            pass  # host connects then immediately disconnects
        game_over = player_ws.receive_json()
        assert game_over["type"] == "game_over"
        assert game_over["reason"] == "host_disconnected"
```

- [ ] **Step 10: Run tests to verify they fail (or pass if already correct — confirm before moving on)**

Run: `cd backend && pytest tests/test_rooms_ws.py -v -k "timeout or disconnect"`
Expected: both should PASS given Steps 3-7's implementation already covers the timer and `_handle_disconnect`; if `test_question_times_out...` hangs or fails, check that `_run_question_timer`'s round-number guard (`room.current_round + 1 != round_number`) matches the 1-indexed `round` passed from `_handle_advance`.

- [ ] **Step 11: Mount the WS route**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.rooms_http import rooms_router
from app.rooms_ws import rooms_websocket_endpoint
from app.store import RoomStore


def create_app() -> FastAPI:
    app = FastAPI(title="Game Room Backend")
    app.state.room_store = RoomStore()

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    app.include_router(rooms_router)
    app.add_api_websocket_route("/ws/room/{pin}", rooms_websocket_endpoint)

    return app


app = create_app()
```

- [ ] **Step 12: Run the full suite**

Run: `cd backend && pytest -v`
Expected: every test across all files PASSES.

- [ ] **Step 13: Commit**

```bash
git add backend/app/rooms_ws.py backend/app/main.py backend/tests/test_rooms_ws.py
git commit -m "feat: add Room WebSocket protocol and state machine"
```

---

### Task 9: TTL cleanup background task

**Files:**
- Modify: `backend/app/main.py` — add a startup background task running `store.sweep_expired()` periodically
- Test: `backend/tests/test_cleanup_task.py`

**Interfaces:**
- Consumes: `RoomStore.sweep_expired` (Task 5).
- Produces: `async def start_cleanup_sweep(store: RoomStore, interval_seconds: float = 30.0, ttl_seconds: float = 300.0) -> None` — infinite loop, `await asyncio.sleep(interval_seconds)` then `await store.sweep_expired(ttl_seconds)`, wired into `create_app()` via a FastAPI `lifespan` context so it starts on app startup and is cancelled on shutdown.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cleanup_task.py
import asyncio
import pytest

from app.models import Question, QuestionSet
from app.store import RoomStore
from app.main import start_cleanup_sweep


def _question_set():
    q = Question(
        concept="c", question_text="q", options=["A", "B", "C", "D"],
        correct_answers=[1], is_select_all=False, explanation="e",
        page_number=1, source_quote="s",
    )
    return QuestionSet(questions=[q])


@pytest.mark.asyncio
async def test_cleanup_sweep_evicts_expired_rooms_on_its_interval():
    store = RoomStore()
    room = await store.create_room(host_session_id="h1", question_set=_question_set(), now=0.0)
    async with store.mutate(room.pin) as mutable_room:
        mutable_room.status = "finished"
        mutable_room.terminal_at = 0.0

    task = asyncio.create_task(
        start_cleanup_sweep(store, interval_seconds=0.01, ttl_seconds=0.0)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    from app.store import RoomNotFoundError
    with pytest.raises(RoomNotFoundError):
        await store.get(room.pin)
```

Note: `sweep_expired`'s default `now` is `time.monotonic()` when not passed — since `ttl_seconds=0.0` here, any positive elapsed time since `terminal_at=0.0` already exceeds the TTL, so the real clock works fine without needing to pass `now` explicitly.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_cleanup_task.py -v`
Expected: FAIL with `ImportError: cannot import name 'start_cleanup_sweep' from 'app.main'`.

- [ ] **Step 3: Implement the sweep loop and wire it into app lifespan**

```python
# backend/app/main.py
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.rooms_http import rooms_router
from app.rooms_ws import rooms_websocket_endpoint
from app.store import RoomStore


async def start_cleanup_sweep(store: RoomStore, interval_seconds: float = 30.0, ttl_seconds: float = 300.0) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await store.sweep_expired(ttl_seconds=ttl_seconds)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cleanup_task = asyncio.create_task(start_cleanup_sweep(app.state.room_store))
        yield
        cleanup_task.cancel()

    app = FastAPI(title="Game Room Backend", lifespan=lifespan)
    app.state.room_store = RoomStore()

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    app.include_router(rooms_router)
    app.add_api_websocket_route("/ws/room/{pin}", rooms_websocket_endpoint)

    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_cleanup_task.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `cd backend && pytest -v`
Expected: every test PASSES.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_cleanup_task.py
git commit -m "feat: add periodic TTL cleanup sweep wired into app lifespan"
```

---

## Post-plan check (manual, before calling the backend done)

- [ ] Run `cd backend && pytest -v` one final time — full green suite.
- [ ] Manually start the server (`cd backend && uvicorn app.main:app --reload`) and, using two browser tabs or `curl`/`websocat`, walk through: create a Room, join as a Player, advance through all 8 fixture Questions, confirm the final `game_over` leaderboard matches expected scores.
- [ ] Report back to Tri before starting frontend work (parts 6-8) — out of scope for this plan.
