"""v1 generation pipeline endpoints (Note upload -> Analyzer checkpoint ->
Generator/Verify -> Question Set), per DESIGN.md's API contract."""

import asyncio
import json

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from openai import BadRequestError, RateLimitError
from pydantic import BaseModel, ValidationError

from app.extraction import UploadValidationError, extract_note_text
from app.models import ConceptAllocation, Question
from app.pipeline import PipelineError, freeze, run_analyzer, run_generator_initial, run_verify_loop
from app.session import get_or_create_session_id
from app.session_store import SessionStore

generation_router = APIRouter()

# requirements.md's Error handling: "show a generic error message" — deliberately
# vague, no pipeline internals leaked to the client.
GENERIC_FAILURE_MESSAGE = "Generation failed. Please try again."


def _session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


@generation_router.post("/upload")
async def upload_note(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    target_question_count: int | None = Form(None),
):
    file_bytes = await file.read()
    try:
        note_text = extract_note_text(file_bytes)
    except UploadValidationError as e:
        raise HTTPException(status_code=400, detail=e.error_code)

    step_log: list[str] = []
    try:
        allocations = await run_analyzer(note_text, target_question_count, step_log)
    except (PipelineError, RateLimitError, BadRequestError):
        raise HTTPException(status_code=502, detail="generation_failed")

    session_id = get_or_create_session_id(request, response)
    store = _session_store(request)
    async with store.mutate(session_id) as state:
        state.status = "checkpoint_pending"
        state.note_text = note_text
        state.target_question_count = target_question_count
        state.allocations = allocations
        state.question_set = None
        state.error_message = None

    return {"concepts": [a.model_dump() for a in allocations]}


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _run_pipeline_sse(
    note_text: str, allocations: list[ConceptAllocation], session_id: str, store: SessionStore
) -> StreamingResponse:
    """Shared body for /generate and /generate/retry: runs Generator-initial
    + the verify loop, streaming DESIGN.md's SSE event shape
    ({stage, concept?, round?}) as each concept/round completes via
    pipeline.py's on_event hook, storing the final QuestionSet (or the
    generic failure) once the run settles."""
    queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_event(evt: dict) -> None:
        queue.put_nowait(evt)

    async def run() -> None:
        step_log: list[str] = []
        try:
            concept_lists = await run_generator_initial(allocations, step_log, on_event=on_event)
            concept_lists, _satisfactory, _rounds_used = await run_verify_loop(
                concept_lists, note_text, step_log, on_event=on_event
            )
            question_set = freeze(concept_lists)
        except (PipelineError, RateLimitError, BadRequestError):
            async with store.mutate(session_id) as state:
                state.status = "failed"
                state.error_message = GENERIC_FAILURE_MESSAGE
            queue.put_nowait({"stage": "error", "message": GENERIC_FAILURE_MESSAGE})
            return

        async with store.mutate(session_id) as state:
            state.status = "ready"
            state.question_set = question_set
            state.error_message = None
        queue.put_nowait({"stage": "done", "question_set": question_set.model_dump()})

    task = asyncio.create_task(run())

    async def event_stream():
        while True:
            evt = await queue.get()
            yield _sse_event(evt)
            if evt["stage"] in ("done", "error"):
                break
        await task  # propagate any unexpected (non-PipelineError) exception

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class GenerateRequest(BaseModel):
    allocations: list[ConceptAllocation]


@generation_router.post("/generate")
async def generate(body: GenerateRequest, request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    store = _session_store(request)
    state = await store.get(session_id)

    if state.note_text is None:
        raise HTTPException(status_code=404, detail="no_active_session")

    weight_sum = sum(a.weight_percentage for a in body.allocations)
    if abs(weight_sum - 100) > 1.0:
        raise HTTPException(status_code=400, detail="weights_not_confirmed")

    # Locks question_count total server-side on receipt, per DESIGN.md.
    locked_total = sum(a.question_count for a in body.allocations)
    async with store.mutate(session_id) as state:
        state.status = "generating"
        state.allocations = body.allocations
        state.target_question_count = locked_total

    return _run_pipeline_sse(state.note_text, body.allocations, session_id, store)


@generation_router.post("/generate/retry")
async def generate_retry(request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    store = _session_store(request)
    state = await store.get(session_id)

    if state.note_text is None or state.allocations is None:
        raise HTTPException(status_code=404, detail="no_active_session")
    if state.status != "failed":
        raise HTTPException(status_code=409, detail="no_failed_run_to_retry")

    async with store.mutate(session_id) as s:
        s.status = "generating"

    return _run_pipeline_sse(state.note_text, state.allocations, session_id, store)


class QuestionPatchRequest(BaseModel):
    concept: str | None = None
    question_text: str | None = None
    options: list[str] | None = None
    correct_answers: list[int] | None = None
    is_select_all: bool | None = None
    explanation: str | None = None
    page_number: int | None = None


@generation_router.patch("/questions/{index}")
async def patch_question(index: int, body: QuestionPatchRequest, request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    store = _session_store(request)
    async with store.mutate(session_id) as state:
        if state.question_set is None:
            raise HTTPException(status_code=404, detail="no_active_question_set")
        questions = state.question_set.questions
        list_index = index - 1  # global index is 1-based; array order == index order, per DESIGN.md's Data model
        if not (0 <= list_index < len(questions)):
            raise HTTPException(status_code=404, detail="index_out_of_range")

        merged = questions[list_index].model_dump()
        merged.update(body.model_dump(exclude_unset=True))
        try:
            updated = Question(**merged)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))

        questions[list_index] = updated
        return updated.model_dump()


class ConceptRenameRequest(BaseModel):
    new_name: str


@generation_router.patch("/concepts/{old_name}")
async def patch_concept(old_name: str, body: ConceptRenameRequest, request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    store = _session_store(request)
    async with store.mutate(session_id) as state:
        if state.question_set is None:
            raise HTTPException(status_code=404, detail="no_active_question_set")
        questions = state.question_set.questions
        existing_concepts = {q.concept for q in questions}
        if old_name not in existing_concepts:
            raise HTTPException(status_code=404, detail="concept_not_found")
        if body.new_name != old_name and body.new_name in existing_concepts:
            # Rename is blocked, not merged, on a same-name collision with a
            # different existing concept — per DESIGN.md's Concept editing.
            raise HTTPException(status_code=409, detail="concept_name_collision")

        updated_count = 0
        for q in questions:
            if q.concept == old_name:
                q.concept = body.new_name
                updated_count += 1
        return {"concept": body.new_name, "updated_count": updated_count}


@generation_router.get("/session")
async def get_session(request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    store = _session_store(request)
    state = await store.get(session_id)

    body: dict = {"status": state.status}
    if state.allocations is not None:
        body["allocations"] = [a.model_dump() for a in state.allocations]
    if state.question_set is not None:
        body["questions"] = [q.model_dump() for q in state.question_set.questions]
    return body
