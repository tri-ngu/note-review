# Game Room manual test — remaining flags (2026-08-11)

Manual test session ran against `game-room-build` clone
(`C:\Users\billn\OneDrive\Documents\zps\bai tap 4\game-room-build`, own `.git`,
backend on `localhost:8000`, frontend on `localhost:5173`, proxy already wired
in `frontend/vite.config.ts`). Full checklist was run interactively with Tri,
flag-by-flag. This session (background job, worktree-isolated to `agent-testing`)
could not write directly to `game-room-build` — that's a separate clone, not a
worktree of this repo, so `EnterWorktree`/`Edit` both refuse it. Next session
should run as a normal foreground session with cwd set inside `game-room-build`
directly, no relay needed.

## Done

- **Flag #2 — No "Join Room" entry point on home page** (was high priority).
  Fixed and verified working by Tri. `/join` route added (PIN-entry form,
  reuses `JoinPage` component when no `:pin` param), "Join Room" button added
  to home page next to "Create Room" (`FlashcardView.tsx`). DESIGN.md's
  "Frontend routing" paragraph updated in `main` by Tri directly (this session
  couldn't write to main's DESIGN.md either — same worktree-isolation issue).

## Remaining flags, priority order

### High priority

**Flag #5 — Answer reveal not shown on either Host or Player**
Round ends and jumps straight to Leaderboard on both sides — `RevealPanel`
component exists in the codebase (`frontend/src/room/panels/RevealPanel.tsx`)
but isn't being rendered/wired into the phase flow. Leaderboard's point totals
ARE correct, so this is a display-wiring bug, not a scoring bug.

Confirmed desired behavior (Tri, 2026-08-11):
- **Host**: Leaderboard panel should show the answer reveal (correct_answers +
  explanation) merged in at the top, per DESIGN.md's existing note that Host's
  screen "collapses ANSWER_REVEAL directly into its LEADERBOARD-phase panel."
  That merge was documented but apparently never actually implemented in the
  Host panel-switch logic.
- **Player**: should get its own distinct reveal screen (their answer vs.
  correct answer, plus explanation) before the leaderboard, using the existing
  `RevealPanel` component.

Needs investigation in `HostPage.tsx` / `PlayerPage.tsx` / the panel-switch
logic keyed on `RoomState.status` — likely `answer_reveal` status is either
not a recognized case in the switch, or falls through to leaderboard
immediately. Check `roomSocketReducer.ts` too for whether the `answer_reveal`
message is even being captured into state correctly.

**Flag #7 — Duplicate WS connection on same `player_id` breaks game progression**
Opening a second `/play/:pin?player_id=X` tab for an already-connected Player:
old tab stops responding to further server messages, new tab shows stale
default state ("waiting for host to start"), and Host gets stuck unable to
progress the round until the 30s timer forces it through. Reproduced
intentionally by Tri (copy-pasted the exact player URL into a new tab).

Not covered by any documented deferred item in DESIGN.md — genuine gap.
Needs server-side decision in `rooms_ws.py`: either reject a second WS
connection for a `player_id` that already has an active connection, or
accept it and cleanly close/replace the old socket (check how the per-player
socket registry is currently keyed — likely a dict overwrite is silently
orphaning the old connection without closing it, which is why the old tab
goes silent instead of erroring).

### Low priority (but needed — Tri's explicit call)

**Flag #1 — Intermittent "Disconnected — lost connection to room" after join**
Likely explained by a console error caught later in testing:
`useRoomSocket.ts:30 WebSocket connection to 'ws://localhost:5173/ws/room/7476'
failed: WebSocket is closed before the connection is established.` — classic
symptom of React `StrictMode` double-invoking `useEffect` in dev (confirmed
`main.tsx` wraps `<App />` in `<StrictMode>`), which opens then immediately
closes the first socket before the second (real) one connects. Likely a
dev-mode-only artifact, not a prod bug — Tri wants it rechecked after Vercel
deploy before concluding it's purely a StrictMode issue. If it needs a real
fix: standard pattern is guarding the WS-open effect against the
StrictMode double-invoke (e.g. a mount-ref guard, or only closing on true
unmount) in `useRoomSocket.ts`.

**Flag #3 — No visible question countdown timer**
`Question.question_start`/`server_time` field exists in the message type and
reducer (`types/room.ts`, `roomSocketReducer.test.ts`) but nothing renders a
countdown anywhere in the frontend — checked `QuestionActivePanel.tsx` and
found no timer UI at all. DESIGN.md's Room answer submission section implies
one should exist ("Client-side countdowns are purely cosmetic UI, not
consulted for scoring") — cosmetic only, client computes remaining time from
`server_time` + local clock, not authoritative. Needs a simple countdown
component added to `QuestionActivePanel` (and Host's mirrored view if it has
one), counting down from 30s based on the broadcast `server_time`.

**Flag #4 — Host reload after Room ended shows stale Lobby, not "room not found"**
Host tab reload closes the WS, which correctly triggers the documented
Host-disconnect short-circuit (Room → FINISHED immediately server-side, no
grace period — working as designed). But the reloaded Host tab's UI doesn't
reflect that — no reconnect/resume exists (documented deferred item,
"Reload/resume mid-game" in DESIGN.md), so it just renders default/Lobby-like
state instead of anything indicating the Room ended.

Tri's explicit desired behavior: `/host/:pin` should show "room not found" /
an ended-state screen for ANY reason the Room is no longer live (natural end,
host-triggered end, host-disconnect, TTL eviction) — not resume, just fail
gracefully. Likely fix: have `HostPage.tsx` do a `GET /rooms/{pin}` precheck
on mount (same pattern `JoinPage.tsx` already uses) before/alongside opening
the WS, and render `RoomErrorPanel` if `status: "finished"` or 404.

**Flag #6 — Last-round Leaderboard should only show "Finish", not "Next Question"**
On the leaderboard after the final question (`round == N`), Host currently
sees both "Next Question" and "Finish" (per earlier PROGRESS.md notes) —
should only show "Finish". Pure UI/conditional-render fix in whichever
component renders Host's Leaderboard controls (`LeaderboardPanel.tsx` or
`HostPage.tsx`) — check `round === total_rounds` (or equivalent) and hide/omit
the "Next Question" button in that case.

## Process notes for next session

- Confirm each fix individually with Tri before implementing (established
  pattern this session) — propose the approach, wait for feedback, then code.
- Don't touch `CONTEXT.md`/`DESIGN.md`/`PROGRESS.md`/`requirements.md` in
  `main` without confirming the exact edit each time; `progress.md` update
  for this whole manual-test pass is still owed at the very end, once all
  flags are resolved (per Tri's original instruction for this session).
- This file (`GAME-ROOM-MANUAL-TEST-FLAGS.md`) is scratch/temporary — delete
  it once all flags are resolved and folded into `PROGRESS.md`, don't let it
  become a permanent doc.
