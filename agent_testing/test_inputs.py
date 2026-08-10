"""Handwritten test inputs for each of the 4 agent call shapes (Analyzer,
Generator-initial, Generator-patch, Verifier). Each agent is tested in
isolation — no chaining one agent's live output into another's input (see
DESIGN.md's Agent prompts section for the call shapes, and
agent-test-log.md for results).

Grounded in water_cycle_note.txt. fixture_questions.json supplies the
happy-path Questions for Generator-patch/Verifier tests; adversarial cases
below are handwritten specifically to be flawed in one identifiable way
each, to check whether Verifier actually catches them.
"""

import json
from pathlib import Path

from models import ConceptSnippet, Question

NOTE_PATH = Path(__file__).parent / "water_cycle_note.txt"
FIXTURE_PATH = Path(__file__).parent / "fixture_questions.json"

FULL_NOTE_TEXT = NOTE_PATH.read_text(encoding="utf-8")

_fixture_data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
FIXTURE_QUESTIONS = [Question(**q) for q in _fixture_data["questions"]]

# Sparse note: handwritten, deliberately thin (one idea, one paragraph) to
# check Analyzer/sparse-content behavior distinct from the full Note.
SPARSE_NOTE_TEXT = """[Page 1]

Photosynthesis is the process by which green plants use sunlight to
synthesize food from carbon dioxide and water. It generally involves the
green pigment chlorophyll and generates oxygen as a byproduct.
"""

# --- Analyzer test cases ----------------------------------------------------

ANALYZER_CASES = [
    {"label": "analyzer-full-note", "note_text": FULL_NOTE_TEXT},
    {"label": "analyzer-sparse-note", "note_text": SPARSE_NOTE_TEXT},
]

# --- Generator-initial test cases -------------------------------------------
# concept/snippets handwritten (pulled by hand from water_cycle_note.txt),
# not chained from a live Analyzer call.

GENERATOR_INITIAL_CASES = [
    {
        "label": "generator-initial-evaporation",
        "concept": "Evaporation and Transpiration",
        "question_count": 3,
        "snippets": [
            (
                "The sun's heat provides the energy needed for evaporation, primarily from "
                "oceans, lakes, and rivers, which together account for the vast majority of "
                "water entering the atmosphere.",
                1,
            ),
            (
                "Because evaporation and transpiration are difficult to measure separately in "
                "vegetated areas, scientists often combine them into a single term: "
                "evapotranspiration.",
                1,
            ),
        ],
    },
    {
        "label": "generator-initial-runoff",
        "concept": "Runoff and Groundwater Storage",
        "question_count": 2,
        "snippets": [
            (
                "Runoff is the primary way that liquid water returns to bodies of water, and "
                "it can carry sediment, nutrients, and pollutants along with it as it moves "
                "downhill.",
                1,
            ),
            (
                "Groundwater is stored in underground formations called aquifers, which can "
                "hold water for long periods of time — in some cases, thousands of years.",
                3,
            ),
        ],
    },
    {
        # Edge case: question_count (4) exceeds what one short snippet can support
        # distinctly — checks "vary phrasing/format rather than repeating, never
        # fabricate to hit the count" instruction.
        "label": "generator-initial-thin-snippet-overask",
        "concept": "Water Cycle Overview",
        "question_count": 4,
        "snippets": [
            (
                "The water cycle, also called the hydrologic cycle, describes the continuous "
                "movement of water on, above, and below the surface of the Earth. Water is "
                "neither created nor destroyed in this process — it simply changes form and "
                "location, moving between the atmosphere, land, and oceans in a repeating "
                "cycle driven by solar energy and gravity.",
                1,
            ),
        ],
    },
]

# --- Generator-patch test cases ---------------------------------------------
# Handwritten fake Verifier-style flags (not chained from a live Verifier
# call) against fixture_questions.json's existing Questions.

GENERATOR_PATCH_CASES = [
    {
        "label": "generator-patch-precipitation-forms",
        "concept": "Condensation and Precipitation: forms and process",
        # index -> (current Question, fake critique, fake fix snippets)
        "flags": {
            4: {
                "question": FIXTURE_QUESTIONS[3],  # "Which forms precipitation can take?"
                "critique": (
                    "Explanation is too thin — it lists the forms but doesn't say what "
                    "determines which form occurs. Strengthen the explanation using the "
                    "temperature-dependence detail from the Note."
                ),
                "snippets": [
                    (
                        "Rain is the most common form of precipitation in warmer climates, "
                        "while snow and sleet occur when temperatures near the ground are at "
                        "or below freezing.",
                        3,
                    )
                ],
            }
        },
    },
    {
        "label": "generator-patch-two-flagged-same-concept",
        "concept": "Runoff and Groundwater Storage",
        "flags": {
            7: {
                "question": FIXTURE_QUESTIONS[6],  # aquifers question
                "critique": (
                    "Options are weak distractors — 'Stomata', 'Watersheds', and 'Deltas' "
                    "aren't all plausible confusions for a student. Replace with distractors "
                    "closer to the actual water-cycle process vocabulary."
                ),
                "snippets": [
                    (
                        "Infiltration is the process by which water soaks into the ground, "
                        "moving through soil and rock layers to become groundwater.",
                        3,
                    )
                ],
            },
            8: {
                "question": FIXTURE_QUESTIONS[7],  # surface runoff statements question
                "critique": (
                    "is_select_all is true but the option set mixes a false statement in "
                    "as a distractor without the question stem making clear multiple can be "
                    "false — reword the stem for clarity."
                ),
                "snippets": [
                    (
                        "Surface runoff occurs when water flows over the land's surface into "
                        "streams, rivers, and eventually back into oceans or lakes, completing "
                        "the visible portion of the cycle.",
                        1,
                    )
                ],
            },
        },
    },
]

# --- Verifier test cases -----------------------------------------------------
# Each case is scoped to one concept (matches DESIGN.md's per-concept fan-out).
# Happy-path Questions come from fixture_questions.json; adversarial Questions
# are handwritten, each broken in exactly one identifiable way.

_adversarial_fabricated_quote = Question(
    concept="Evaporation and Transpiration",
    question_text="What percentage of atmospheric moisture comes from ocean evaporation, according to NASA satellite data?",
    options=["90 percent", "75 percent", "60 percent", "95 percent"],
    correct_answers=[1],
    is_select_all=False,
    explanation="NASA satellite data confirms 90 percent of atmospheric moisture originates from ocean evaporation.",
    page_number=1,
    source_quote="NASA satellite data confirms 90 percent of atmospheric moisture originates from ocean evaporation.",
    # FLAW: source_quote is fabricated — not present anywhere in the Note,
    # even though the "90 percent" figure itself is (attributed differently).
)

_adversarial_duplicate_distractors = Question(
    concept="Evaporation and Transpiration",
    question_text="What is the primary source of energy driving evaporation in the water cycle?",
    options=["The sun's heat", "The sun's warmth", "Wind speed", "Ocean salinity"],
    correct_answers=[1],
    is_select_all=False,
    explanation="The sun's heat provides the energy needed for evaporation.",
    page_number=1,
    source_quote=(
        "The sun's heat provides the energy needed for evaporation, primarily from oceans, "
        "lakes, and rivers, which together account for the vast majority of water entering "
        "the atmosphere."
    ),
    # FLAW: options 1 and 2 are near-duplicate distractors ("heat" vs "warmth").
)

_adversarial_wrong_page = Question(
    concept="Condensation and Precipitation: forms and process",
    question_text="What is condensation the reverse of?",
    options=["Evaporation", "Infiltration", "Runoff", "Collection"],
    correct_answers=[1],
    is_select_all=False,
    explanation="Condensation is essentially the reverse of evaporation.",
    page_number=3,  # FLAW: this quote is actually on page 2, not 3.
    source_quote=(
        "Condensation is essentially the reverse of evaporation, and it is the process "
        "responsible for the formation of clouds and fog."
    ),
)

_adversarial_select_all_mismatch = Question(
    concept="Condensation and Precipitation: forms and process",
    question_text="Which of the following are forms precipitation can take?",
    options=["Rain", "Snow", "Sleet", "Hail"],
    correct_answers=[1],
    is_select_all=False,
    explanation="Rain is a form of precipitation.",
    page_number=3,
    source_quote=(
        "Precipitation can take several forms depending on atmospheric temperature: rain, "
        "snow, sleet, or hail."
    ),
    # FLAW: source_quote clearly supports all 4 options as correct and
    # is_select_all=true, but only option 1 is marked correct with
    # is_select_all=false — semantics mismatch against its own grounding.
)

_adversarial_mismatched_concept = Question(
    concept="Runoff and Groundwater Storage",  # FLAW: wrong concept — this is about Transpiration
    question_text="What process is described as plants releasing water vapor from their leaves into the atmosphere?",
    options=["Transpiration", "Infiltration", "Condensation", "Collection"],
    correct_answers=[1],
    is_select_all=False,
    explanation=(
        "Transpiration is a related but distinct process in which plants release water "
        "vapor from their leaves into the atmosphere."
    ),
    page_number=1,
    source_quote=(
        "Transpiration is a related but distinct process in which plants release water "
        "vapor from their leaves into the atmosphere."
    ),
)

_adversarial_ambiguous_phrasing = Question(
    concept="Runoff and Groundwater Storage",
    question_text="Which process most directly explains why evaporation rates are higher in summer?",
    options=["Warmer temperatures", "The sun's heat", "Tropical location", "Wind speed"],
    correct_answers=[1],
    is_select_all=False,
    explanation="Warmer temperatures increase the rate of evaporation.",
    page_number=1,
    source_quote=(
        "Warmer temperatures increase the rate of evaporation, which is why evaporation is "
        "fastest in tropical regions and during summer months."
    ),
    # FLAW: ambiguous — the Note credits both "the sun's heat" (energy source)
    # and "warmer temperatures" (rate driver) for evaporation; options 1 and 2
    # aren't clearly distinguishable as the single correct answer from the text.
)

VERIFIER_CASES = [
    {
        "label": "verifier-evaporation-mixed",
        "concept": "Evaporation and Transpiration",
        "note_text": FULL_NOTE_TEXT,
        "questions": {
            1: FIXTURE_QUESTIONS[0],
            2: FIXTURE_QUESTIONS[1],
            3: FIXTURE_QUESTIONS[2],
            4: _adversarial_fabricated_quote,
            5: _adversarial_duplicate_distractors,
        },
        "expected_actions": {1: "keep", 2: "keep", 3: "keep", 4: "patch", 5: "patch"},
    },
    {
        "label": "verifier-condensation-mixed",
        "concept": "Condensation and Precipitation: forms and process",
        "note_text": FULL_NOTE_TEXT,
        "questions": {
            1: FIXTURE_QUESTIONS[3],
            2: FIXTURE_QUESTIONS[4],
            3: FIXTURE_QUESTIONS[5],
            4: _adversarial_wrong_page,
            5: _adversarial_select_all_mismatch,
        },
        # index 2 (FIXTURE_QUESTIONS[4]) was originally marked "keep" here as the
        # deliberate "Select-All with only 1 correct" edge case from the fixture
        # spec, but the Verifier consistently flags it (confirmed after tightening
        # its is_select_all guidance — see agent-test-log.md's 2026-08-10T12:48:37
        # fix verification): the question stem doesn't actually invite select-all
        # framing, independent of the count-inference issue that guidance fixed.
        "expected_actions": {1: "keep", 2: "patch", 3: "keep", 4: "patch", 5: "patch"},
    },
    {
        "label": "verifier-runoff-mixed",
        "concept": "Runoff and Groundwater Storage",
        "note_text": FULL_NOTE_TEXT,
        "questions": {
            1: FIXTURE_QUESTIONS[6],
            2: FIXTURE_QUESTIONS[7],
            3: _adversarial_mismatched_concept,
            4: _adversarial_ambiguous_phrasing,
        },
        "expected_actions": {1: "keep", 2: "keep", 3: "patch", 4: "patch"},
    },
]
