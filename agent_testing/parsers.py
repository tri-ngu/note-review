"""Deterministic parsing of each agent's --START--/--END--delimited free-text
output into the Pydantic models in models.py, per DESIGN.md's Agents section
("Python parses this text deterministically ... not an SDK-level structured
output_type"). Also includes the whitespace-normalized exact-substring
snippet validation DESIGN.md's Snippet grounding section requires before any
snippet/source_quote is trusted.
"""

import ast
import re

from models import ConceptSnippet, Question, VerifierIssue

_BODY_RE = re.compile(r"--START--\s*\n(.*?)\n--END--", re.DOTALL)
_FIELD_START_RE = re.compile(r"^(\w+):\s*", re.MULTILINE)
_QUOTED_RE = re.compile(r'"([^"]*)"')
_SNIPPET_RE = re.compile(r'\["([^"]*)"\s*:\s*(\d+)\]')


class ParseError(ValueError):
    pass


def extract_body(text: str) -> str:
    m = _BODY_RE.search(text)
    if not m:
        raise ParseError(f"no --START--/--END-- markers found in output: {text[:200]!r}")
    return m.group(1)


def split_blocks(body: str) -> list[str]:
    parts = re.split(r"\n\s*\n", body.strip())
    return [p.strip() for p in parts if p.strip()]


def parse_fields(block: str) -> dict[str, str]:
    matches = list(_FIELD_START_RE.finditer(block))
    if not matches:
        raise ParseError(f"no fields found in block: {block[:200]!r}")
    fields: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        fields[name] = block[start:end].strip()
    return fields


def unescape(s: str) -> str:
    """Undoes JSON-style escapes the model sometimes injects into our
    non-JSON quoted-string format (e.g. \\" for a literal quote inside a
    field). Order matters: backslash first, so a literal backslash isn't
    re-interpreted by the later replacements."""
    return s.replace("\\\\", "\x00").replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t").replace("\x00", "\\")


def parse_quoted_string(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return unescape(raw[1:-1])
    return unescape(raw)


def parse_float(raw: str) -> float:
    return float(raw.strip())


def parse_int(raw: str) -> int:
    return int(raw.strip())


def parse_bool(raw: str) -> bool:
    v = raw.strip().lower()
    if v not in ("true", "false"):
        raise ParseError(f"expected true/false, got {raw!r}")
    return v == "true"


def parse_list_str(raw: str) -> list[str]:
    """Primary format: a bracketed, double-quoted string list. `options` is
    this function's only caller and always expects exactly 4 entries
    (Question.exactly_four_options enforces this downstream regardless of
    what this function returns) — if the strict double-quote count isn't 4,
    falls back to parsing the bracketed text as a Python list literal via
    ast.literal_eval, which correctly handles single-quoted or mixed-quote
    strings, including internal apostrophes, unlike a naive quote-character
    replace. literal_eval only evaluates literals (no code execution risk);
    any failure or a non-list-of-str result falls back to the strict result
    unchanged, so this can only recover cases the strict parser would
    already have rejected — never accept something the strict parser would
    have parsed differently."""
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        raise ParseError(f"expected a bracketed list, got {raw!r}")
    strict = [unescape(s) for s in _QUOTED_RE.findall(raw)]
    if len(strict) == 4:
        return strict
    try:
        literal = ast.literal_eval(raw)
    except (ValueError, SyntaxError, MemoryError, RecursionError, TypeError):
        return strict
    if isinstance(literal, list) and all(isinstance(x, str) for x in literal):
        return literal
    return strict


def parse_list_int(raw: str) -> list[int]:
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        raise ParseError(f"expected a bracketed list, got {raw!r}")
    inner = raw[1:-1].strip()
    if not inner:
        return []
    return [int(x.strip()) for x in inner.split(",")]


def parse_snippets(raw: str) -> list[ConceptSnippet]:
    raw = raw.strip()
    if raw == "[]":
        return []
    return [ConceptSnippet(quote=q, page_number=int(n)) for q, n in _SNIPPET_RE.findall(raw)]


def normalize_whitespace(s: str) -> str:
    return " ".join(s.split())


def is_exact_substring(quote: str, source_text: str) -> bool:
    """Whitespace-normalized exact substring check — DESIGN.md's Snippet
    grounding rule: never trust a model's claim that a quote is real."""
    return normalize_whitespace(quote) in normalize_whitespace(source_text)


# --- Analyzer -----------------------------------------------------------

def parse_analyzer_output(text: str) -> list[dict]:
    """Returns list of {concept, weight_percentage, snippets} dicts —
    question_count isn't part of this call's output (Python derives it
    afterward, per DESIGN.md)."""
    blocks = split_blocks(extract_body(text))
    results = []
    for block in blocks:
        fields = parse_fields(block)
        results.append(
            {
                "concept": parse_quoted_string(fields["concept"]),
                "weight_percentage": parse_float(fields["weight_percentage"]),
                "snippets": parse_snippets(fields["snippets"]),
            }
        )
    return results


# --- Generator ------------------------------------------------------------

def _parse_question_fields(fields: dict[str, str], concept: str) -> Question:
    return Question(
        concept=concept,
        question_text=parse_quoted_string(fields["question_text"]),
        options=parse_list_str(fields["options"]),
        correct_answers=parse_list_int(fields["correct_answers"]),
        is_select_all=parse_bool(fields["is_select_all"]),
        explanation=parse_quoted_string(fields["explanation"]),
        page_number=parse_int(fields["page_number"]),
        source_quote=parse_quoted_string(fields["source_quote"]),
    )


def parse_generator_initial_output(text: str, concept: str) -> list[Question]:
    blocks = split_blocks(extract_body(text))
    return [_parse_question_fields(parse_fields(block), concept) for block in blocks]


def parse_generator_patch_output(text: str, concept: str) -> dict[int, Question]:
    blocks = split_blocks(extract_body(text))
    result: dict[int, Question] = {}
    for block in blocks:
        fields = parse_fields(block)
        index = parse_int(fields["index"])
        result[index] = _parse_question_fields(fields, concept)
    return result


# --- Verifier ---------------------------------------------------------------

def parse_verifier_output(text: str) -> tuple[list[VerifierIssue], bool]:
    blocks = split_blocks(extract_body(text))
    issues: list[VerifierIssue] = []
    satisfactory: bool | None = None
    for block in blocks:
        fields = parse_fields(block)
        if "satisfactory" in fields and "index" not in fields:
            satisfactory = parse_bool(fields["satisfactory"])
            continue
        issues.append(
            VerifierIssue(
                index=parse_int(fields["index"]),
                action=parse_quoted_string(fields["action"]),
                critique=parse_quoted_string(fields.get("critique", '""')),
                snippets=parse_snippets(fields.get("snippets", "[]")),
            )
        )
    if satisfactory is None:
        raise ParseError("no trailing 'satisfactory: true/false' line found")
    return issues, satisfactory


# --- Batched (multi-concept per call) variants -------------------------------
# One call now covers several Concepts at once (token-saving: fewer calls,
# less repeated boilerplate — see PROGRESS.md's concept-batching proposal),
# so each block is self-tagged with its own `concept` field instead of the
# caller passing a single concept in for the whole response.

def parse_generator_initial_batch_output(text: str) -> dict[str, list[Question]]:
    blocks = split_blocks(extract_body(text))
    result: dict[str, list[Question]] = {}
    for block in blocks:
        fields = parse_fields(block)
        concept = parse_quoted_string(fields["concept"])
        result.setdefault(concept, []).append(_parse_question_fields(fields, concept))
    return result


def parse_generator_patch_batch_output(text: str) -> dict[str, dict[int, Question]]:
    blocks = split_blocks(extract_body(text))
    result: dict[str, dict[int, Question]] = {}
    for block in blocks:
        fields = parse_fields(block)
        concept = parse_quoted_string(fields["concept"])
        index = parse_int(fields["index"])
        result.setdefault(concept, {})[index] = _parse_question_fields(fields, concept)
    return result


def parse_verifier_batch_output(text: str) -> dict[str, list[VerifierIssue]]:
    """No single trailing satisfactory line here — the batch spans several
    Concepts, so the caller derives per-concept satisfaction itself (empty
    flagged list for that concept) rather than trusting one call-level
    self-report to correctly span all of them."""
    blocks = split_blocks(extract_body(text))
    result: dict[str, list[VerifierIssue]] = {}
    for block in blocks:
        fields = parse_fields(block)
        concept = parse_quoted_string(fields["concept"])
        result.setdefault(concept, []).append(
            VerifierIssue(
                index=parse_int(fields["index"]),
                action=parse_quoted_string(fields["action"]),
                critique=parse_quoted_string(fields.get("critique", '""')),
                snippets=parse_snippets(fields.get("snippets", "[]")),
            )
        )
    return result
