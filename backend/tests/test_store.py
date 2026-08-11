import asyncio

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
    await store.get(room.pin)


@pytest.mark.asyncio
async def test_sweep_expired_evicts_abandoned_lobby_by_created_at():
    store = RoomStore()
    room = await store.create_room(host_session_id="host-1", question_set=_question_set(), now=0.0)
    evicted = await store.sweep_expired(ttl_seconds=300.0, now=301.0)
    assert evicted == [room.pin]


@pytest.mark.asyncio
async def test_concurrent_create_room_never_assigns_duplicate_pins():
    store = RoomStore()
    rooms = await asyncio.gather(
        *[store.create_room(host_session_id=f"host-{i}", question_set=_question_set()) for i in range(50)]
    )
    pins = [room.pin for room in rooms]
    assert len(pins) == len(set(pins))


@pytest.mark.asyncio
async def test_concurrent_mutations_do_not_lose_updates():
    store = RoomStore()
    room = await store.create_room(host_session_id="host-1", question_set=_question_set(), now=0.0)

    async def bump_round():
        async with store.mutate(room.pin) as mutable_room:
            mutable_room.current_round += 1

    await asyncio.gather(*[bump_round() for _ in range(20)])
    fetched = await store.get(room.pin)
    assert fetched.current_round == 20
