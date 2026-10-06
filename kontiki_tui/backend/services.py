import logging
from datetime import datetime, timezone

from kontiki.messaging import RpcProxy
from kontiki.messaging.common import KONTIKI_SESSION_OPEN_RPC
from kontiki.messaging.flow import short_instance_id
from kontiki.registry import ServiceRegistryProxy

from kontiki_tui.backend.log import instance_log_files, instance_log_stem

OPS_OPEN_ALERT_SOURCES = ("kontiki-monitor", "host-check-service")
MONITOR_SERVICE_NAME = "kontiki-monitor"
CENSUS_REMOTE_METHODS = frozenset(
    (
        "get_services",
        "list_instances",
        "get_events",
        "get_filtered_events",
        "get_exceptions",
        "get_filtered_exceptions",
        "list_silences",
        "list_open_alerts",
        "list_failed_messages",
        "replay_failed_messages",
        "drop_failed_messages",
    )
)


def normalize_registration_group(group):
    """Treat missing / null / blank group as business (reader-side contract)."""
    if group is None:
        return "business"
    if not isinstance(group, str):
        return "business"
    stripped = group.strip()
    if not stripped:
        return "business"
    return stripped


def matches_group_filter(group, group_filter):
    """Return True if an instance group should appear for the current filter.

    group_filter is ``all`` (every group) or a concrete group name (e.g.
    ``business``, ``platform``).
    """
    if group_filter == "all":
        return True
    return normalize_registration_group(group) == group_filter


def implied_platform_group(service_name):
    """Return ``platform`` for infra that does not self-register, else None.

    The registry process starts with registration disabled. Its logs still
    follow Kontiki naming (``ServiceRegistry-<12hex>.log``) and would otherwise
    fall back to business.
    """
    if service_name == "ServiceRegistry":
        return "platform"
    return None


def event_flow_id(event):
    raw = event.get("flow_id")
    if raw is None:
        return ""
    return str(raw).strip()


def event_hop_id(event):
    raw = event.get("hop_id")
    if raw is None:
        return ""
    return str(raw).strip()


def event_parent_hop_id(event):
    raw = event.get("parent_hop_id")
    if raw is None:
        return ""
    return str(raw).strip()


def event_type_label(event):
    event_type = str(event.get("event_type", "") or "").strip()
    if event_type:
        return event_type
    remote_method = str(event.get("remote_method", "") or "").strip()
    if not remote_method:
        return ""
    rpc_service = str(event.get("rpc_service", "") or "").strip()
    if rpc_service:
        return "rpc:%s.%s" % (rpc_service, remote_method)
    return "rpc:%s" % remote_method


def exception_type_label(exc):
    exc_type = str(exc.get("exception_type") or "").strip() or "Exception"
    message = str(exc.get("message") or "").strip()
    if message:
        return "exc:%s: %s" % (exc_type, message)
    return "exc:%s" % exc_type


KIND_MESSAGE = "message"
KIND_EXCEPTION = "exception"
KIND_CONTEXT = "context"
TREE_CHILD_MARK = "↪️"
TREE_EXCEPTION_MARK = "💥"
TREE_CONTEXT_MARK = "💡"

# Registry 2.0 ActivityTracker context records carried in the event timeline.
CONTEXT_EVENT_TYPE = "registry.context.recorded"


def is_context_event(event):
    """True for a ``registry.context.recorded`` timeline entry."""
    return str(event.get("event_type", "") or "").strip() == CONTEXT_EVENT_TYPE


def context_count_label(row):
    """Annotation label for the contexts of one hop.

    Counts the values the tooltip shows: top-level keys of each context
    payload, 1 for a non-object payload, summed across the hop's records.
    The record ids follow in brackets, comma-separated, so the row can be
    referenced from the export's Contexts section.
    """
    records = row.get("_contexts") or []
    total = 0
    ids = []
    for record in records:
        context = record.get("context")
        if isinstance(context, dict):
            total += len(context)
        else:
            total += 1
        context_id = str(record.get("context_id") or "").strip()
        if context_id:
            ids.append(context_id)
    label = "%d context value%s" % (total, "" if total == 1 else "s")
    if ids:
        label = "%s [%s]" % (label, ", ".join(ids))
    return label


def tree_type_prefix(depth, kind, delta=""):
    """Indent + emoji for Type when depth >= 1. Roots stay unmarked."""
    if not depth:
        return ""
    indent = "  " * int(depth)
    if kind == KIND_EXCEPTION:
        return "%s%s " % (indent, TREE_EXCEPTION_MARK)
    if kind == KIND_CONTEXT:
        return "%s%s " % (indent, TREE_CONTEXT_MARK)
    mark = TREE_CHILD_MARK
    text = str(delta or "").strip()
    if text and text != "—":
        return "%s%s  [%s] " % (indent, mark, text)
    return "%s%s " % (indent, mark)


def tree_row_type_label(row):
    if row.get("_kind") == KIND_EXCEPTION:
        base = exception_type_label(row)
    elif row.get("_kind") == KIND_CONTEXT:
        base = context_count_label(row)
    else:
        base = event_type_label(row)
    return (
        tree_type_prefix(row.get("_depth") or 0, row.get("_kind"), row.get("_delta"))
        + base
    )


def export_tree_type_label(row):
    """Type label for Markdown tables: repeat ↪️ by depth (spaces collapse in GFM)."""
    if row.get("_kind") == KIND_EXCEPTION:
        base = exception_type_label(row)
    elif row.get("_kind") == KIND_CONTEXT:
        base = context_count_label(row)
    else:
        base = event_type_label(row)
    depth = int(row.get("_depth") or 0)
    if not depth:
        return base
    if row.get("_kind") == KIND_EXCEPTION:
        marks = TREE_CHILD_MARK * (depth - 1) + TREE_EXCEPTION_MARK
        return "%s %s" % (marks, base)
    if row.get("_kind") == KIND_CONTEXT:
        marks = TREE_CHILD_MARK * (depth - 1) + TREE_CONTEXT_MARK
        return "%s %s" % (marks, base)
    marks = TREE_CHILD_MARK * depth
    text = str(row.get("_delta") or "").strip()
    if text and text != "—":
        return "%s  [%s] %s" % (marks, text, base)
    return "%s %s" % (marks, base)


def event_timestamp_sort_key(event):
    timestamp = str(event.get("timestamp", "") or "").strip()
    if not timestamp:
        return float("-inf")
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()


def format_hop_time(timestamp):
    """Hop clock as ``HH:MM:SS.ff`` (centiseconds)."""
    if timestamp is None:
        return ""
    text = str(timestamp).strip()
    if not text:
        return ""
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    hundredths = parsed.microsecond // 10000
    return "%s.%02d" % (parsed.strftime("%H:%M:%S"), hundredths)


def parse_event_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_parent_delta(child_timestamp, parent_timestamp):
    """Clock gap vs parent emission. Not a handler duration."""
    child = parse_event_timestamp(child_timestamp)
    parent = parse_event_timestamp(parent_timestamp)
    if child is None or parent is None:
        return "—"
    delta = (child - parent).total_seconds()
    sign = "+" if delta >= 0 else "-"
    mag = abs(delta)
    if mag < 1:
        return "%s%dms" % (sign, int(round(mag * 1000)))
    if mag < 10:
        return "%s%.1fs" % (sign, mag)
    if mag < 60:
        return "%s%ds" % (sign, int(round(mag)))
    if mag < 3600:
        return "%s%dm" % (sign, int(round(mag / 60)))
    return "%s%dh" % (sign, int(round(mag / 3600)))


def format_flow_index_time(timestamp, now=None):
    """Last/Started: ``HH:MM:SS`` if UTC today, else ``YYYY-MM-DD HH:MM:SS``."""
    full = format_last_heartbeat(timestamp)
    if not full:
        return ""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    prefix = today + " "
    if full.startswith(prefix):
        return full[len(prefix) :]
    return full


def instance_id_filter_matches(instance_id, expected):
    """True if ``expected`` is a substring of the full id or the 12-hex short id."""
    needle = str(expected or "").lower()
    if not needle:
        return True
    raw = str(instance_id or "")
    return needle in raw.lower() or needle in short_instance_id(raw).lower()


def group_for_event(event, instance_group_map):
    """Registry group of an event emitter, or ``business`` if unknown."""
    service_name = event.get("service_name")
    implied = implied_platform_group(service_name)
    if implied:
        return implied
    key = (service_name, event.get("instance_id"))
    return instance_group_map.get(key, "business")


def flow_touches_group(hop_groups, group_filter):
    """True if a flow belongs in the session slice (any hop in the group)."""
    if group_filter == "all":
        return True
    return any(matches_group_filter(group, group_filter) for group in hop_groups)


def _tree_node_from_hop(hop):
    row = dict(hop)
    row["_kind"] = KIND_MESSAGE
    return row


def _tree_node_from_exception(exc, instance_group_map):
    row = dict(exc)
    row["_kind"] = KIND_EXCEPTION
    row["_group"] = group_for_event(exc, instance_group_map)
    return row


def _tree_node_from_context(contexts, instance_group_map):
    """One annotation row aggregating every context record of a hop.

    ``_contexts`` keeps the records in timestamp order; the row itself
    carries the fields of the first one (service, instance, timestamps).
    """
    first = contexts[0]
    row = dict(first)
    row["_kind"] = KIND_CONTEXT
    row["_group"] = group_for_event(first, instance_group_map)
    row["_contexts"] = list(contexts)
    return row


def flatten_flow_tree(hops, exceptions, instance_group_map, contexts=None):
    """DFS rows for the Messages pane. Depth 0 when no hop_id is present.

    Exceptions and context records are annotations, not hops: they attach
    under the hop whose ``hop_id`` they carry, at the same depth as its
    message children. All rows of one hop (children, exceptions, context
    annotations) form one timestamp-ordered sequence, so the Time column
    stays readable. All contexts of one hop aggregate into a single
    annotation row; the records themselves stay on that row in
    ``_contexts``.
    """
    hops = hops or []
    by_id = {}
    for hop in hops:
        hop_id = event_hop_id(hop)
        if hop_id:
            by_id[hop_id] = hop

    if not by_id:
        rows = []
        for hop in hops:
            node = _tree_node_from_hop(hop)
            node["_depth"] = 0
            node["_delta"] = "—"
            rows.append(node)
        return rows

    message_children = {}
    exception_children = {}
    context_children = {}
    roots = []
    for hop in hops:
        node = _tree_node_from_hop(hop)
        parent_id = event_parent_hop_id(hop)
        if parent_id and parent_id in by_id:
            message_children.setdefault(parent_id, []).append(node)
        else:
            roots.append(node)

    for exc in exceptions or []:
        parent_id = event_hop_id(exc)
        if parent_id and parent_id in by_id:
            exception_children.setdefault(parent_id, []).append(
                _tree_node_from_exception(exc, instance_group_map)
            )

    for context in contexts or []:
        parent_id = event_hop_id(context)
        if parent_id and parent_id in by_id:
            context_children.setdefault(parent_id, []).append(context)

    for key in message_children:
        message_children[key].sort(key=event_timestamp_sort_key)
    for key in exception_children:
        exception_children[key].sort(key=event_timestamp_sort_key)
    for key in context_children:
        context_children[key].sort(key=event_timestamp_sort_key)
    roots.sort(key=event_timestamp_sort_key)

    rows = []

    def walk(node, parent_node, depth):
        row = dict(node)
        row["_depth"] = depth
        if row.get("_kind") in (KIND_EXCEPTION, KIND_CONTEXT) or parent_node is None:
            row["_delta"] = "—"
        else:
            row["_delta"] = format_parent_delta(
                node.get("timestamp"), parent_node.get("timestamp")
            )
        rows.append(row)
        if row.get("_kind") != KIND_MESSAGE:
            return
        hop_id = event_hop_id(row)
        kids = list(message_children.get(hop_id) or [])
        kids.extend(exception_children.get(hop_id) or [])
        attached = context_children.get(hop_id)
        if attached:
            context_node = _tree_node_from_context(attached, instance_group_map)
            kids.append(context_node)
        # One chronological sequence per hop: children, exceptions and
        # context annotations share the depth, ordered by timestamp.
        kids.sort(key=event_timestamp_sort_key)
        for kid in kids:
            walk(kid, row, depth + 1)

    for root in roots:
        walk(root, None, 0)
    return rows


def build_flows(events, instance_group_map, group_filter="all", exceptions=None):
    """Group tracker events by ``flow_id`` (omit blank ids).

    ``registry.context.recorded`` timeline entries are not hops: they are
    split out here and attached to their hop in ``flatten_flow_tree``.
    """
    buckets = {}
    context_buckets = {}
    for event in events or []:
        flow_id = event_flow_id(event)
        if not flow_id:
            continue
        if is_context_event(event):
            context_buckets.setdefault(flow_id, []).append(event)
            continue
        buckets.setdefault(flow_id, []).append(event)

    flows = []
    for flow_id, hops in buckets.items():
        hops_sorted = sorted(hops, key=event_timestamp_sort_key)
        groups = []
        annotated = []
        for hop in hops_sorted:
            group = group_for_event(hop, instance_group_map)
            row = dict(hop)
            row["_group"] = group
            annotated.append(row)
            if group not in groups:
                groups.append(group)
        if not flow_touches_group(groups, group_filter):
            continue
        first = annotated[0]
        last = annotated[-1]
        origin = str(first.get("service_name", "") or "").strip()
        flow_exceptions = []
        for exc in exceptions or []:
            if event_flow_id(exc) == flow_id:
                flow_exceptions.append(exc)
        flows.append(
            {
                "flow_id": flow_id,
                "hops": annotated,
                "tree_rows": flatten_flow_tree(
                    annotated,
                    flow_exceptions,
                    instance_group_map,
                    context_buckets.get(flow_id),
                ),
                "groups": tuple(groups),
                "origin": origin,
                "first_type": event_type_label(first),
                "started": first.get("timestamp", "") or "",
                "last": last.get("timestamp", "") or "",
            }
        )
    flows.sort(
        key=lambda flow: event_timestamp_sort_key({"timestamp": flow["last"]}),
        reverse=True,
    )
    return flows


def apply_flow_field_filter(flows, field, value):
    if not field or field == "all" or not value:
        return list(flows)
    expected = value.lower()
    matched = []
    for flow in flows:
        if field == "flow_id":
            haystack = str(flow.get("flow_id", "") or "")
        elif field == "origin":
            haystack = str(flow.get("origin", "") or "")
        elif field == "event_type":
            haystack = str(flow.get("first_type", "") or "")
        elif field == "service_name":
            if any(
                expected in str(hop.get("service_name", "") or "").lower()
                for hop in flow.get("hops") or []
            ):
                matched.append(flow)
            continue
        elif field == "group":
            groups = flow.get("groups") or ()
            if any(expected in str(group).lower() for group in groups):
                matched.append(flow)
            continue
        else:
            haystack = ""
        if expected in haystack.lower():
            matched.append(flow)
    return matched


def group_filter_select_options(discovered_groups):
    """Build Select options: All first, then groups seen in the registry."""
    options = [("All", "all")]
    for name in sorted(set(discovered_groups or [])):
        options.append((name, name))
    return options


class Services:
    def __init__(self, messenger):
        self.messenger = messenger
        self.services = ServiceRegistryProxy(messenger)
        self.monitor = RpcProxy(messenger, service_name=MONITOR_SERVICE_NAME)

    async def get_services(self):
        return await self.services.get_services()

    async def list_failed_messages(self, service_name, name, limit):
        return await self.services.list_failed_messages(
            service_name=service_name, name=name, limit=limit
        )

    async def replay_failed_messages(self, service_name, name, count):
        return await self.services.replay_failed_messages(
            service_name=service_name, name=name, count=count
        )

    async def drop_failed_messages(self, service_name, name, count):
        return await self.services.drop_failed_messages(
            service_name=service_name, name=name, count=count
        )

    async def list_registration_groups(self):
        """Return sorted group names discovered in the live registry."""
        instance_group_map = await self._build_instance_group_map()
        return sorted(set(instance_group_map.values()))

    def _is_internal_registry_event(self, event: dict) -> bool:
        """True for TUI observer traffic, Registry bookkeeping, and census RPCs.

        Domain publishes and other RPC calls stay visible.
        """
        service_name = event.get("service_name")
        if isinstance(service_name, str) and (
            "kontiki_tui" in service_name or service_name == "ServiceRegistry"
        ):
            return True
        method = str(event.get("remote_method") or "").strip()
        return method == KONTIKI_SESSION_OPEN_RPC or method in CENSUS_REMOTE_METHODS

    def _filter_registry_events(
        self, events: list[dict], include_internal: bool = False
    ) -> list[dict]:
        if include_internal:
            return events
        return [
            event for event in events if not self._is_internal_registry_event(event)
        ]

    async def _build_instance_group_map(self) -> dict:
        """Return {(service_name, instance_id): group} from the live registry.

        Used to apply group_filter to events, exceptions, and log filenames.
        Instances whose group cannot be resolved are mapped to "business"
        (reader-side contract, aligned with normalize_registration_group).
        """
        try:
            raw = await self.services.get_services()
        except Exception as e:
            logging.getLogger("kontiki_tui").warning(
                "Could not fetch services for group map: %s", e
            )
            return {}
        result = {}
        for service_name, instances in raw.items():
            if not isinstance(instances, dict):
                continue
            for instance_id, entry in instances.items():
                if not isinstance(entry, dict):
                    continue
                metadata = entry.get("metadata", {}) or {}
                group = normalize_registration_group(metadata.get("group"))
                result[(service_name, instance_id)] = group
        return result

    def _group_for_event(self, event: dict, instance_group_map: dict) -> str:
        """Resolve the group of an event via the registry map.

        Falls back to ``business`` when the instance is unknown (e.g. already
        deregistered) so that historical business events remain visible.
        ``ServiceRegistry`` is platform (it does not self-register).
        """
        return group_for_event(event, instance_group_map)

    async def get_events(
        self,
        include_internal: bool = False,
        group_filter: str = "all",
        include_contexts=False,
    ) -> list[dict]:
        events = await self.services.get_events()
        events = self._filter_registry_events(events, include_internal=include_internal)
        if not include_contexts:
            events = [event for event in events if not is_context_event(event)]
        if group_filter == "all":
            return events
        instance_group_map = await self._build_instance_group_map()
        return [
            e
            for e in events
            if matches_group_filter(
                self._group_for_event(e, instance_group_map), group_filter
            )
        ]

    async def get_flows(self, group_filter="all"):
        """Build flow rows from tracker events (full chain, slice by hop group)."""
        events = await self.get_events(group_filter="all", include_contexts=True)
        instance_group_map = await self._build_instance_group_map()
        exceptions = await self.get_exceptions(group_filter="all")
        return build_flows(events, instance_group_map, group_filter, exceptions)

    async def get_filtered_events(
        self,
        filter_field: str,
        value,
        include_internal: bool = False,
        group_filter: str = "all",
    ) -> list[dict]:
        events = await self.services.get_filtered_events(filter_field, value)
        events = self._filter_registry_events(events, include_internal=include_internal)
        events = [event for event in events if not is_context_event(event)]
        if group_filter == "all":
            return events
        instance_group_map = await self._build_instance_group_map()
        return [
            e
            for e in events
            if matches_group_filter(
                self._group_for_event(e, instance_group_map), group_filter
            )
        ]

    async def get_exceptions(self, group_filter: str = "all") -> list[dict]:
        exceptions = await self.services.get_exceptions()
        if group_filter == "all":
            return exceptions
        instance_group_map = await self._build_instance_group_map()
        return [
            exc
            for exc in exceptions
            if matches_group_filter(
                self._group_for_event(exc, instance_group_map), group_filter
            )
        ]

    async def get_filtered_exceptions(
        self, filter_field: str, value, group_filter: str = "all"
    ) -> list[dict]:
        exceptions = await self.services.get_filtered_exceptions(filter_field, value)
        if group_filter == "all":
            return exceptions
        instance_group_map = await self._build_instance_group_map()
        return [
            exc
            for exc in exceptions
            if matches_group_filter(
                self._group_for_event(exc, instance_group_map), group_filter
            )
        ]

    async def get_log_files_for_group(
        self, log_directory: str, group_filter: str
    ) -> list[str]:
        """Return log files for registry instances matching ``group_filter``.

        Requires Kontiki >=1.8.1 naming: ``{service_name}-{12hex}.log`` and
        numeric RotatingFileHandler backups (``.log.N``). Oldest rotation
        first, current file last, per instance. The set is the live registry
        (any status), then the session group. Leftover files from
        deregistered instances, dated TimedRotating suffixes, non-Kontiki
        names, and ``ServiceRegistry-*.log`` (not in the registry) are omitted.
        """
        import os

        if not log_directory or not os.path.isdir(log_directory):
            return []

        instance_group_map = await self._build_instance_group_map()
        keys = []
        for (svc, inst_id), group in instance_group_map.items():
            if not matches_group_filter(group, group_filter):
                continue
            keys.append((svc, inst_id))
        keys.sort(key=lambda item: instance_log_stem(item[0], item[1]))
        result = []
        for svc, inst_id in keys:
            result.extend(instance_log_files(log_directory, svc, inst_id))
        return result

    async def fetch_open_alerts(self):
        """Load open NormalizedAlerts from ops producers.

        Returns ``(alerts, registry_failed, instance_errors)``.
        ``instance_errors`` is a list of ``(service_name, instance_id)``.
        ``list_instances`` ``[]`` skips that name. A registry RPC failure
        sets ``registry_failed``; alerts already fetched are kept.
        """
        alerts = []
        registry_failed = False
        instance_errors = []
        for source in OPS_OPEN_ALERT_SOURCES:
            try:
                ids = await self.services.list_instances(source)
            except Exception as exc:
                logging.getLogger("kontiki_tui").warning(
                    "list_instances failed for %s: %s", source, exc
                )
                registry_failed = True
                break
            for instance_id in ids or []:
                try:
                    proxy = RpcProxy(
                        self.messenger,
                        service_name=source,
                        instance_id=instance_id,
                    )
                    raw = await proxy.list_open_alerts()
                except Exception as exc:
                    logging.getLogger("kontiki_tui").warning(
                        "list_open_alerts failed for %s %s: %s",
                        source,
                        instance_id,
                        exc,
                    )
                    instance_errors.append((source, instance_id))
                    continue
                for item in raw or []:
                    alert = alert_to_dict(item)
                    alert["_producer_service"] = source
                    alert["_producer_instance_id"] = instance_id
                    alerts.append(alert)
        alerts.sort(key=lambda alert: str(alert.get("alert_id") or ""))
        return alerts, registry_failed, instance_errors

    async def list_monitor_instances(self):
        return await self.services.list_instances(MONITOR_SERVICE_NAME)

    async def list_instances(self, service_name):
        return await self.services.list_instances(service_name)

    async def instance_groups(self):
        return await self._build_instance_group_map()

    async def list_silences(self):
        return await self.monitor.list_silences()

    async def fetch_silence_rows(self):
        """Load silence rows joined with the registry.

        Returns ``(rows, error)``. ``error`` is ``None``, ``"registry"``,
        ``"monitor_missing"``, or ``"monitor_unreachable"``.
        """
        try:
            ids = await self.services.list_instances(MONITOR_SERVICE_NAME)
            raw_services = await self.services.get_services()
        except Exception as exc:
            logging.getLogger("kontiki_tui").warning(
                "registry RPC failed while listing silences: %s", exc
            )
            return [], "registry"
        if not ids:
            return [], "monitor_missing"
        try:
            silences = await self.monitor.list_silences()
        except Exception as exc:
            logging.getLogger("kontiki_tui").warning("list_silences failed: %s", exc)
            return [], "monitor_unreachable"
        return build_silence_rows(silences, raw_services), None

    async def add_silence(self, service_name):
        return await self.monitor.add_silence(service_name=service_name)

    async def clear_silence(self, service_name):
        return await self.monitor.clear_silence(service_name=service_name)


def alert_to_dict(alert):
    """Normalize a list_open_alerts item to a plain dict."""
    if isinstance(alert, dict):
        return dict(alert)
    return alert.model_dump(mode="json")


def display_alert_dict(alert):
    """NormalizedAlert fields only (drop TUI producer keys)."""
    return {key: value for key, value in alert.items() if not str(key).startswith("_")}


def group_for_open_alert(alert, instance_group_map):
    """Registry group for an open alert, or None (disk, producer gone).

    ``attributes.service_name`` → group of any live instance of that name,
    else ``business``. Disk alerts (no service_name) → group of the
    producer instance; missing producer → None (Group ``all`` only).
    """
    attributes = alert.get("attributes") or {}
    service_name = attributes.get("service_name")
    if service_name:
        for (svc, _inst), group in instance_group_map.items():
            if svc == service_name:
                return group
        return "business"
    producer = alert.get("_producer_service")
    producer_id = alert.get("_producer_instance_id")
    return instance_group_map.get((producer, producer_id))


def open_alert_matches_group(alert, group_filter, instance_group_map):
    if group_filter == "all":
        return True
    group = group_for_open_alert(alert, instance_group_map)
    if group is None:
        return False
    return matches_group_filter(group, group_filter)


def apply_incident_field_filter(rows, field, value):
    if not field or field == "all" or not value:
        return list(rows)
    expected = value.lower()
    return [row for row in rows if expected in _incident_field(row, field).lower()]


def incident_host_display(alert):
    """Host cell: disk alias, or ``N/A`` for kontiki-monitor opens."""
    source = alert.get("source") or alert.get("_producer_service")
    if source == MONITOR_SERVICE_NAME:
        return "N/A"
    attributes = alert.get("attributes") or {}
    return str(attributes.get("host", "") or "")


def _incident_field(row, field):
    if field == "host":
        return incident_host_display(row)
    if field == "service_name":
        attributes = row.get("attributes") or {}
        return str(attributes.get("service_name", "") or "")
    return str(row.get(field, "") or "")


def silenced_service_names(silences):
    """Set of service_name values from list_silences."""
    names = set()
    for item in silences or []:
        name = item.get("service_name") if isinstance(item, dict) else None
        if name:
            names.add(name)
    return names


def build_silence_row(service_name, raw_services):
    """Join one silenced name with get_services (present / absent / group / live)."""
    instances = (raw_services or {}).get(service_name)
    if not isinstance(instances, dict) or not instances:
        return {
            "service_name": service_name,
            "registry": "absent",
            "group": "business",
            "groups": ("business",),
            "live": 0,
        }
    groups = []
    live = 0
    for entry in instances.values():
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata") or {}
        group = normalize_registration_group(metadata.get("group"))
        if group not in groups:
            groups.append(group)
        if str(entry.get("status") or "").lower() in ("active", "degraded"):
            live += 1
    if not groups:
        groups.append("business")
    groups.sort()
    return {
        "service_name": service_name,
        "registry": "present",
        "group": groups[0],
        "groups": tuple(groups),
        "live": live,
    }


def build_silence_rows(silences, raw_services):
    names = sorted(silenced_service_names(silences))
    return [build_silence_row(name, raw_services) for name in names]


def silence_matches_group(row, group_filter):
    if group_filter == "all":
        return True
    return group_filter in (row.get("groups") or ())


def apply_silence_field_filter(rows, field, value):
    if not field or field == "all" or not value:
        return list(rows)
    expected = value.lower()
    return [row for row in rows if expected in str(row.get(field, "") or "").lower()]


def orphan_silenced_count(silenced_names, raw_services):
    """How many silenced names have no registry entry (any status)."""
    count = 0
    for name in silenced_names or []:
        instances = (raw_services or {}).get(name)
        if not isinstance(instances, dict) or not instances:
            count += 1
    return count


def format_orphan_silence_warning(count):
    if count == 1:
        return "1 unregistered service still silenced"
    return "%s unregistered services still silenced" % count


def live_service_names_in_group(raw_services, group_filter):
    """Distinct live (active/degraded) service names in the session group."""
    names = []
    seen = set()
    for service_name, instances in (raw_services or {}).items():
        if not isinstance(instances, dict):
            continue
        for _instance_id, entry in instances.items():
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status") or "").lower()
            if status not in ("active", "degraded"):
                continue
            metadata = entry.get("metadata") or {}
            group = normalize_registration_group(metadata.get("group"))
            if not matches_group_filter(group, group_filter):
                continue
            if service_name in seen:
                continue
            seen.add(service_name)
            names.append(service_name)
    return sorted(names)


def format_instance_unreachable(service_name, instance_id):
    return "%s %s unreachable" % (
        service_name,
        short_instance_id(str(instance_id or "")),
    )


def format_last_heartbeat(last_heartbeat):
    """Return ``last_heartbeat`` as ``YYYY-MM-DD HH:MM:SS`` UTC, or empty."""
    if last_heartbeat is None:
        return ""
    if isinstance(last_heartbeat, datetime):
        parsed = last_heartbeat
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    if not isinstance(last_heartbeat, str):
        return str(last_heartbeat)
    text = last_heartbeat.strip()
    if not text:
        return ""

    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def format_degraded_reason(reason):
    """Display helper for registry ``degraded_reason`` (``-`` when absent)."""
    if reason is None:
        return "-"
    if not isinstance(reason, str):
        return str(reason)
    text = reason.strip()
    if not text:
        return "-"
    return text
