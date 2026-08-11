# Game Room Frontend — Design

Frontend implementation for the Game Room (v2 Room mode) described in `DESIGN.md`'s Room pipeline / Room WebSocket message protocol sections. The backend (`backend/`) is already built, tested (76 pytest cases), and pushed to `origin/game-room-build` — this spec covers the frontend only, extending the existing Vite + React + TS app in `frontend/` (which currently has the v1 flashcard prototype: browse view, Review Session, in-place editing).

This corresponds to Todo parts 6-8 in `PROGRESS.md`: Host flow, Player flow, WS wiring.

## Scope

Builds all three parts (Host flow, Player flow, WS wiring) together, since they share the same routing/WS foundation and don't decompose cleanly into independent sub-projects. Room creation still uses the one hardcoded fixture (`WATER_CYCLE_QUESTION_SET`) per `DESIGN.md`'s "Room mode — deferred / out of scope" — connecting to a live-generated Question Set and the real v2 hub screen stay deferred, as already documented there.

## Routing

No router exists in the current frontend (`App.tsx` renders the flashcard view directly). Adds `react-router` with four routes:

- `/` — existing flashcard app (`FlashcardView`), gains a "Create Room" button next to "Start Review"
- `/host/:pin` — Host view (Lobby → in-game controller → leaderboard → final)
- `/join/:pin` — Player join page (PIN pre-filled from the URL param, nickname entry)
- `/play/:pin` — Player view (waiting → question → reveal → leaderboard → final), `player_id` carried as a `?player_id=` query param so it survives a page reference without needing app-level state

Each of `/host/:pin` and `/play/:pin` is a single route whose page component switches between sub-view panels based on `RoomState.status`, delivered live over the room's WebSocket — not separate routes per phase, since phase transitions are server-driven, not navigation events.

## Entry point

"Create Room" button lives on the existing `FlashcardView` (browse view), next to "Start Review". Uses that view's already-loaded fixture `QuestionSet` conceptually (though `POST /rooms` currently ignores any request body and always uses the backend's own hardcoded fixture — this button is a stand-in for the deferred real hub, matching `DESIGN.md`'s existing "Room mode — deferred / out of scope" note). Clicking it calls `POST /rooms`, then navigates to `/host/:pin` with the returned PIN.

## QR code

`qrcode.react`'s `<QRCodeSVG>` component, rendered client-side in the Lobby panel, encoding `{origin}/join/{pin}`. No network call, pure SVG.

## Visual style

Matches the existing Botanical Field Guide theme (CSS Modules, same tokens/colors/fonts as the flashcard app) — one consistent visual language across the whole product, not a distinct "game show" style for Room screens.

## API / dev wiring

`vite.config.ts` gets a dev-server proxy forwarding `/rooms`, `/health`, and `/ws` to `http://localhost:8000` (FastAPI's default `uvicorn` port). Frontend code calls relative paths (`fetch("/rooms", ...)`, `new WebSocket("/ws/room/" + pin)`) — same-origin from the browser's perspective, so the session cookie flows automatically and no backend CORS configuration is needed. Production deployment shape (separate origins, real CORS) is out of scope for this build.

## WebSocket wiring

One hook, `useRoomSocket({ pin, role, playerId? })` (`src/room/useRoomSocket.ts`):

- Connects to `/ws/room/{pin}` (player role appends `?player_id={playerId}`)
- Internally a reducer switching on each inbound message's `type` field — confirmed against `backend/app/rooms_ws.py`, every server→client message is a flat `{ type, ...payload }` JSON object, matching `DESIGN.md`'s Room WebSocket message protocol section exactly
- Accumulates into one state object: roster (built from `player_joined`/`player_left`), `status` (derived from which message last arrived — `question_start` → question-active, `answer_reveal` → reveal, `leaderboard` → leaderboard, `game_over` → finished), current question (from `question_start`, correct answers withheld until reveal per protocol), `answered_count`/`total_connected` (from `answered_count`), last reveal result (from `answer_reveal`), leaderboard standings (from `leaderboard`), final standings (from `game_over`), connection state (`connecting` / `open` / `closed`)
- Returns `{ state, send }` — `send` is a thin wrapper posting `{ type, ...payload }` client→server messages (`advance`, `end_game`, `submit_answer`)
- `error` (`{ code, message }`) is modeled in `types/room.ts` and handled by the reducer per `DESIGN.md`'s documented shape, even though `backend/app/rooms_ws.py` never actually emits it today — every invalid `submit_answer` case (wrong status, already answered, wrong round, late arrival) currently just silently `return`s server-side with no broadcast. So this branch is dead code against the current backend; kept for parity with the documented protocol and in case the backend starts sending it later. Until then, a rejected submission (e.g. a late Select-All Submit) simply has no visible effect in the UI.
- **No reconnect logic.** A dropped connection surfaces as `connection state: closed`; the page shows a static "disconnected" panel. This is a frontend engineering choice, not something `requirements.md` mandates — that doc's "no reconnect flow" scope cut is specifically about a Player who disconnects mid-game being unable to *rejoin* (enforced server-side via `already_started` at the join endpoint, a business rule). This spec's choice not to auto-retry the WS connection on an unexpected drop, for either role, at any phase, is a separate and broader decision, made for build-simplicity reasons — not derived from that requirements.md line.
- WS close codes aren't distinguished in the UI: a `4403`/`4404` close (host cookie mismatch, room not found — shouldn't occur in the normal flow, since `HostPage`/`PlayerPage` only connect right after a successful create/join) renders the same generic "disconnected" panel as a plain network drop.
- **No page-reload recovery.** The backend has no full-`RoomState` snapshot message — a fresh WS connection only receives *future* broadcasts, never past ones. A Host or Player who reloads `/host/:pin` or `/play/:pin` mid-game gets a blank/stuck state. Accepted as a known limitation for this build (see Known limitations below) — no backend changes made to support this.

## Components

- `/` — `FlashcardView` (existing) + new "Create Room" button/handler
- `/host/:pin` — `HostPage` (owns `useRoomSocket(role: "host")`, renders one panel per phase):
  - `LobbyPanel` — PIN display, `<QRCodeSVG>`, live roster list, "Start Game" button (`send({type: "advance"})`)
  - `QuestionActivePanel` — round progress (`round`/`total_rounds`), live answered-count ping, no answer input (Host doesn't answer)
  - `LeaderboardPanel` — shown once the `leaderboard` message arrives (reveal-then-leaderboard happens server-side in immediate succession with no Host action between, so Host UI doesn't get a separate reveal screen); ranked standings, "Next Question" (or "Finish" when `is_final`) and "End Game" buttons
  - `FinishedPanel` — final standings, `reason`
- `/join/:pin` — `JoinPage`: on mount, calls `GET /rooms/{pin}` (per `DESIGN.md`'s API contract, which documents this endpoint's purpose as exactly this pre-check). `room_not_found`, `status: "finished"`, or `status: "in_progress"` (join window already closed — `_PUBLIC_STATUS` collapses `question_active`/`answer_reveal`/`leaderboard` all into `in_progress`, all equally "too late to join") render `RoomErrorPanel` immediately, before showing the form; a `"lobby"` status with `player_count >= 10` also renders it early (`room_full`, computed client-side from the returned count — the endpoint doesn't return a dedicated full flag). Otherwise shows the nickname form. `POST /rooms/{pin}/join`'s own 404/409 responses stay as the authoritative fallback (e.g. a room that fills up in the gap between the pre-check and submit) — the pre-check only improves the common case, it doesn't replace error handling on submit. PIN from route param, nickname field, submit → `POST /rooms/{pin}/join` → navigate to `/play/:pin?player_id=...`
- `/play/:pin` — `PlayerPage` (owns `useRoomSocket(role: "player", playerId)`, renders one panel per phase):
  - `WaitingPanel` — lobby, "waiting for host to start"
  - `QuestionPanel` — live question + 4 options; Multiple-Choice taps send immediately, Select-All accumulates local selection with a Submit button; locks after submit, shows "waiting for others"
  - `RevealPanel` — own correct/incorrect, points earned, explanation (from `answer_reveal.results[player_id]`)
  - `LeaderboardPanel` — own rank + full standings
  - `FinishedPanel` — final standings
- Shared `RoomErrorPanel` — used by `JoinPage` (inline, for `room_full`/`already_started`) and by `HostPage`/`PlayerPage` (full-page, for `room_not_found` — e.g. a TTL-evicted PIN) with a link back to `/`

## File structure

New `src/room/` directory:
```
src/room/
  HostPage.tsx
  PlayerPage.tsx
  JoinPage.tsx
  useRoomSocket.ts
  panels/
    LobbyPanel.tsx / .module.css
    QuestionActivePanel.tsx / .module.css
    LeaderboardPanel.tsx / .module.css
    FinishedPanel.tsx / .module.css
    WaitingPanel.tsx / .module.css
    QuestionPanel.tsx / .module.css
    RevealPanel.tsx / .module.css
    RoomErrorPanel.tsx / .module.css
  lib/
    joinUrl.ts          # builds {origin}/join/{pin}
    roomSocketReducer.ts # pure reducer, unit-tested separately from the hook
  types/
    room.ts             # WS message types (mirrors DESIGN.md's protocol), RoomSocketState
```

Existing `src/components/`, `src/lib/`, `src/fixtures/`, `src/types/question.ts` are untouched except `src/App.tsx`, which gains the router and the "Create Room" button/handler.

## Testing

- `roomSocketReducer` and `joinUrl` get Vitest unit tests, same pattern as existing `src/lib/*.test.ts` (pure-function tests, no component/network mocking)
- No mocked-WebSocket integration tests — the real-time flow is manually smoke-tested live (backend `uvicorn` + frontend `vite dev`, multiple browser tabs simulating Host + Players), same approach `PROGRESS.md` records for the backend build
- `tsc --noEmit` and `oxlint` clean, same bar as existing code

## Error handling

- `room_not_found` (404) on `/host/:pin`, `/join/:pin`, or `/play/:pin` → `RoomErrorPanel`, link back to `/`
- `room_full` / `already_started` (409) on join → inline error on `JoinPage`, form stays open
- Unexpected WS close → static "disconnected" panel (see WebSocket wiring's no-reconnect note)
- Host disconnects → Players receive `game_over` (`reason: "host_disconnected"`) same as any other end-of-game, rendered by the same `FinishedPanel`

## Known limitations (explicitly accepted, not bugs to fix in this build)

- No page-reload / resume support mid-game for either role (see WebSocket wiring above) — closes over an implementation-level gap in the already-built backend (no state-snapshot-on-connect message) without touching backend code, since this session's build is frontend-only and the gap doesn't block the described flows as long as the page isn't reloaded.
- No WS auto-reconnect, for either role, at any phase — a frontend build-simplicity choice, not something any of the 4 architectural docs mandates (see WebSocket wiring above for the distinction from `requirements.md`'s narrower Player-rejoin cut).
- Room creation still uses the one hardcoded fixture, not a real generated Question Set, and there's no real hub screen — both already documented as deferred in `DESIGN.md`.
