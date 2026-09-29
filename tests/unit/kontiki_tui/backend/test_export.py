from datetime import datetime, timezone
from pathlib import Path

import pytest

from kontiki_tui.backend.export import (
    LAST_EXPORT_NAME,
    exception_stem,
    export_directory,
    export_markdown,
    flow_log_instance_keys,
    flow_stem,
    incident_stem,
    planned_export_path,
    render_exception,
    render_flow,
    render_incident,
    sanitize_filename_part,
    write_markdown_export,
)
from kontiki_tui.config import BASE_CONF


def test_export_directory_uses_conf():
    assert export_directory({"export": {"directory": "/tmp/out"}}) == "/tmp/out"


def test_export_directory_falls_back_to_base_conf():
    assert export_directory({}) == BASE_CONF["export"]["directory"]
    assert export_directory({"export": {}}) == BASE_CONF["export"]["directory"]
    assert (
        export_directory({"export": {"directory": "  "}})
        == BASE_CONF["export"]["directory"]
    )


def test_sanitize_filename_part():
    assert sanitize_filename_part("a1b2c3d4e5f6") == "a1b2c3d4e5f6"
    assert sanitize_filename_part("fleet:alpha/missing") == "fleet_alpha_missing"
    assert sanitize_filename_part("") == "no-id"
    assert sanitize_filename_part(None) == "no-id"


def test_stems_include_stamp():
    now = datetime(2026, 9, 18, 14, 48, 2, tzinfo=timezone.utc)
    assert exception_stem({"flow_id": "a1b2c3d4e5f6"}, now=now) == (
        "exception-a1b2c3d4e5f6-20260918T144802"
    )
    assert exception_stem({"flow_id": None}, now=now) == (
        "exception-no-flow-20260918T144802"
    )
    assert flow_stem({"flow_id": "a1b2c3d4e5f6"}, now=now) == (
        "flow-a1b2c3d4e5f6-20260918T144802"
    )
    assert incident_stem({"alert_id": "fleet:alpha:missing"}, now=now) == (
        "incident-fleet_alpha_missing-20260918T144802"
    )


def test_render_exception():
    text = render_exception(
        {
            "timestamp": "2026-09-18T12:44:01+00:00",
            "service_name": "RpcService",
            "instance_id": "11111111-2222-3333-4444-555555555555",
            "flow_id": "a1b2c3d4e5f6",
            "entrypoint": "rpc",
            "operation": "charge",
            "exception_type": "ValueError",
            "message": "bad amount",
        }
    )
    assert text.startswith("# Exception — RpcService 111111112222\n")
    assert "- Time: 2026-09-18 12:44:01 UTC\n" in text
    assert "- Flow: a1b2c3d4e5f6\n" in text
    assert "- Entrypoint: rpc\n" in text
    assert "- Operation: charge\n" in text
    assert "- Type: ValueError\n" in text
    assert "- Message: bad amount\n" in text


def test_render_exception_null_scope():
    text = render_exception(
        {
            "service_name": "BootSvc",
            "instance_id": "abc",
            "flow_id": None,
            "entrypoint": None,
            "operation": None,
            "exception_type": "RuntimeError",
            "message": "nope",
        }
    )
    assert "- Flow: —\n" in text
    assert "- Entrypoint: —\n" in text
    assert "- Operation: —\n" in text


def test_render_flow_hops():
    text = render_flow(
        {
            "flow_id": "a1b2c3d4e5f6",
            "origin": "OrderApi",
            "first_type": "order.placed",
            "started": "2026-09-18T09:14:01.120000+00:00",
            "last": "2026-09-18T09:14:02.050000+00:00",
            "hops": [
                {
                    "timestamp": "2026-09-18T09:14:01.120000+00:00",
                    "_group": "business",
                    "service_name": "OrderApi",
                    "instance_id": "11111111-2222-3333-4444-555555555555",
                    "event_type": "order.placed",
                    "host": "box-1",
                },
                {
                    "timestamp": "2026-09-18T09:14:01.400000+00:00",
                    "_group": "platform",
                    "service_name": "Billing",
                    "instance_id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
                    "remote_method": "charge",
                    "host": "box-2",
                },
            ],
        }
    )
    assert text.startswith("# Flow a1b2c3d4e5f6\n")
    assert "- Origin: OrderApi\n" in text
    assert "- First: order.placed\n" in text
    assert "- Messages: 2\n" in text
    assert (
        "| Time | Group | Service | Instance | Type | Host |\n"
        "| --- | --- | --- | --- | --- | --- |\n" in text
    )
    assert (
        "| 09:14:01.12 | business | OrderApi | 111111112222 | order.placed | box-1 |\n"
        in text
    )
    assert (
        "| 09:14:01.40 | platform | Billing | bbbbbbbbcccc | rpc:charge | box-2 |\n"
        in text
    )


def test_render_flow_tree_exception_shows_record_time():
    text = render_flow(
        {
            "flow_id": "a1b2c3d4e5f6",
            "origin": "OrderApi",
            "first_type": "order.placed",
            "hops": [{}],
            "tree_rows": [
                {
                    "_kind": "message",
                    "_depth": 0,
                    "_delta": "—",
                    "_group": "business",
                    "timestamp": "2026-09-18T09:14:01.120000+00:00",
                    "service_name": "OrderApi",
                    "instance_id": "11111111-2222-3333-4444-555555555555",
                    "event_type": "order.placed",
                    "host": "box-1",
                },
                {
                    "_kind": "message",
                    "_depth": 2,
                    "_delta": "+1ms",
                    "_group": "business",
                    "timestamp": "2026-09-18T09:14:01.160000+00:00",
                    "service_name": "Notify",
                    "instance_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "event_type": "chain.c",
                    "host": "box-2",
                },
                {
                    "_kind": "exception",
                    "_depth": 1,
                    "_delta": "—",
                    "_group": "business",
                    "timestamp": "2026-09-18T09:14:01.200000+00:00",
                    "service_name": "Notify",
                    "instance_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "exception_type": "ValueError",
                    "message": "boom | extra",
                    "host": "box-2",
                },
            ],
        }
    )
    assert "- Messages: 1\n" in text
    assert (
        "| 09:14:01.16 | business | Notify | aaaaaaaabbbb |"
        " ↪️↪️  [+1ms] chain.c | box-2 |\n"
    ) in text
    assert (
        "| 09:14:01.20 | business | Notify | aaaaaaaabbbb |"
        " 💥 exc:ValueError: boom \\| extra | box-2 |\n"
    ) in text


def test_render_flow_empty_hops():
    text = render_flow({"flow_id": "deadbeef0000", "hops": []})
    assert "## Timeline\n\n—\n" in text
    assert "## Logs" not in text


def test_render_flow_logs_section():
    text = render_flow(
        {"flow_id": "a1b2c3d4e5f6", "hops": []},
        log_lines=["[flow=a1b2c3d4e5f6] boom"],
    )
    assert "## Logs\n\n```\n[flow=a1b2c3d4e5f6] boom\n```\n" in text


def test_render_flow_empty_logs():
    text = render_flow({"flow_id": "a1b2c3d4e5f6", "hops": []}, log_lines=[])
    assert "## Logs\n\n—\n" in text


def test_flow_log_instance_keys_skips_duplicates():
    keys = flow_log_instance_keys(
        {
            "hops": [
                {
                    "service_name": "OrderApi",
                    "instance_id": "11111111-2222-3333-4444-555555555555",
                },
                {
                    "service_name": "OrderApi",
                    "instance_id": "11111111-2222-3333-4444-555555555555",
                },
                {
                    "service_name": "Billing",
                    "instance_id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
                },
            ]
        }
    )
    assert keys == [
        ("OrderApi", "11111111-2222-3333-4444-555555555555"),
        ("Billing", "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"),
    ]


def test_render_incident_drops_producer_keys():
    text = render_incident(
        {
            "alert_id": "fleet:alpha-service:missing",
            "source": "kontiki-monitor",
            "event_type": "expected_service_missing",
            "severity": "critical",
            "title": "alpha-service missing from registry",
            "body": "alpha-service missing from registry",
            "occurred_at": "2026-09-14T20:57:00+00:00",
            "attributes": {"service_name": "alpha-service"},
            "_producer_service": "kontiki-monitor",
            "_producer_instance_id": "mon-1",
        }
    )
    assert text.startswith("# alpha-service missing from registry\n")
    assert "- Severity: critical\n" in text
    assert "- Host: N/A\n" in text
    assert "- Service: alpha-service\n" in text
    assert "_producer_service" not in text
    assert "## Body\n\n" in text
    assert "alpha-service missing from registry\n" in text


def test_planned_export_path(tmp_path):
    conf = {"export": {"directory": str(tmp_path / "out")}}
    assert planned_export_path(conf, "exception-abc") == str(
        tmp_path / "out" / "exception-abc.md"
    )


def test_write_markdown_export_unique_and_last(tmp_path):
    directory = tmp_path / "exports"
    path = write_markdown_export(
        str(directory), "exception-abc-20260918T144802", "# Hi\n"
    )
    unique = Path(path)
    last = directory / LAST_EXPORT_NAME
    assert unique.name == "exception-abc-20260918T144802.md"
    assert unique.read_text(encoding="utf-8") == "# Hi\n"
    assert last.read_text(encoding="utf-8") == "# Hi\n"


def test_write_markdown_export_overwrites_last(tmp_path):
    directory = tmp_path / "exports"
    write_markdown_export(str(directory), "one", "first")
    write_markdown_export(str(directory), "two", "second")
    assert (directory / "one.md").read_text(encoding="utf-8") == "first"
    assert (directory / "two.md").read_text(encoding="utf-8") == "second"
    assert (directory / LAST_EXPORT_NAME).read_text(encoding="utf-8") == "second"


def test_export_markdown_uses_conf_directory(tmp_path):
    conf = {"export": {"directory": str(tmp_path / "out")}}
    path = export_markdown(conf, "flow-x", "# Flow\n")
    assert Path(path).parent == tmp_path / "out"
    assert Path(path).read_text(encoding="utf-8") == "# Flow\n"


def test_write_markdown_export_fails_when_path_is_a_file(tmp_path):
    target = tmp_path / "not-a-dir"
    target.write_text("nope", encoding="utf-8")
    with pytest.raises(OSError):
        write_markdown_export(str(target), "x", "# x\n")
