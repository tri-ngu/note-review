# Agent Test Log

Isolated per-call test runs for the Analyzer, Generator (initial + patch), and Verifier — `agent-testing` branch, before pipeline wiring. Test inputs are handwritten (`test_inputs.py`), grounded in `water_cycle_note.txt` / `fixture_questions.json`. Expected behavior contracts live in `DESIGN.md`'s Expected behavior section.

Each entry: run time, agent + call type, input, expected output, actual output, notes (parse/validation result, contract match, anything surprising). Full detail below the summary table; two prompt fixes (Generator-patch `source_quote` grounding, Verifier `is_select_all` count-inference) were applied mid-session and re-verified against the affected cases only — see the two "Fix verification" sections.

**Next phase**: agents wire together into the real pipeline (Analyzer → checkpoint → Generator → verify loop → Freeze) for a full live end-to-end run, no longer isolated single-call tests. This log's isolated-call results stand as the pre-wiring baseline.

## Summary

| # | Agent | Call | Label | Time | Duration | Result | Notes |
|---|-------|------|-------|------|----------|--------|-------|
| 1 | Analyzer | — | `analyzer-full-note` | 12:25:32 | 5.3s | PASS | 8 concepts, weight sum 100.00, all snippets verbatim |
| 2 | Analyzer | — | `analyzer-sparse-note` | 12:25:37 | 2.6s | PASS | 3 narrow concepts, no invented content |
| 3 | Generator | initial | `generator-initial-evaporation` | 12:25:40 | 2.4s | PASS | 3/3 questions, source_quote grounded in snippets |
| 4 | Generator | initial | `generator-initial-runoff` | 12:25:42 | 12.0s | PASS | 2/2 questions, source_quote grounded |
| 5 | Generator | initial | `generator-initial-thin-snippet-overask` | 12:25:54 | 4.9s | PASS | 4/4 questions from 1 thin snippet, varied not fabricated |
| 6 | Generator | patch | `generator-patch-precipitation-forms` | 12:25:59 | 28.7s | FAIL → fixed | source_quote stayed on pre-fix quote, not fix snippet |
| 6b | Generator | patch | `generator-patch-precipitation-forms` (re-run) | 12:42:52 | 2.6s | PASS | Fix applied — source_quote now grounded in fix snippet |
| 7 | Generator | patch | `generator-patch-two-flagged-same-concept` | 12:26:28 | 12.1s | FAIL → fixed | Same source_quote issue, both indices |
| 7b | Generator | patch | `generator-patch-two-flagged-same-concept` (re-run) | 12:42:55 | 4.6s | PASS | Fix applied — both source_quotes now grounded |
| 8 | Verifier | — | `verifier-evaporation-mixed` | 12:26:40 | 24.6s | PASS | 5/5 keep/patch verdicts matched expectation |
| 9 | Verifier | — | `verifier-condensation-mixed` | 12:27:05 | 29.4s | PASS* | 4/5 matched; index 2 "mismatch" — see 9b |
| 9b | Verifier | — | `verifier-condensation-mixed` (re-run, idx 2) | 12:48:37 | 4.3s | PASS | Confirms index 2's patch flag is correct, not a bug — test oracle fixed |
| 10 | Verifier | — | `verifier-runoff-mixed` | 12:27:34 | 17.8s | PASS | 4/4 keep/patch verdicts matched expectation |

**Overall**: 10/10 calls parsed and validated structurally; 2 real issues found and fixed mid-session (Generator-patch grounding, Verifier is_select_all guidance), both confirmed resolved by targeted re-runs; 1 apparent mismatch turned out to be a wrong test expectation, corrected in `test_inputs.py`.

---

## Run 2026-08-10T12:25:32

### Analyzer — `analyzer-full-note`

- **Time**: 2026-08-10T12:25:32 (5.3s)
- **Input**: note_text (4133 chars)
- **Expected**: weights sum to ~100 (±10), non-overlapping Concepts, all snippets verbatim substrings — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
concept: "Water cycle overview"
weight_percentage: 8.00
snippets: ["The water cycle, also called the hydrologic cycle, describes the continuous movement of water on, above, and below the surface of the Earth." : 1],
          ["Water is neither created nor destroyed in this process — it simply changes form and location, moving between the atmosphere, land, and oceans in a repeating cycle driven by solar energy and gravity." : 1]

concept: "Evaporation"
weight_percentage: 15.00
snippets: ["Evaporation is the process by which liquid water changes into water vapor and rises into the atmosphere. The sun's heat provides the energy needed for evaporation, primarily from oceans, lakes, and rivers, which together account for the vast majority of water entering the atmosphere." : 1],
          ["Approximately 90 percent of the moisture in the atmosphere comes from evaporation off the surface of oceans, with the remaining 10 percent contributed by other sources such as lakes, rivers, and transpiration." : 1]

concept: "Transpiration and evapotranspiration"
weight_percentage: 12.00
snippets: ["Transpiration is a related but distinct process in which plants release water vapor from their leaves into the atmosphere." : 1],
          ["Because evaporation and transpiration are difficult to measure separately in vegetated areas, scientists often combine them into a single term: evapotranspiration." : 1]

concept: "Condensation and cloud formation"
weight_percentage: 10.00
snippets: ["Condensation is the process by which water vapor cools and changes back into liquid water droplets." : 2],
          ["These droplets gather around tiny particles of dust, salt, or smoke in the air, forming clouds." : 2]

concept: "Precipitation amount and forms"
weight_percentage: 14.00
snippets: ["On average, the Earth receives about 505,000 cubic kilometers of precipitation each year, roughly 78 percent of which falls over the oceans and the remaining 22 percent over land." : 2],
          ["Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail." : 3],
          ["Rain is the most common form of precipitation in warmer climates, while snow and sleet occur when temperatures near the ground are at or below freezing." : 3],
          ["Hail forms when strong updrafts within storm clouds carry water droplets through freezing layers of air multiple times before they fall." : 3]

concept: "Surface runoff"
weight_percentage: 10.00
snippets: ["Surface runoff occurs when water flows over the land's surface into streams, rivers, and eventually back into oceans or lakes, completing the visible portion of the cycle." : 1]

concept: "Infiltration, groundwater, and aquifers"
weight_percentage: 18.00
snippets: ["Infiltration is the process by which water soaks into the ground, moving through soil and rock layers to become groundwater." : 3],
          ["Groundwater is stored in underground formations called aquifers, which can hold water for long periods of time — in some cases, thousands of years." : 3],
          ["Groundwater also feeds into rivers and lakes during dry periods when surface runoff is minimal, helping to sustain ecosystems and water supplies between rainfalls." : 3]

concept: "Collection as the cycle’s closing stage"
weight_percentage: 13.00
snippets: ["Collection refers broadly to the accumulation of water in oceans, lakes, rivers, and groundwater reservoirs, where it will eventually evaporate again and restart the cycle." : 3],
          ["Because the water cycle has no true beginning or end, collection is often considered the closing stage of one cycle and the starting point of the next, as accumulated water is once again exposed to solar energy and begins to evaporate." : 3]
--END--
```
- **Notes**: Parsed OK: 8 concepts, weight sum = 100.00; Concepts: Water cycle overview, Evaporation, Transpiration and evapotranspiration, Condensation and cloud formation, Precipitation amount and forms, Surface runoff, Infiltration, groundwater, and aquifers, Collection as the cycle’s closing stage

### Analyzer — `analyzer-sparse-note`

- **Time**: 2026-08-10T12:25:37 (2.6s)
- **Input**: note_text (214 chars)
- **Expected**: weights sum to ~100 (±10), non-overlapping Concepts, all snippets verbatim substrings — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
concept: "Overall photosynthesis process"
weight_percentage: 60.00
snippets: ["Photosynthesis is the process by which green plants use sunlight to synthesize food from carbon dioxide and water." : 1]

concept: "Chlorophyll role in photosynthesis"
weight_percentage: 20.00
snippets: ["It generally involves the green pigment chlorophyll" : 1]

concept: "Oxygen as byproduct"
weight_percentage: 20.00
snippets: ["generates oxygen as a byproduct." : 1]
--END--
```
- **Notes**: Parsed OK: 3 concepts, weight sum = 100.00; Concepts: Overall photosynthesis process, Chlorophyll role in photosynthesis, Oxygen as byproduct

### Generator (initial pass) — `generator-initial-evaporation`

- **Time**: 2026-08-10T12:25:40 (2.4s)
- **Input**: concept='Evaporation and Transpiration', question_count=3, snippets=["The sun's heat provides the energy needed for evaporation, p...", 'Because evaporation and transpiration are difficult to measu...']
- **Expected**: exactly 3 Questions, each with source_quote an exact substring of a given snippet — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
question_text: "What provides the energy needed for evaporation?"
options: ["The sun's heat", "Moon's gravity", "Wind speed", "Atmospheric pressure"]
correct_answers: [1]
is_select_all: false
explanation: "The sun's heat provides the energy needed for evaporation."
page_number: 1
source_quote: "The sun's heat provides the energy needed for evaporation"

question_text: "Which of the following water bodies are cited as the primary sources of water entering the atmosphere through evaporation? (Select all that apply)"
options: ["Oceans", "Lakes", "Rivers", "Groundwater"]
correct_answers: [1, 2, 3]
is_select_all: true
explanation: "Evaporation occurs primarily from oceans, lakes, and rivers, which together account for the vast majority of water entering the atmosphere."
page_number: 1
source_quote: "primarily from oceans, lakes, and rivers"

question_text: "Why do scientists often combine evaporation and transpiration into the term evapotranspiration?"
options: ["Because evaporation and transpiration are difficult to measure separately", "Because they occur simultaneously in all ecosystems", "Because they involve the same chemical reactions", "Because they both create clouds"]
correct_answers: [1]
is_select_all: false
explanation: "Because evaporation and transpiration are difficult to measure separately, scientists often combine them into a single term: evapotranspiration."
page_number: 1
source_quote: "Because evaporation and transpiration are difficult to measure separately"
--END--
```
- **Notes**: Parsed OK: 3 Questions (requested 3)

### Generator (initial pass) — `generator-initial-runoff`

- **Time**: 2026-08-10T12:25:42 (12.0s)
- **Input**: concept='Runoff and Groundwater Storage', question_count=2, snippets=['Runoff is the primary way that liquid water returns to bodie...', 'Groundwater is stored in underground formations called aquif...']
- **Expected**: exactly 2 Questions, each with source_quote an exact substring of a given snippet — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
question_text: "What is the primary way that liquid water returns to bodies of water?"
options: ["Runoff", "Infiltration", "Evaporation", "Transpiration"]
correct_answers: [1]
is_select_all: false
explanation: "Runoff is described as the primary way that liquid water returns to bodies of water."
page_number: 1
source_quote: "Runoff is the primary way that liquid water returns to bodies of water, and it can carry sediment, nutrients, and pollutants along with it as it moves downhill."

question_text: "In what type of underground formation is groundwater stored for long periods, sometimes thousands of years?"
options: ["Aquifers", "Caverns", "Fault zones", "Sedimentary basins"]
correct_answers: [1]
is_select_all: false
explanation: "Groundwater is stored in underground formations called aquifers, which can hold water for long periods of time — in some cases, thousands of years."
page_number: 3
source_quote: "Groundwater is stored in underground formations called aquifers, which can hold water for long periods of time — in some cases, thousands of years."
--END--
```
- **Notes**: Parsed OK: 2 Questions (requested 2)

### Generator (initial pass) — `generator-initial-thin-snippet-overask`

- **Time**: 2026-08-10T12:25:54 (4.9s)
- **Input**: concept='Water Cycle Overview', question_count=4, snippets=['The water cycle, also called the hydrologic cycle, describes...']
- **Expected**: exactly 4 Questions, each with source_quote an exact substring of a given snippet — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
question_text: "What does the water cycle (also called the hydrologic cycle) describe?"
options: ["The continuous movement of water on, above, and below the surface of the Earth", "The formation of rocks and minerals", "The process of photosynthesis in plants", "The migration patterns of animals across continents"]
correct_answers: [1]
is_select_all: false
explanation: "The water cycle, also called the hydrologic cycle, describes the continuous movement of water on, above, and below the surface of the Earth."
page_number: 1
source_quote: "describes the continuous movement of water on, above, and below the surface of the Earth"

question_text: "According to the water cycle, what happens to the total amount of water on Earth?"
options: ["It is created by solar energy", "It is destroyed during precipitation", "It remains constant because water is neither created nor destroyed", "It steadily increases each year"]
correct_answers: [3]
is_select_all: false
explanation: "Water is neither created nor destroyed in this process — it simply changes form and location."
page_number: 1
source_quote: "Water is neither created nor destroyed in this process — it simply changes form and location"

question_text: "Which forces drive the repeating movement of water in the water cycle?"
options: ["Solar energy and gravity", "Magnetic fields and wind", "Tidal forces only", "Atmospheric pressure alone"]
correct_answers: [1]
is_select_all: false
explanation: "The cycle is a repeating cycle driven by solar energy and gravity."
page_number: 1
source_quote: "in a repeating cycle driven by solar energy and gravity"

question_text: "Between which major reservoirs does water move during the water cycle?"
options: ["Atmosphere, land, and oceans", "Crust, mantle, and core", "Rivers, lakes, and glaciers only", "Soil, plants, and insects"]
correct_answers: [1]
is_select_all: false
explanation: "Water moves between the atmosphere, land, and oceans as part of the cycle."
page_number: 1
source_quote: "moving between the atmosphere, land, and oceans"
--END--
```
- **Notes**: Parsed OK: 4 Questions (requested 4)

### Generator (patch pass) — `generator-patch-precipitation-forms`

- **Time**: 2026-08-10T12:25:59 (28.7s)
- **Input**: concept='Condensation and Precipitation: forms and process', flagged indices=[4]
- **Expected**: output contains exactly the flagged indices, each once; new source_quote grounded in the *fix* snippets, not the original — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
index: 4
question_text: "Which of the following are forms precipitation can take?"
options: ["Rain", "Snow", "Sleet", "Hail"]
correct_answers: [1, 2, 3, 4]
is_select_all: true
explanation: "Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail. Rain is the most common form of precipitation in warmer climates, while snow and sleet occur when temperatures near the ground are at or below freezing."
page_number: 3
source_quote: "Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail."
--END--
```
- **Notes**: Parsed OK: returned indices [4] (expected [4]); CONTRACT VIOLATION (index 4): source_quote not a substring of the new fix snippets — 'Precipitation can take several forms depending on atmospheric temperature: rain,'

### Generator (patch pass) — `generator-patch-two-flagged-same-concept`

- **Time**: 2026-08-10T12:26:28 (12.1s)
- **Input**: concept='Runoff and Groundwater Storage', flagged indices=[7, 8]
- **Expected**: output contains exactly the flagged indices, each once; new source_quote grounded in the *fix* snippets, not the original — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
index: 7
question_text: "According to the Note, which underground formation stores groundwater for long periods and can slowly release it to rivers and lakes during dry periods?"
options: ["Aquifers", "Water table", "Infiltration zone", "Saturated zone"]
correct_answers: [1]
is_select_all: false
explanation: "Groundwater is stored in underground formations called aquifers, which can hold water for long periods of time — in some cases, thousands of years — and which also feed into rivers and lakes during dry periods when surface runoff is minimal."
page_number: 3
source_quote: "Groundwater is stored in underground formations called aquifers, which can hold water for long periods of time — in some cases, thousands of years."

index: 8
question_text: "Select all statements that correctly describe surface runoff."
options: ["It occurs when water flows over land into streams and rivers", "It is the primary way that liquid water returns to bodies of water", "It can carry sediment, nutrients, and pollutants downhill", "It occurs primarily underground through aquifers"]
correct_answers: [1, 2, 3]
is_select_all: true
explanation: "Surface runoff occurs when water flows over the land's surface into streams, rivers, and eventually back into oceans or lakes, completing the visible portion of the cycle. It is the primary way that liquid water returns to bodies of water and can carry sediment, nutrients, and pollutants downhill."
page_number: 1
source_quote: "Runoff is the primary way that liquid water returns to bodies of water, and it can carry sediment, nutrients, and pollutants along with it as it moves downhill."
--END--
```
- **Notes**: Parsed OK: returned indices [7, 8] (expected [7, 8]); CONTRACT VIOLATION (index 7): source_quote not a substring of the new fix snippets — 'Groundwater is stored in underground formations called aquifers, which can hold '; CONTRACT VIOLATION (index 8): source_quote not a substring of the new fix snippets — 'Runoff is the primary way that liquid water returns to bodies of water, and it c'

### Verifier — `verifier-evaporation-mixed`

- **Time**: 2026-08-10T12:26:40 (24.6s)
- **Input**: concept='Evaporation and Transpiration', indices=[1, 2, 3, 4, 5] (expected actions: {1: 'keep', 2: 'keep', 3: 'keep', 4: 'patch', 5: 'patch'})
- **Expected**: happy-path indices -> keep, adversarial indices -> patch — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
index: 1
action: "keep"
critique: ""
snippets: []

index: 2
action: "keep"
critique: ""
snippets: []

index: 3
action: "keep"
critique: ""
snippets: []

index: 4
action: "patch"
critique: "source_quote is fabricated; the note does not contain the phrase about NASA satellite data. The quoted source must exactly match text on page 1."
snippets: ["Approximately 90 percent of the moisture in the atmosphere comes from evaporation off the surface of oceans" : 1]

index: 5
action: "patch"
critique: "The distractor \"The sun's warmth\" is virtually synonymous with the correct answer and creates ambiguity; the note only mentions \"sun's heat\". The question should avoid such near‑duplicate options."
snippets: ["The sun's heat provides the energy needed for evaporation, primarily from oceans, lakes, and rivers" : 1]

satisfactory: false
--END--
```
- **Notes**: Parsed OK: 5 verdicts, satisfactory=False; idx 1: expected=keep actual=keep [OK]; idx 2: expected=keep actual=keep [OK]; idx 3: expected=keep actual=keep [OK]; idx 4: expected=patch actual=patch [OK]; idx 5: expected=patch actual=patch [OK]

### Verifier — `verifier-condensation-mixed`

- **Time**: 2026-08-10T12:27:05 (29.4s)
- **Input**: concept='Condensation and Precipitation: forms and process', indices=[1, 2, 3, 4, 5] (expected actions: {1: 'keep', 2: 'keep', 3: 'keep', 4: 'patch', 5: 'patch'})
- **Expected**: happy-path indices -> keep, adversarial indices -> patch — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
index: 1
action: "keep"
critique: ""
snippets: []

index: 2
action: "patch"
critique: "is_select_all is set to true even though only one option (Condensation) is correct; for a single‑answer question it should be false."
snippets: ["Condensation is essentially the reverse of evaporation, and it is the process responsible for the formation of clouds and fog." : 2]

index: 3
action: "keep"
critique: ""
snippets: []

index: 4
action: "patch"
critique: "source_quote is assigned to page 3, but the quoted sentence appears on page 2 in the note."
snippets: ["Condensation is essentially the reverse of evaporation, and it is the process responsible for the formation of clouds and fog." : 2]

index: 5
action: "patch"
critique: "The question asks for all forms precipitation can take, yet only 'Rain' is marked correct and is_select_all is false; this makes the answer incorrect and the question ambiguous."
snippets: ["Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail." : 3]

satisfactory: false
--END--
```
- **Notes**: Parsed OK: 5 verdicts, satisfactory=False; idx 1: expected=keep actual=keep [OK]; idx 2: expected=keep actual=patch [MISMATCH — resolved, see Fix verification below]; idx 3: expected=keep actual=keep [OK]; idx 4: expected=patch actual=patch [OK]; idx 5: expected=patch actual=patch [OK]

### Verifier — `verifier-runoff-mixed`

- **Time**: 2026-08-10T12:27:34 (17.8s)
- **Input**: concept='Runoff and Groundwater Storage', indices=[1, 2, 3, 4] (expected actions: {1: 'keep', 2: 'keep', 3: 'patch', 4: 'patch'})
- **Expected**: happy-path indices -> keep, adversarial indices -> patch — see DESIGN.md Expected behavior
- **Actual output**:
```
--START--
index: 1
action: "keep"
critique: ""
snippets: []

index: 2
action: "keep"
critique: ""
snippets: []

index: 3
action: "patch"
critique: "The question concerns transpiration, which is unrelated to the assigned concept 'Runoff and Groundwater Storage'."
snippets: ["Transpiration is a related but distinct process in which plants release water vapor from their leaves into the atmosphere." : 1]

index: 4
action: "patch"
critique: "The question addresses evaporation, not the concept 'Runoff and Groundwater Storage'."
snippets: ["Warmer temperatures increase the rate of evaporation, which is why evaporation is fastest in tropical regions and during summer months." : 1]

satisfactory: false
--END--
```
- **Notes**: Parsed OK: 4 verdicts, satisfactory=False; idx 1: expected=keep actual=keep [OK]; idx 2: expected=keep actual=keep [OK]; idx 3: expected=patch actual=patch [OK]; idx 4: expected=patch actual=patch [OK]

### Findings summary (this run)

- **Analyzer**: both cases parsed clean, weights summed exactly to 100, all snippets verbatim. Full-note case produced 8 non-overlapping Concepts spanning all 3 pages (within the Expected-behavior range); sparse-note case correctly produced only 3 narrow Concepts without inventing content. No violations.
- **Generator (initial)**: all 3 cases produced exactly the requested count, every `source_quote` grounded in a given snippet. The thin-snippet-overask case (4 Questions from 1 short snippet) varied phrasing/angle per question rather than repeating or fabricating — matches the Expected-behavior contract.
- **Generator (patch) — reproducible issue (3/3 patched Questions)**: every patched Question's `source_quote` was left as the *original* (pre-flag) quote rather than grounded in the newly-provided fix snippet, even though the critique itself was otherwise addressed (e.g. index 4's explanation did pull in the fix-snippet detail). Suspect cause: the flagged-question block shown to the model includes the original `source_quote` as one of the "current Question fields" (per DESIGN.md's prompt format), sitting right next to the fix snippets — the model may be treating the original as still-valid grounding rather than treating it as superseded. **Fixed and re-verified — see Fix verification below.**
- **Verifier**: 4/5 flag-vs-expectation matches per case; one mismatch (`verifier-condensation-mixed` index 2) — flagged fixture's intentional "Select-All with only 1 correct" edge case as needing a patch (is_select_all/count mismatch). **Resolved — see Fix verification below**: the flag turned out to be a legitimate content-quality catch (question stem doesn't invite select-all framing), not a Verifier defect; the test oracle was wrong, not the agent. All fabricated-quote / wrong-page / mismatched-concept / ambiguous-phrasing adversarial cases were caught correctly (5/5).

---

## Fix verification 2026-08-10T12:42:52 — Generator-patch source_quote grounding

Tri approved direction (a) from the Generator (patch) finding above: added an explicit prompt line stating the flagged Question's pre-fix `source_quote` is context-only and must not be reused unless it also appears in the new fix snippets (plus reworded the field bullet and quality-bar line the same way). Re-ran only the 2 Generator-patch cases against this revised prompt (same handwritten flags as before, `call_agent.py`'s `GENERATOR_PATCH_INSTRUCTIONS` edited, then copied into `DESIGN.md`'s canonical prompt block once confirmed working).

### Generator (patch pass) — `generator-patch-precipitation-forms` (re-run)

- **Time**: 2026-08-10T12:42:52 (2.6s)
- **Actual output**:
```
--START--
index: 4
question_text: "Which of the following are forms that precipitation can take according to temperature conditions?"
options: ["Rain", "Snow", "Sleet", "Hail"]
correct_answers: [1, 2, 3]
is_select_all: true
explanation: "Rain is the most common form of precipitation in warmer climates, while snow and sleet occur when temperatures near the ground are at or below freezing."
page_number: 3
source_quote: "Rain is the most common form of precipitation in warmer climates, while snow and sleet occur when temperatures near the ground are at or below freezing."
--END--
```
- **Notes**: Parsed OK, returned indices [4] as expected. `source_quote` now correctly grounded in the fix snippet (was the stale original before the fix). Side effect: `correct_answers` narrowed from `[1,2,3,4]` to `[1,2,3]` — Hail dropped, because the handwritten fix snippet for this test only covered rain/snow/sleet's temperature explanation, not hail. Expected consequence of "use only the fix snippets" now actually being followed — correctness of the patch is bounded by fix-snippet completeness, which is the real Verifier's job to get right, not a flaw in this fix itself.

### Generator (patch pass) — `generator-patch-two-flagged-same-concept` (re-run)

- **Time**: 2026-08-10T12:42:55 (4.6s)
- **Actual output**:
```
--START--
index: 7
question_text: "Which process describes water soaking into the ground and moving through soil and rock layers to become groundwater?"
options: ["Infiltration", "Evaporation", "Condensation", "Transpiration"]
correct_answers: [1]
is_select_all: false
explanation: "Infiltration is the process by which water soaks into the ground, moving through soil and rock layers to become groundwater."
page_number: 3
source_quote: "Infiltration is the process by which water soaks into the ground, moving through soil and rock layers to become groundwater."

index: 8
question_text: "Which statement best describes surface runoff?"
options: ["It occurs when water flows over the land's surface into streams, rivers, and eventually back into oceans or lakes.", "It is the process by which water evaporates directly from soil into the atmosphere.", "It describes the movement of water through underground fractures into aquifers.", "It refers to water being absorbed by plant roots and released as vapor."]
correct_answers: [1]
is_select_all: false
explanation: "Surface runoff occurs when water flows over the land's surface into streams, rivers, and eventually back into oceans or lakes, completing the visible portion of the cycle."
page_number: 1
source_quote: "Surface runoff occurs when water flows over the land's surface into streams, rivers, and eventually back into oceans or lakes, completing the visible portion of the cycle."
--END--
```
- **Notes**: Parsed OK, returned indices [7, 8] as expected. Both `source_quote`s now correctly grounded in their respective fix snippets. 0/3 contract violations across both re-run cases (was 3/3 pre-fix).

---

## Fix verification 2026-08-10T12:48:37 — Verifier is_select_all count-inference guidance

Tri approved tightening the Verifier's `is_select_all` quality-bar bullet: made explicit that `is_select_all: true` legitimately covers 1-4 correct answers, and the Verifier should only flag it on an actual phrasing/framing mismatch — never purely because `len(correct_answers) == 1`. Re-ran only `verifier-condensation-mixed` (the case that originally mismatched on index 2) against the revised prompt.

### Verifier — `verifier-condensation-mixed` (re-run, index 2 only relevant)

- **Time**: 2026-08-10T12:48:37 (4.3s)
- **Actual output** (index 2 excerpt):
```
index: 2
action: "patch"
critique: "is_select_all is true but the question wording ("Which process is described as essentially the reverse of evaporation?") invites a single answer; it should be false."
snippets: ["Condensation is essentially the reverse of evaporation, and it is the process responsible for the formation of clouds and fog." : 2]
```
- **Notes**: Still `action: "patch"` for index 2 — but the critique's *reasoning* changed from count-inference ("only one option correct, so is_select_all should be false") to phrasing-based ("question wording invites a single answer"), which is exactly the legitimate criterion the tightened guidance was meant to preserve rather than suppress. This confirms the original `expected: keep` for this test case in `test_inputs.py` was the wrong expectation, not a Verifier defect — the fixture's phrasing genuinely doesn't sell select-all framing, matching hypothesis (b) from the original finding. `test_inputs.py`'s `expected_actions` for this case corrected (index 2: `keep` → `patch`). Guidance change copied into `DESIGN.md`'s Agent prompts (Verifier quality bar) and Verify loop detail sections (kept verbatim-identical per that section's own note).

---
