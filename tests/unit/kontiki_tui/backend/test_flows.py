import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from kontiki_tui.backend.services import (
    Services,
    apply_flow_field_filter,
    build_flows,
    event_type_label,
    format_flow_index_time,
    format_hop_time,
    group_for_event,
)


@pytest.fixture
def services():
    return Services(messenger=Mock(name="messenger"))


def _hop(**overrides):
    hop = {
        "flow_id": "a1b2c3d4e5f6",
        "timestamp": "2026-09-18T09:14:01.120000+00:00",
        "event_type": "order.placed",
        "service_name": "OrderApi",
        "instance_id": "inst-order",
        "host": "box-1",
    }
    hop.update(overrides)
    return hop


def _registry():
    return {
        ("OrderApi", "inst-order"): "business",
        ("Billing", "inst-bill"): "platform",
        ("Notify", "inst-notify"): "business",
    }


def test_event_type_label_event_and_rpc():
    assert event_type_label({"event_type": "order.placed"}) == "order.placed"
    assert event_type_label({"remote_method": "charge"}) == "rpc:charge"
    assert event_type_label({"event_type": "x", "remote_method": "y"}) == "x"
    assert event_type_label({}) == ""


def test_format_hop_time():
    assert format_hop_time("2026-09-18T09:14:01.120000+00:00") == "09:14:01.12"
    assert format_hop_time("2026-09-18T09:14:01.400000+00:00") == "09:14:01.40"
    assert format_hop_time("") == ""
    assert format_hop_time(None) == ""


def test_format_flow_index_time_omits_today():
    now = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
    assert (
        format_flow_index_time("2026-09-18T08:22:19.745190+00:00", now=now)
        == "08:22:19"
    )
    assert (
        format_flow_index_time("2026-09-17T23:58:02+00:00", now=now)
        == "2026-09-17 23:58:02"
    )
    assert format_flow_index_time("", now=now) == ""
    assert format_flow_index_time(None, now=now) == ""


def test_group_for_event_join_and_fallback():
    mapping = _registry()
    assert group_for_event(_hop(), mapping) == "business"
    assert (
        group_for_event(_hop(service_name="Billing", instance_id="inst-bill"), mapping)
        == "platform"
    )
    assert group_for_event(_hop(service_name="Gone", instance_id="old"), mapping) == (
        "business"
    )
    assert group_for_event({"service_name": "ServiceRegistry"}, mapping) == "platform"


def test_build_flows_omits_blank_flow_id_and_groups_hops():
    events = [
        _hop(),
        _hop(
            timestamp="2026-09-18T09:14:01.400000+00:00",
            event_type="",
            remote_method="charge",
            service_name="Billing",
            instance_id="inst-bill",
            host="box-2",
        ),
        _hop(
            timestamp="2026-09-18T09:14:02.050000+00:00",
            event_type="",
            remote_method="send",
            service_name="Notify",
            instance_id="inst-notify",
            host="box-3",
        ),
        _hop(flow_id="", event_type="orphan"),
        _hop(flow_id=None, event_type="also-orphan"),
        _hop(
            flow_id="c9d0e1f2a3b4",
            timestamp="2026-09-18T09:13:58+00:00",
            event_type="",
            remote_method="send",
            service_name="Notify",
            instance_id="inst-notify",
        ),
    ]
    flows = build_flows(events, _registry(), group_filter="all")
    assert [flow["flow_id"] for flow in flows] == [
        "a1b2c3d4e5f6",
        "c9d0e1f2a3b4",
    ]
    chain = flows[0]
    assert len(chain["hops"]) == 3
    assert chain["groups"] == ("business", "platform")
    assert chain["origin"] == "OrderApi"
    assert chain["first_type"] == "order.placed"
    assert chain["hops"][1]["_group"] == "platform"
    assert chain["hops"][1]["remote_method"] == "charge"
    assert flows[1]["first_type"] == "rpc:send"
    assert len(flows[1]["hops"]) == 1


def test_build_flows_group_filter_keeps_full_chain():
    events = [
        _hop(),
        _hop(
            timestamp="2026-09-18T09:14:01.400000+00:00",
            event_type="",
            remote_method="charge",
            service_name="Billing",
            instance_id="inst-bill",
        ),
        _hop(
            flow_id="only-platform",
            timestamp="2026-09-18T09:10:00+00:00",
            event_type="infra.ping",
            service_name="Billing",
            instance_id="inst-bill",
        ),
    ]
    business = build_flows(events, _registry(), group_filter="business")
    assert [flow["flow_id"] for flow in business] == ["a1b2c3d4e5f6"]
    assert [hop["service_name"] for hop in business[0]["hops"]] == [
        "OrderApi",
        "Billing",
    ]

    platform = build_flows(events, _registry(), group_filter="platform")
    ids = [flow["flow_id"] for flow in platform]
    assert ids == ["a1b2c3d4e5f6", "only-platform"]
    assert len(platform[0]["hops"]) == 2


def test_apply_flow_field_filter():
    flows = build_flows(
        [
            _hop(),
            _hop(
                timestamp="2026-09-18T09:14:01.400000+00:00",
                event_type="",
                remote_method="charge",
                service_name="Billing",
                instance_id="inst-bill",
            ),
            _hop(
                flow_id="c9d0e1f2a3b4",
                timestamp="2026-09-18T09:13:58+00:00",
                event_type="",
                remote_method="send",
                service_name="Notify",
                instance_id="inst-notify",
            ),
        ],
        _registry(),
    )
    assert apply_flow_field_filter(flows, "all", "x") == flows
    by_id = apply_flow_field_filter(flows, "flow_id", "C9D0")
    assert [flow["flow_id"] for flow in by_id] == ["c9d0e1f2a3b4"]
    by_origin = apply_flow_field_filter(flows, "origin", "order")
    assert [flow["flow_id"] for flow in by_origin] == ["a1b2c3d4e5f6"]
    by_type = apply_flow_field_filter(flows, "event_type", "order")
    assert [flow["flow_id"] for flow in by_type] == ["a1b2c3d4e5f6"]
    by_service = apply_flow_field_filter(flows, "service_name", "billing")
    assert [flow["flow_id"] for flow in by_service] == ["a1b2c3d4e5f6"]
    by_group = apply_flow_field_filter(flows, "group", "platform")
    assert [flow["flow_id"] for flow in by_group] == ["a1b2c3d4e5f6"]


def test_get_flows_hides_internal_and_uses_unfiltered_events(services):
    raw = [
        _hop(),
        _hop(
            timestamp="2026-09-18T09:14:01.400000+00:00",
            event_type="",
            remote_method="charge",
            service_name="Billing",
            instance_id="inst-bill",
        ),
        _hop(
            flow_id="internal",
            service_name="ServiceRegistry",
            event_type="registry.instance.registered",
        ),
        _hop(flow_id="tui", service_name="kontiki_tui", event_type="rpc:get_events"),
        _hop(
            flow_id="census",
            remote_method="get_services",
            service_name="kontiki-monitor",
            event_type="",
        ),
    ]
    services.services.get_events = AsyncMock(return_value=raw)
    services.services.get_services = AsyncMock(
        return_value={
            "OrderApi": {
                "inst-order": {"metadata": {"group": "business"}},
            },
            "Billing": {
                "inst-bill": {"metadata": {"group": "platform"}},
            },
        }
    )
    out = asyncio.run(services.get_flows(group_filter="business"))
    assert len(out) == 1
    assert out[0]["flow_id"] == "a1b2c3d4e5f6"
    assert [hop["service_name"] for hop in out[0]["hops"]] == ["OrderApi", "Billing"]
