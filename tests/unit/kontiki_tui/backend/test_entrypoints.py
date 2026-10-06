from kontiki_tui.backend.entrypoints import (
    apply_entrypoint_service_filter,
    build_service_rows,
    entrypoint_failed_display,
    service_failed_display,
)


def _instance(status="active", group="business", entrypoints=None, omit=False):
    metadata = {"group": group}
    if not omit:
        metadata["entrypoints"] = [] if entrypoints is None else entrypoints
    return {"status": status, "metadata": metadata}


def _event(name, handler, mode="competing", attempts=3):
    entry = {
        "type": "event",
        "name": name,
        "handler": handler,
        "mode": mode,
    }
    if mode == "competing":
        entry["max_attempts"] = attempts
    return entry


def _analyzer():
    return [
        _event("analysis.requested", "handle_analysis", attempts=3),
        _event("ui.progress", "on_progress", mode="in_session"),
        {"type": "rpc", "name": "get_status", "handler": "get_status"},
        {
            "type": "http",
            "method": "POST",
            "path": "/analysis",
            "handler": "create_analysis",
        },
        {"type": "task", "handler": "backup", "schedule": "0 2 * * *"},
    ]


def test_live_instances_in_the_group_form_one_service_row():
    raw = {
        "Analyzer": {
            "bbbb": _instance(entrypoints=_analyzer()),
            "aaaa": _instance(entrypoints=_analyzer()),
            "down": _instance(status="down", entrypoints=_analyzer()),
            "other": _instance(group="platform", entrypoints=_analyzer()),
        }
    }
    rows = build_service_rows(raw, "business")
    assert len(rows) == 1
    row = rows[0]
    assert row["service_name"] == "Analyzer"
    assert row["instances"] == 2
    assert row["catalogue"] == "ok"
    assert [entry["declared"] for entry in row["entrypoints"]] == ["2/2"] * 5
    competing = row["entrypoints"][0]
    assert competing["name"] == "analysis.requested"
    assert competing["mode"] == "competing"
    assert competing["attempts"] == "3"
    assert competing["competing"] is True
    progress = row["entrypoints"][1]
    assert progress["mode"] == "in_session"
    assert progress["attempts"] == ""
    assert progress["competing"] is False
    assert row["entrypoints"][3]["name"] == "POST /analysis"
    task = row["entrypoints"][4]
    assert task["name"] == "backup"
    assert task["handler"] == "backup"
    assert task["mode"] == "0 2 * * *"
    assert task["attempts"] == ""


def test_one_instance_without_entrypoints_hides_the_catalogue():
    raw = {
        "Analyzer": {
            "aaaa": _instance(entrypoints=_analyzer()),
            "bbbb": _instance(omit=True),
        }
    }
    rows = build_service_rows(raw, "all")
    assert rows[0]["catalogue"] == "unknown"
    assert rows[0]["entrypoints"] == []
    assert rows[0]["instances"] == 2


def test_empty_catalogue_is_known():
    raw = {"Analyzer": {"aaaa": _instance(entrypoints=[])}}
    rows = build_service_rows(raw, "all")
    assert rows[0]["catalogue"] == "ok"
    assert rows[0]["entrypoints"] == []
    assert service_failed_display(rows[0], {}) == "0"


def test_replica_gap_and_divergent_lines():
    shared = _event("analysis.requested", "handle_analysis")
    raw = {
        "Analyzer": {
            "aaaa": _instance(
                entrypoints=[
                    shared,
                    {
                        "type": "http",
                        "method": "POST",
                        "path": "/analysis",
                        "handler": "create_analysis",
                    },
                ]
            ),
            "bbbb": _instance(
                entrypoints=[
                    _event("analysis.requested", "handle_other", attempts=5),
                ]
            ),
        }
    }
    rows = build_service_rows(raw, "all")
    declared = {
        (entry["name"], entry["handler"], entry["attempts"]): entry["declared"]
        for entry in rows[0]["entrypoints"]
    }
    assert declared[("analysis.requested", "handle_analysis", "3")] == "1/2"
    assert declared[("analysis.requested", "handle_other", "5")] == "1/2"
    assert declared[("POST /analysis", "create_analysis", "")] == "1/2"
    counts = {("Analyzer", "analysis.requested"): 3}
    assert service_failed_display(rows[0], counts) == "3"
    for entry in rows[0]["entrypoints"]:
        if entry["competing"]:
            assert entrypoint_failed_display("Analyzer", entry, counts) == "3"
        else:
            assert entrypoint_failed_display("Analyzer", entry, counts) == ""


def test_failed_cell_is_zero_when_nothing_is_retained():
    raw = {
        "Analyzer": {
            "aaaa": _instance(
                entrypoints=[_event("analysis.requested", "handle_analysis")]
            )
        }
    }
    row = build_service_rows(raw, "all")[0]
    counts = {("Analyzer", "analysis.requested"): 0}
    assert service_failed_display(row, counts) == "0"
    assert entrypoint_failed_display("Analyzer", row["entrypoints"][0], counts) == "0"


def test_missing_count_leaves_failed_blank():
    raw = {
        "Analyzer": {
            "aaaa": _instance(
                entrypoints=[_event("analysis.requested", "handle_analysis")]
            )
        }
    }
    row = build_service_rows(raw, "all")[0]
    assert service_failed_display(row, {}) == ""
    assert entrypoint_failed_display("Analyzer", row["entrypoints"][0], {}) == ""
    assert (
        service_failed_display(
            {"catalogue": "unknown", "service_name": "Analyzer", "entrypoints": []},
            {},
        )
        == ""
    )


def test_service_name_filter():
    rows = [
        {"service_name": "Analyzer"},
        {"service_name": "Billing"},
    ]
    assert apply_entrypoint_service_filter(rows, "all", "ana") == rows
    assert apply_entrypoint_service_filter(rows, "service_name", "") == rows
    assert [
        row["service_name"]
        for row in apply_entrypoint_service_filter(rows, "service_name", "BILL")
    ] == ["Billing"]


def test_down_only_service_is_omitted():
    raw = {"Analyzer": {"aaaa": _instance(status="down", entrypoints=_analyzer())}}
    assert build_service_rows(raw, "all") == []


def test_duplicate_line_on_one_instance_counts_once():
    line = _event("analysis.requested", "handle_analysis")
    raw = {"Analyzer": {"aaaa": _instance(entrypoints=[line, dict(line)])}}
    row = build_service_rows(raw, "all")[0]
    assert len(row["entrypoints"]) == 1
    assert row["entrypoints"][0]["declared"] == "1/1"
