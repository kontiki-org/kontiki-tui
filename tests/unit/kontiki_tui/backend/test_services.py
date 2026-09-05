import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from kontiki_tui.backend.services import (
    Services,
    format_degraded_reason,
    format_last_heartbeat,
    implied_platform_group,
    matches_group_filter,
    normalize_registration_group,
)


@pytest.fixture
def messenger():
    return Mock(name="messenger")


@pytest.fixture
def services(messenger):
    return Services(messenger=messenger)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, "business"),
        ("", "business"),
        ("   ", "business"),
        ("business", "business"),
        ("platform", "platform"),
        (" batch ", "batch"),
        (123, "business"),
    ],
)
def test_normalize_registration_group(raw, expected):
    assert normalize_registration_group(raw) == expected


def test_matches_group_filter_business_only():
    assert matches_group_filter(None, "business")
    assert matches_group_filter("", "business")
    assert matches_group_filter("  ", "business")
    assert matches_group_filter("business", "business")
    assert not matches_group_filter("platform", "business")
    assert not matches_group_filter("batch", "business")


def test_matches_group_filter_concrete_group():
    assert matches_group_filter("platform", "platform")
    assert not matches_group_filter("business", "platform")
    assert matches_group_filter("batch", "batch")


def test_matches_group_filter_all():
    assert matches_group_filter("platform", "all")
    assert matches_group_filter("business", "all")
    assert matches_group_filter(None, "all")
    assert matches_group_filter("batch", "all")


def test_group_filter_select_options_from_discovered():
    from kontiki_tui.backend.services import group_filter_select_options

    options = group_filter_select_options(["earth", "batch"])
    values = [v for _, v in options]
    assert values[0] == "all"
    assert values[1:] == ["batch", "earth"]
    assert "business" not in values
    assert "platform" not in values


def test_group_filter_select_options_empty():
    from kontiki_tui.backend.services import group_filter_select_options

    assert [v for _, v in group_filter_select_options([])] == ["all"]
    assert [v for _, v in group_filter_select_options(None)] == ["all"]


def test_implied_platform_group():
    assert implied_platform_group("ServiceRegistry") == "platform"
    assert implied_platform_group("OrderSvc") is None
    assert implied_platform_group(None) is None


def test_is_internal_registry_event(services):
    # Hide observer + ServiceRegistry; keep domain events and RPC calls.
    assert not services._is_internal_registry_event({"event_type": "_rpc_event"})
    assert not services._is_internal_registry_event(
        {"remote_method": "rpc_example", "service_name": "SvcA"}
    )
    assert services._is_internal_registry_event({"service_name": "ServiceRegistry"})
    assert services._is_internal_registry_event({"service_name": "kontiki_tui"})
    assert services._is_internal_registry_event(
        {"service_name": "kontiki_tui-standalone-x"}
    )

    assert not services._is_internal_registry_event(
        {"event_type": "simple_event", "service_name": "SvcA"}
    )
    assert not services._is_internal_registry_event({"service_name": "kontiki"})
    assert not services._is_internal_registry_event({"service_name": "MyService"})


def test_filter_registry_events(services):
    events = [
        {"remote_method": "rpc_example", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "ServiceRegistry"},
        {"event_type": "business", "service_name": "kontiki_tui"},
        {"event_type": "business", "service_name": "SvcB"},
    ]

    kept = services._filter_registry_events(events, include_internal=False)
    assert kept == [
        {"remote_method": "rpc_example", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcB"},
    ]

    kept_internal = services._filter_registry_events(events, include_internal=True)
    assert kept_internal == events


def test_format_last_heartbeat():
    assert format_last_heartbeat(None) == ""
    assert format_last_heartbeat("") == ""
    assert format_last_heartbeat("  ") == ""
    assert (
        format_last_heartbeat("2026-09-04T11:59:48.123456+00:00")
        == "2026-09-04 11:59:48"
    )
    assert format_last_heartbeat("2026-09-04T11:59:48Z") == "2026-09-04 11:59:48"


def test_format_degraded_reason():
    assert format_degraded_reason(None) == "-"
    assert format_degraded_reason("") == "-"
    assert format_degraded_reason("   ") == "-"
    assert format_degraded_reason("amqp timeout") == "amqp timeout"


def test_get_events_filters_observer_and_registry_noise(services):
    raw = [
        {"remote_method": "rpc_example", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "ServiceRegistry"},
        {"event_type": "business", "service_name": "kontiki_tui"},
        {"event_type": "business", "service_name": "SvcB"},
    ]

    services.services.get_events = AsyncMock(return_value=raw)
    out = asyncio.run(services.get_events())
    assert out == [
        {"remote_method": "rpc_example", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcB"},
    ]


# ---------------------------------------------------------------------------
# group_filter on events
# ---------------------------------------------------------------------------


def _make_registry(group_map):
    """Return a get_services mock payload from {(svc, inst): group}."""
    result = {}
    for (svc, inst), group in group_map.items():
        result.setdefault(svc, {})[inst] = {
            "status": "active",
            "metadata": {"group": group, "pid": 1, "host": "h"},
        }
    return result


def test_get_events_group_filter_business(services):
    raw = [
        {
            "event_type": "order.placed",
            "service_name": "OrderSvc",
            "instance_id": "inst-1",
        },
        {
            "event_type": "infra.ping",
            "service_name": "PlatformSvc",
            "instance_id": "inst-2",
        },
    ]
    services.services.get_events = AsyncMock(return_value=raw)
    services.services.get_services = AsyncMock(
        return_value=_make_registry(
            {
                ("OrderSvc", "inst-1"): "business",
                ("PlatformSvc", "inst-2"): "platform",
            }
        )
    )
    out = asyncio.run(services.get_events(group_filter="business"))
    assert out == [
        {
            "event_type": "order.placed",
            "service_name": "OrderSvc",
            "instance_id": "inst-1",
        }
    ]


def test_get_events_group_filter_all(services):
    raw = [
        {
            "event_type": "order.placed",
            "service_name": "OrderSvc",
            "instance_id": "inst-1",
        },
        {
            "event_type": "infra.ping",
            "service_name": "PlatformSvc",
            "instance_id": "inst-2",
        },
    ]
    services.services.get_events = AsyncMock(return_value=raw)
    out = asyncio.run(services.get_events(group_filter="all"))
    assert len(out) == 2


def test_get_events_unknown_instance_defaults_to_business(services):
    """Deregistered instance (not in registry) falls back to business."""
    raw = [{"event_type": "x", "service_name": "Gone", "instance_id": "old-inst"}]
    services.services.get_events = AsyncMock(return_value=raw)
    services.services.get_services = AsyncMock(return_value={})
    out = asyncio.run(services.get_events(group_filter="business"))
    assert out == raw


# ---------------------------------------------------------------------------
# group_filter on exceptions
# ---------------------------------------------------------------------------


def test_get_exceptions_group_filter_business(services):
    raw = [
        {
            "exception_type": "ValueError",
            "service_name": "OrderSvc",
            "instance_id": "inst-1",
        },
        {
            "exception_type": "RuntimeError",
            "service_name": "PlatformSvc",
            "instance_id": "inst-2",
        },
    ]
    services.services.get_exceptions = AsyncMock(return_value=raw)
    services.services.get_services = AsyncMock(
        return_value=_make_registry(
            {
                ("OrderSvc", "inst-1"): "business",
                ("PlatformSvc", "inst-2"): "platform",
            }
        )
    )
    out = asyncio.run(services.get_exceptions(group_filter="business"))
    assert out == [
        {
            "exception_type": "ValueError",
            "service_name": "OrderSvc",
            "instance_id": "inst-1",
        }
    ]


def test_get_exceptions_group_filter_all(services):
    raw = [
        {
            "exception_type": "ValueError",
            "service_name": "OrderSvc",
            "instance_id": "inst-1",
        },
        {
            "exception_type": "RuntimeError",
            "service_name": "PlatformSvc",
            "instance_id": "inst-2",
        },
    ]
    services.services.get_exceptions = AsyncMock(return_value=raw)
    out = asyncio.run(services.get_exceptions(group_filter="all"))
    assert len(out) == 2


# ---------------------------------------------------------------------------
# get_log_files_for_group
# ---------------------------------------------------------------------------


def test_get_log_files_for_group_all(services, tmp_path):
    (tmp_path / "OrderSvc-aabbccddeeff.log").write_text("x")
    (tmp_path / "PlatformSvc-112233445566.log").write_text("x")
    (tmp_path / "ServiceRegistry-8403559c88ae.log").write_text("x")
    out = asyncio.run(services.get_log_files_for_group(str(tmp_path), "all"))
    assert len(out) == 2
    assert all("ServiceRegistry" not in path for path in out)


def test_get_log_files_for_group_business(services, tmp_path):
    (tmp_path / "OrderSvc-aabbccddeeff.log").write_text("x")
    (tmp_path / "PlatformSvc-112233445566.log").write_text("x")

    # OrderSvc inst UUID starts with aabbccddeeff
    services.services.get_services = AsyncMock(
        return_value=_make_registry(
            {
                ("OrderSvc", "aabbccddeeff-0000-0000-0000-000000000000"): "business",
                ("PlatformSvc", "11223344-5566-0000-0000-000000000000"): "platform",
            }
        )
    )
    out = asyncio.run(services.get_log_files_for_group(str(tmp_path), "business"))
    assert len(out) == 1
    assert "OrderSvc" in out[0]


def test_get_log_files_for_group_non_kontiki_file_always_included(services, tmp_path):
    """Files not matching the Kontiki naming pattern are always included."""
    (tmp_path / "some_legacy.log").write_text("x")
    services.services.get_services = AsyncMock(return_value={})
    out = asyncio.run(services.get_log_files_for_group(str(tmp_path), "business"))
    assert len(out) == 1


def test_get_log_files_for_group_empty_dir(services, tmp_path):
    services.services.get_services = AsyncMock(return_value={})
    out = asyncio.run(services.get_log_files_for_group(str(tmp_path), "business"))
    assert out == []


def test_get_log_files_for_group_missing_dir(services):
    out = asyncio.run(services.get_log_files_for_group("/nonexistent/path", "business"))
    assert out == []


def test_get_log_files_always_excludes_service_registry(services, tmp_path):
    """ServiceRegistry-*.log is never listed, including group_filter=platform/all."""
    (tmp_path / "OrderSvc-aabbccddeeff.log").write_text("x")
    (tmp_path / "ServiceRegistry-8403559c88ae.log").write_text("x")
    services.services.get_services = AsyncMock(
        return_value=_make_registry(
            {
                ("OrderSvc", "aabbccddeeff-0000-0000-0000-000000000000"): "business",
            }
        )
    )
    for group_filter in ("business", "platform", "all"):
        out = asyncio.run(services.get_log_files_for_group(str(tmp_path), group_filter))
        assert all("ServiceRegistry" not in path for path in out)
    business = asyncio.run(services.get_log_files_for_group(str(tmp_path), "business"))
    assert len(business) == 1
    assert "OrderSvc" in business[0]


def test_get_exceptions_excludes_service_registry(services):
    raw = [
        {
            "exception_type": "ValueError",
            "service_name": "OrderSvc",
            "instance_id": "inst-1",
        },
        {
            "exception_type": "RuntimeError",
            "service_name": "ServiceRegistry",
            "instance_id": "reg-1",
        },
    ]
    services.services.get_exceptions = AsyncMock(return_value=raw)
    services.services.get_services = AsyncMock(return_value={})
    out = asyncio.run(services.get_exceptions(group_filter="business"))
    assert out == [
        {
            "exception_type": "ValueError",
            "service_name": "OrderSvc",
            "instance_id": "inst-1",
        }
    ]
