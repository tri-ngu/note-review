"""Offline unit tests for parsers.py's pure-Python parsing functions — no
live agent calls, no network. Run directly: python test_parsers_unit.py
(this project's .venv has no pytest installed; every other test harness in
agent_testing/ follows this same assert-and-print-PASS convention, not
pytest)."""

from parsers import ParseError, parse_list_str


def test_parse_list_str_strict_double_quoted():
    result = parse_list_str('["Rain", "Snow", "Evaporation", "Hail"]')
    assert result == ["Rain", "Snow", "Evaporation", "Hail"], result


def test_parse_list_str_falls_back_to_single_quoted_literal():
    # Real failure mode from generator-model-swap-log.md: llama-3.3-70b-versatile
    # wrote options as a single-quoted Python-list literal instead of the
    # spec's double-quoted format.
    result = parse_list_str("['Rain', 'Snow', 'Evaporation', 'Hail']")
    assert result == ["Rain", "Snow", "Evaporation", "Hail"], result


def test_parse_list_str_preserves_internal_apostrophe():
    result = parse_list_str(r"""['It\'s raining', "Snow", "Evaporation", "Hail"]""")
    assert result[0] == "It's raining", result
    assert result == ["It's raining", "Snow", "Evaporation", "Hail"], result


def test_parse_list_str_non_bracketed_raises():
    try:
        parse_list_str('"Rain", "Snow"')
    except ParseError:
        pass
    else:
        raise AssertionError("expected ParseError for a non-bracketed input")


def test_parse_list_str_malformed_falls_back_to_strict_unchanged():
    # Not valid Python (mismatched quote) and doesn't yield 4 entries either
    # way — must not raise, must return whatever the strict path found.
    result = parse_list_str('["Rain, "Snow"]')
    assert isinstance(result, list), result


def main() -> None:
    tests = [
        test_parse_list_str_strict_double_quoted,
        test_parse_list_str_falls_back_to_single_quoted_literal,
        test_parse_list_str_preserves_internal_apostrophe,
        test_parse_list_str_non_bracketed_raises,
        test_parse_list_str_malformed_falls_back_to_strict_unchanged,
    ]
    failures = []
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception as e:
            failures.append((t.__name__, e))
            print(f"FAIL: {t.__name__}: {e}")
    if failures:
        raise SystemExit(f"{len(failures)}/{len(tests)} tests failed")
    print(f"All {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
