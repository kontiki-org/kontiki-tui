from rich.text import Text

from kontiki_tui.components.flows import FlowsTab


def _row_tuple(kind, **overrides):
    row = {
        "_kind": kind,
        "_depth": 1,
        "_group": "business",
        "service_name": "Notify",
        "instance_id": "inst-notify",
        "timestamp": "2026-09-18T09:14:01.200000+00:00",
        "host": "box-1",
    }
    row.update(overrides)
    return FlowsTab(id_="flows")._hop_row_tuple(row)


def test_context_row_cyan_with_record_time():
    cells = _row_tuple(
        "context",
        _contexts=[{"context_id": "ctx-1", "context": {"feature": "standard_case"}}],
    )
    assert cells[0] == "09:14:01.20"
    assert isinstance(cells[4], Text)
    assert cells[4].plain == "  💡 1 context value [ctx-1]"
    assert cells[4].style == "cyan"


def test_exception_row_red_with_record_time():
    cells = _row_tuple("exception", exception_type="ValueError", message="boom")
    assert cells[0] == "09:14:01.20"
    assert cells[4].style == "red"


def test_message_row_plain_with_time():
    cells = _row_tuple("message", event_type="order.placed", _delta="+30ms")
    assert cells[0] == "09:14:01.20"
    assert not isinstance(cells[4], Text)
