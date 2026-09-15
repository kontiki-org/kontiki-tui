import asyncio
import pickle
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from boomerang_contracts.alert.normalized import NormalizedAlert

from kontiki_tui.backend.services import (
    MONITOR_SERVICE_NAME,
    OPS_OPEN_ALERT_SOURCES,
    Services,
    alert_to_dict,
    apply_incident_field_filter,
    apply_silence_field_filter,
    build_silence_rows,
    display_alert_dict,
    format_instance_unreachable,
    format_last_heartbeat,
    format_orphan_silence_warning,
    group_for_open_alert,
    incident_host_display,
    live_service_names_in_group,
    open_alert_matches_group,
    orphan_silenced_count,
    silence_matches_group,
    silenced_service_names,
)


@pytest.fixture
def services():
    messenger = Mock(name="messenger")
    messenger.call = AsyncMock()
    backend = Services(messenger=messenger)
    backend.services.list_instances = AsyncMock()
    backend.services.get_services = AsyncMock(return_value={})
    return backend


def test_alert_to_dict_copies_mapping():
    raw = {"alert_id": "fleet:alpha:missing", "title": "missing"}
    out = alert_to_dict(raw)
    assert out == raw
    out["alert_id"] = "other"
    assert raw["alert_id"] == "fleet:alpha:missing"


def test_alert_to_dict_pydantic_model_dump():
    class FakeAlert:
        def model_dump(self, mode="python"):
            return {"alert_id": "x", "mode": mode}

    assert alert_to_dict(FakeAlert()) == {"alert_id": "x", "mode": "json"}


def test_alert_to_dict_unpickles_normalized_alert():
    alert = NormalizedAlert(
        alert_id="fleet:alpha-service:missing",
        source="kontiki-monitor",
        category="kontiki.registry",
        event_type="expected_service_missing",
        severity="critical",
        occurred_at=datetime(2026, 9, 14, 20, 57, tzinfo=timezone.utc),
        title="alpha-service missing from registry",
        body="alpha-service missing from registry",
        areas=[],
        attributes={"service_name": "alpha-service", "resolution": "open"},
        expires_at=None,
    )
    restored = pickle.loads(pickle.dumps(alert))
    out = alert_to_dict(restored)
    assert out["alert_id"] == "fleet:alpha-service:missing"
    assert out["source"] == "kontiki-monitor"
    assert out["attributes"]["service_name"] == "alpha-service"


def test_display_alert_dict_drops_producer_keys():
    alert = {
        "alert_id": "disk:edge-1:/",
        "_producer_service": "host-check-service",
        "_producer_instance_id": "abc",
    }
    assert display_alert_dict(alert) == {"alert_id": "disk:edge-1:/"}


def test_group_for_open_alert_uses_subject_service():
    mapping = {("payment-service", "i1"): "platform"}
    alert = {"attributes": {"service_name": "payment-service"}}
    assert group_for_open_alert(alert, mapping) == "platform"


def test_group_for_open_alert_missing_service_is_business():
    alert = {"attributes": {"service_name": "alpha-service"}}
    assert group_for_open_alert(alert, {}) == "business"


def test_group_for_open_alert_disk_uses_producer_instance():
    mapping = {("host-check-service", "inst-1"): "platform"}
    alert = {
        "attributes": {"host": "edge-1"},
        "_producer_service": "host-check-service",
        "_producer_instance_id": "inst-1",
    }
    assert group_for_open_alert(alert, mapping) == "platform"
    assert group_for_open_alert(alert, {}) is None


def test_open_alert_matches_group_disk_only_in_all():
    alert = {
        "attributes": {},
        "_producer_service": "host-check-service",
        "_producer_instance_id": "gone",
    }
    assert open_alert_matches_group(alert, "all", {})
    assert not open_alert_matches_group(alert, "business", {})


def test_apply_incident_field_filter_attributes_and_title():
    rows = [
        {
            "severity": "critical",
            "title": "alpha missing",
            "alert_id": "fleet:alpha:missing",
            "attributes": {"service_name": "alpha-service", "host": ""},
        },
        {
            "severity": "warning",
            "title": "disk high",
            "alert_id": "disk:edge-1:/",
            "attributes": {"host": "edge-1"},
        },
    ]
    assert apply_incident_field_filter(rows, "all", "alpha") == rows
    by_service = apply_incident_field_filter(rows, "service_name", "ALPHA")
    assert [row["alert_id"] for row in by_service] == ["fleet:alpha:missing"]
    by_host = apply_incident_field_filter(rows, "host", "edge")
    assert [row["alert_id"] for row in by_host] == ["disk:edge-1:/"]
    by_title = apply_incident_field_filter(rows, "title", "missing")
    assert [row["alert_id"] for row in by_title] == ["fleet:alpha:missing"]


def test_incident_host_display_na_for_monitor():
    monitor = {
        "source": "kontiki-monitor",
        "attributes": {"service_name": "alpha-service"},
    }
    disk = {
        "_producer_service": "host-check-service",
        "attributes": {"host": "edge-1"},
    }
    assert incident_host_display(monitor) == "N/A"
    assert incident_host_display(disk) == "edge-1"
    monitor["source"] = "kontiki-monitor"
    assert apply_incident_field_filter([monitor, disk], "host", "n/a") == [monitor]


def test_silenced_service_names():
    assert silenced_service_names([{"service_name": "alpha-service"}]) == {
        "alpha-service"
    }
    assert silenced_service_names([]) == set()
    assert silenced_service_names(None) == set()


def test_live_service_names_in_group_skips_down_and_other_groups():
    raw = {
        "alpha-service": {
            "a": {
                "status": "active",
                "metadata": {"group": "business"},
            },
            "b": {
                "status": "down",
                "metadata": {"group": "business"},
            },
        },
        "beta-service": {
            "c": {
                "status": "degraded",
                "metadata": {"group": "platform"},
            }
        },
        "gamma-service": {
            "d": {
                "status": "active",
                "metadata": {"group": "business"},
            }
        },
    }
    assert live_service_names_in_group(raw, "business") == [
        "alpha-service",
        "gamma-service",
    ]
    assert live_service_names_in_group(raw, "all") == [
        "alpha-service",
        "beta-service",
        "gamma-service",
    ]


def test_format_instance_unreachable_uses_short_id():
    uid = "11111111-2222-3333-4444-555555555555"
    assert format_instance_unreachable("host-check-service", uid) == (
        "host-check-service 111111112222 unreachable"
    )


def test_format_last_heartbeat_datetime():
    stamp = datetime(2026, 7, 15, 12, 2, tzinfo=timezone.utc)
    assert format_last_heartbeat(stamp) == "2026-07-15 12:02:00"


def test_fetch_open_alerts_concatenates_and_sorts(services):
    async def list_instances(name):
        if name == "kontiki-monitor":
            return ["mon-1"]
        if name == "host-check-service":
            return ["host-1"]
        return []

    services.services.list_instances = list_instances

    async def call(service_name, method_name, *args, instance_id=None, **kwargs):
        assert method_name == "list_open_alerts"
        if service_name == MONITOR_SERVICE_NAME:
            return [{"alert_id": "fleet:alpha:missing", "title": "missing"}]
        return [{"alert_id": "disk:edge-1:/mnt/root", "title": "disk"}]

    services.messenger.call = call
    alerts, registry_failed, instance_errors = asyncio.run(services.fetch_open_alerts())
    assert not registry_failed
    assert instance_errors == []
    assert [a["alert_id"] for a in alerts] == [
        "disk:edge-1:/mnt/root",
        "fleet:alpha:missing",
    ]
    assert alerts[0]["_producer_service"] == "host-check-service"
    assert alerts[0]["_producer_instance_id"] == "host-1"


def test_fetch_open_alerts_skips_empty_list_instances(services):
    services.services.list_instances = AsyncMock(return_value=[])
    alerts, registry_failed, instance_errors = asyncio.run(services.fetch_open_alerts())
    assert alerts == []
    assert not registry_failed
    assert instance_errors == []
    services.messenger.call.assert_not_called()
    assert services.services.list_instances.await_count == len(OPS_OPEN_ALERT_SOURCES)


def test_fetch_open_alerts_registry_failure(services):
    services.services.list_instances = AsyncMock(side_effect=RuntimeError("down"))
    alerts, registry_failed, instance_errors = asyncio.run(services.fetch_open_alerts())
    assert alerts == []
    assert registry_failed
    assert instance_errors == []


def test_fetch_open_alerts_keeps_other_instance_on_timeout(services):
    async def list_instances(name):
        if name == "kontiki-monitor":
            return ["mon-1", "mon-2"]
        return []

    services.services.list_instances = list_instances

    async def call(service_name, method_name, *args, instance_id=None, **kwargs):
        if instance_id == "mon-1":
            raise TimeoutError("rpc")
        return [{"alert_id": "exception:pay:abc"}]

    services.messenger.call = call
    alerts, registry_failed, instance_errors = asyncio.run(services.fetch_open_alerts())
    assert not registry_failed
    assert instance_errors == [("kontiki-monitor", "mon-1")]
    assert [a["alert_id"] for a in alerts] == ["exception:pay:abc"]


def test_build_silence_rows_joins_registry():
    silences = [
        {"service_name": "gone-service"},
        {"service_name": "alpha-service"},
    ]
    raw = {
        "alpha-service": {
            "a": {
                "status": "active",
                "metadata": {"group": "earth"},
            },
            "b": {
                "status": "down",
                "metadata": {"group": "earth"},
            },
        }
    }
    rows = build_silence_rows(silences, raw)
    assert [row["service_name"] for row in rows] == [
        "alpha-service",
        "gone-service",
    ]
    assert rows[0]["registry"] == "present"
    assert rows[0]["group"] == "earth"
    assert rows[0]["live"] == 1
    assert rows[1]["registry"] == "absent"
    assert rows[1]["group"] == "business"
    assert rows[1]["live"] == 0
    assert silence_matches_group(rows[0], "earth")
    assert not silence_matches_group(rows[0], "business")
    assert silence_matches_group(rows[1], "all")
    assert silence_matches_group(rows[1], "business")
    assert not silence_matches_group(rows[1], "earth")


def test_apply_silence_field_filter_registry():
    rows = [
        {"service_name": "alpha-service", "registry": "present", "group": "earth"},
        {"service_name": "gone-service", "registry": "absent", "group": "business"},
    ]
    assert apply_silence_field_filter(rows, "registry", "absent") == [rows[1]]
    assert apply_silence_field_filter(rows, "all", "") == rows


def test_orphan_silenced_count_and_warning():
    silenced = {"alpha-service", "gone-service"}
    raw = {
        "alpha-service": {
            "a": {"status": "down", "metadata": {"group": "earth"}},
        }
    }
    assert orphan_silenced_count(silenced, raw) == 1
    assert orphan_silenced_count(silenced, {}) == 2
    assert format_orphan_silence_warning(1) == ("1 unregistered service still silenced")
    assert format_orphan_silence_warning(2) == (
        "2 unregistered services still silenced"
    )


def test_fetch_silence_rows_ok(services):
    services.services.list_instances = AsyncMock(return_value=["mon-1"])
    services.services.get_services = AsyncMock(
        return_value={
            "alpha-service": {
                "a": {"status": "active", "metadata": {"group": "platform"}}
            }
        }
    )
    services.monitor = Mock()
    services.monitor.list_silences = AsyncMock(
        return_value=[{"service_name": "alpha-service"}]
    )
    rows, error = asyncio.run(services.fetch_silence_rows())
    assert error is None
    assert rows[0]["service_name"] == "alpha-service"
    assert rows[0]["registry"] == "present"


def test_fetch_silence_rows_monitor_missing(services):
    services.services.list_instances = AsyncMock(return_value=[])
    services.services.get_services = AsyncMock(return_value={})
    rows, error = asyncio.run(services.fetch_silence_rows())
    assert rows == []
    assert error == "monitor_missing"


def test_fetch_silence_rows_registry_failure(services):
    services.services.list_instances = AsyncMock(side_effect=RuntimeError("down"))
    rows, error = asyncio.run(services.fetch_silence_rows())
    assert rows == []
    assert error == "registry"
