import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from kontiki.messaging.common import KONTIKI_SESSION_OPEN_RPC

from kontiki_tui.backend.services import (
    CONTEXT_EVENT_TYPE,
    KIND_CONTEXT,
    KIND_EXCEPTION,
    KIND_MESSAGE,
    Services,
    apply_flow_field_filter,
    build_flows,
    event_type_label,
    exception_type_label,
    export_tree_type_label,
    flatten_flow_tree,
    format_flow_index_time,
    format_hop_time,
    format_parent_delta,
    group_for_event,
    tree_row_type_label,
    tree_type_prefix,
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
    assert (
        event_type_label({"remote_method": "charge", "rpc_service": "Billing"})
        == "rpc:Billing.charge"
    )
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
    services.services.get_exceptions = AsyncMock(return_value=[])
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


def test_exception_type_label():
    assert exception_type_label(
        {"exception_type": "ValueError", "message": "boom"}
    ) == ("exc:ValueError: boom")
    assert (
        exception_type_label({"exception_type": "RuntimeError"}) == "exc:RuntimeError"
    )
    assert exception_type_label({}) == "exc:Exception"


def test_format_parent_delta():
    parent = "2026-09-18T09:14:01.000000+00:00"
    assert format_parent_delta("2026-09-18T09:14:01.020000+00:00", parent) == "+20ms"
    assert format_parent_delta("2026-09-18T09:14:00.920000+00:00", parent) == "-80ms"
    assert format_parent_delta(parent, parent) == "+0ms"
    assert format_parent_delta("", parent) == "—"
    assert format_parent_delta("2026-09-18T09:14:03.000000+00:00", parent) == "+2.0s"
    assert format_parent_delta("2026-09-18T09:14:13.000000+00:00", parent) == "+12s"


def test_tree_type_prefix():
    assert tree_type_prefix(0, KIND_MESSAGE) == ""
    assert tree_type_prefix(1, KIND_MESSAGE) == "  ↪️ "
    assert tree_type_prefix(1, KIND_MESSAGE, "+12ms") == "  ↪️  [+12ms] "
    assert tree_type_prefix(1, KIND_MESSAGE, "—") == "  ↪️ "
    assert tree_type_prefix(2, KIND_MESSAGE, "+1ms") == "    ↪️  [+1ms] "
    assert tree_type_prefix(1, KIND_EXCEPTION, "+4ms") == "  💥 "


def test_export_tree_type_label_repeats_marks():
    root = {
        "_kind": KIND_MESSAGE,
        "_depth": 0,
        "event_type": "order.placed",
    }
    child = {
        "_kind": KIND_MESSAGE,
        "_depth": 1,
        "_delta": "+12ms",
        "event_type": "chain.b",
    }
    grandchild = {
        "_kind": KIND_MESSAGE,
        "_depth": 2,
        "_delta": "+1ms",
        "event_type": "chain.c",
    }
    nested_exc = {
        "_kind": KIND_EXCEPTION,
        "_depth": 2,
        "exception_type": "ValueError",
        "message": "boom",
    }
    assert export_tree_type_label(root) == "order.placed"
    assert export_tree_type_label(child) == "↪️  [+12ms] chain.b"
    assert export_tree_type_label(grandchild) == "↪️↪️  [+1ms] chain.c"
    assert export_tree_type_label(nested_exc) == "↪️💥 exc:ValueError: boom"


def test_flatten_flow_tree_parent_children_and_exception():
    mapping = _registry()
    hops = [
        _hop(hop_id="h1", timestamp="2026-09-18T09:14:01.000000+00:00"),
        _hop(
            hop_id="h2",
            parent_hop_id="h1",
            timestamp="2026-09-18T09:14:01.040000+00:00",
            event_type="notify.requested",
            service_name="Notify",
            instance_id="inst-notify",
        ),
        _hop(
            hop_id="h3",
            parent_hop_id="h1",
            timestamp="2026-09-18T09:14:01.030000+00:00",
            event_type="notify.requested",
            service_name="Billing",
            instance_id="inst-bill",
        ),
    ]
    annotated = []
    for hop in hops:
        row = dict(hop)
        row["_group"] = group_for_event(hop, mapping)
        annotated.append(row)
    exc = {
        "flow_id": "a1b2c3d4e5f6",
        "hop_id": "h1",
        "timestamp": "2026-09-18T09:14:01.035000+00:00",
        "service_name": "Notify",
        "instance_id": "inst-notify",
        "exception_type": "ValueError",
        "message": "boom",
    }
    rows = flatten_flow_tree(annotated, [exc], mapping)
    # One chronological sequence per hop: h1's block is
    # [child h3 (.03), exception (.035), child h2 (.04)].
    assert [row["service_name"] for row in rows] == [
        "OrderApi",
        "Billing",
        "Notify",
        "Notify",
    ]
    assert rows[0]["_depth"] == 0
    assert rows[0]["_delta"] == "—"
    assert tree_row_type_label(rows[0]) == "order.placed"
    assert rows[1]["_depth"] == 1
    assert rows[1]["_delta"] == "+30ms"
    assert tree_row_type_label(rows[1]) == "  ↪️  [+30ms] notify.requested"
    assert rows[2]["_kind"] == "exception"
    assert rows[2]["_depth"] == 1
    assert rows[2]["_delta"] == "—"
    assert tree_row_type_label(rows[2]) == "  💥 exc:ValueError: boom"
    assert rows[3]["_kind"] == "message"
    assert rows[3]["_depth"] == 1
    assert rows[3]["_delta"] == "+40ms"
    assert tree_row_type_label(rows[3]) == "  ↪️  [+40ms] notify.requested"


def test_flatten_without_hop_id_is_chrono():
    hops = [
        _hop(),
        _hop(
            timestamp="2026-09-18T09:14:01.400000+00:00",
            service_name="Billing",
            instance_id="inst-bill",
        ),
    ]
    rows = flatten_flow_tree(hops, [], _registry())
    assert [row["_depth"] for row in rows] == [0, 0]
    assert [row["_delta"] for row in rows] == ["—", "—"]


def test_get_flows_hides_session_open(services):
    raw = [
        _hop(),
        _hop(
            flow_id="session",
            event_type="",
            remote_method=KONTIKI_SESSION_OPEN_RPC,
            service_name="OrderApi",
            instance_id="inst-order",
        ),
    ]
    services.services.get_events = AsyncMock(return_value=raw)
    services.services.get_exceptions = AsyncMock(return_value=[])
    services.services.get_services = AsyncMock(
        return_value={
            "OrderApi": {
                "inst-order": {"metadata": {"group": "business"}},
            },
        }
    )
    out = asyncio.run(services.get_flows(group_filter="all"))
    assert len(out) == 1
    assert out[0]["flow_id"] == "a1b2c3d4e5f6"
    assert len(out[0]["hops"]) == 1


def test_get_flows_keeps_context_records(services):
    raw = [
        _hop(hop_id="h1"),
        {
            "flow_id": "a1b2c3d4e5f6",
            "hop_id": "h1",
            "timestamp": "2026-09-18T09:14:01.200000+00:00",
            "event_type": CONTEXT_EVENT_TYPE,
            "service_name": "OrderApi",
            "instance_id": "inst-order",
            "context_id": "ctx-1",
            "context": {"k": 1},
        },
    ]
    services.services.get_events = AsyncMock(return_value=raw)
    services.services.get_exceptions = AsyncMock(return_value=[])
    services.services.get_services = AsyncMock(
        return_value={
            "OrderApi": {
                "inst-order": {"metadata": {"group": "business"}},
            },
        }
    )
    out = asyncio.run(services.get_flows(group_filter="all"))
    assert [row["_kind"] for row in out[0]["tree_rows"]] == [KIND_MESSAGE, KIND_CONTEXT]
