from kontiki_tui.backend.export import render_flow
from kontiki_tui.backend.services import (
    CONTEXT_EVENT_TYPE,
    KIND_CONTEXT,
    KIND_MESSAGE,
    build_flows,
    context_count_label,
    export_tree_type_label,
    flatten_flow_tree,
    group_for_event,
    is_context_event,
    tree_row_type_label,
)


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


def _context(**overrides):
    context = {
        "flow_id": "a1b2c3d4e5f6",
        "hop_id": "h1",
        "timestamp": "2026-09-18T09:14:01.200000+00:00",
        "event_type": CONTEXT_EVENT_TYPE,
        "service_name": "Notify",
        "instance_id": "inst-notify",
        "context_id": "ctx-1",
        "entrypoint": "event",
        "operation": "notify.requested",
        "context": {"key": "value"},
    }
    context.update(overrides)
    return context


def _registry():
    return {
        ("OrderApi", "inst-order"): "business",
        ("Notify", "inst-notify"): "business",
    }


def _annotated(hops, mapping):
    rows = []
    for hop in hops:
        row = dict(hop)
        row["_group"] = group_for_event(hop, mapping)
        rows.append(row)
    return rows


def test_is_context_event():
    assert is_context_event(_context())
    assert not is_context_event(_hop())
    assert not is_context_event(_context(event_type="other.recorded"))


def test_build_flows_splits_context_events_out_of_hops():
    events = [
        _hop(hop_id="h1"),
        _hop(
            hop_id="h2",
            parent_hop_id="h1",
            timestamp="2026-09-18T09:14:01.400000+00:00",
            event_type="notify.requested",
            service_name="Notify",
            instance_id="inst-notify",
        ),
        _context(hop_id="h1"),
        _context(
            hop_id="h2",
            context_id="ctx-9",
            timestamp="2026-09-18T09:14:01.500000+00:00",
        ),
    ]
    flows = build_flows(events, _registry())
    assert len(flows) == 1
    flow = flows[0]
    assert [hop["event_type"] for hop in flow["hops"]] == [
        "order.placed",
        "notify.requested",
    ]
    kinds = [row.get("_kind") for row in flow["tree_rows"]]
    assert kinds == [KIND_MESSAGE, KIND_CONTEXT, KIND_MESSAGE, KIND_CONTEXT]
    assert flow["tree_rows"][0]["hop_id"] == "h1"
    # One chronological sequence per hop: h1's block is [ctx h1 (.20),
    # child h2 (.40)], then h2's block contains its own context (.50).
    assert tree_row_type_label(flow["tree_rows"][1]) == ("  💡 1 context value [ctx-1]")
    assert tree_row_type_label(flow["tree_rows"][2]) == (
        "  ↪  [+280ms] notify.requested"
    )
    assert tree_row_type_label(flow["tree_rows"][3]) == (
        "    💡 1 context value [ctx-9]"
    )


def test_context_annotation_aggregates_and_keeps_order():
    contexts = [
        _context(
            timestamp="2026-09-18T09:14:01.500000+00:00",
            context_id="ctx-2",
            context={"second": True},
        ),
        _context(timestamp="2026-09-18T09:14:01.200000+00:00"),
    ]
    hops = _annotated([_hop(hop_id="h1")], _registry())
    rows = flatten_flow_tree(hops, [], _registry(), contexts)
    assert len(rows) == 2
    annotation = rows[1]
    assert annotation["_kind"] == KIND_CONTEXT
    assert annotation["_depth"] == 1
    assert annotation["_delta"] == "—"
    assert annotation["_contexts"] == [
        contexts[1],
        contexts[0],
    ]
    assert context_count_label(annotation) == "2 context values [ctx-1, ctx-2]"
    assert tree_row_type_label(annotation) == ("  💡 2 context values [ctx-1, ctx-2]")


def test_same_hop_annotations_sorted_by_timestamp():
    hops = _annotated([_hop(hop_id="h1")], _registry())
    exc = {
        "flow_id": "a1b2c3d4e5f6",
        "hop_id": "h1",
        "timestamp": "2026-09-18T09:14:01.300000+00:00",
        "service_name": "Notify",
        "instance_id": "inst-notify",
        "exception_type": "ValueError",
        "message": "boom",
    }
    # Context recorded at .20, exception at .30: chronological order in
    # h1's block, whatever the annotation kind.
    rows = flatten_flow_tree(hops, [exc], _registry(), [_context()])
    assert [row["_kind"] for row in rows] == [KIND_MESSAGE, KIND_CONTEXT, "exception"]


def test_context_with_unknown_hop_id_stays_out_of_the_tree():
    hops = _annotated([_hop(hop_id="h1")], _registry())
    rows = flatten_flow_tree(
        hops, [], _registry(), [_context(hop_id="gone"), _context(hop_id="")]
    )
    assert [row["_kind"] for row in rows] == [KIND_MESSAGE]


def test_build_flows_drops_context_without_flow_id():
    events = [
        _hop(hop_id="h1"),
        _context(flow_id=""),
    ]
    flows = build_flows(events, _registry())
    assert len(flows) == 1
    assert [row["_kind"] for row in flows[0]["tree_rows"]] == [KIND_MESSAGE]


def test_export_tree_type_label_context():
    row = {
        "_kind": KIND_CONTEXT,
        "_depth": 2,
        "_contexts": [
            {"context_id": "c1", "context": {"a": 1}},
            {"context_id": "c2", "context": {"b": 2}},
            {"context_id": "c3", "context": {"c": 3}},
        ],
    }
    assert export_tree_type_label(row) == "↪💡 3 context values [c1, c2, c3]"
    assert (
        export_tree_type_label({**row, "_depth": 0}) == "3 context values [c1, c2, c3]"
    )


def _flow_with_context():
    hops = [_hop(hop_id="h1")]
    contexts = [_context()]
    rows = flatten_flow_tree(_annotated(hops, _registry()), [], _registry(), contexts)
    return build_flows(hops + contexts, _registry())[0], rows


def test_render_flow_contexts_section():
    flow, tree_rows = _flow_with_context()
    flow["tree_rows"] = tree_rows
    text = render_flow(flow)
    assert (
        "| 09:14:01.20 | business | Notify | instnotify |"
        " 💡 1 context value [ctx-1] | — |\n" in text
    )
    assert (
        "## Contexts\n\n### [ctx-1] - Notify: notify.requested\n\n"
        "| Key | Value |\n| --- | --- |\n| **key** | value |\n" in text
    )


def test_render_flow_without_contexts_has_no_section():
    flow = build_flows([_hop(hop_id="h1")], _registry())[0]
    assert "## Contexts" not in render_flow(flow)


def test_context_count_label_non_dict_payload_counts_one():
    row = {"_contexts": [{"context": "a plain string"}, {"context": {"a": 1, "b": 2}}]}
    assert context_count_label(row) == "3 context values"
