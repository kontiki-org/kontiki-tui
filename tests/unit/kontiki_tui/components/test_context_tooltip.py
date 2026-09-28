from kontiki_tui.components.flows import format_context_tooltip


def test_single_context_aligned_keys():
    text = format_context_tooltip(
        [{"feature": "standard_case", "result": "Standard case"}]
    )
    assert text.plain == "feature  standard_case\nresult   Standard case"


def test_nested_dict_indented():
    text = format_context_tooltip([{"order": {"id": 42, "note": "priority"}}])
    assert text.plain == "order:\n  id    42\n  note  priority"


def test_list_items():
    text = format_context_tooltip([{"tags": ["alpha", "beta"]}])
    assert text.plain == "tags:\n  - alpha\n  - beta"


def test_scalars():
    text = format_context_tooltip(
        [{"empty": None, "flag": True, "off": False, "raw": "with [brackets]"}]
    )
    assert (
        text.plain == "empty  null\nflag   true\noff    false\nraw    with [brackets]"
    )


def test_multiple_contexts_get_headers():
    text = format_context_tooltip(
        [{"step": "first"}, {"step": "second", "extra": "detail"}]
    )
    assert text.plain == (
        "context 1/2\nstep  first\n\n" "context 2/2\nstep   second\nextra  detail"
    )


def test_empty_structures():
    assert format_context_tooltip([{}]).plain == "{}"
    assert format_context_tooltip([{"items": []}]).plain == "items  []"
