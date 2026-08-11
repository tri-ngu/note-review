import asyncio
import pytest

from app.models import Question, QuestionSet
from app.store import RoomStore, RoomNotFoundError
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

    with pytest.raises(RoomNotFoundError):
        await store.get(room.pin)
