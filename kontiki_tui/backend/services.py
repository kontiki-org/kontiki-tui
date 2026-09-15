import logging
from datetime import datetime, timezone

from kontiki.messaging import RpcProxy
from kontiki.messaging.flow import short_instance_id
from kontiki.registry import ServiceRegistryProxy

OPS_OPEN_ALERT_SOURCES = ("kontiki-monitor", "host-check-service")
MONITOR_SERVICE_NAME = "kontiki-monitor"


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

    async def list_registration_groups(self):
        """Return sorted group names discovered in the live registry."""
        instance_group_map = await self._build_instance_group_map()
        return sorted(set(instance_group_map.values()))

    def _is_internal_registry_event(self, event: dict) -> bool:
        """True for TUI observer traffic and ServiceRegistry bookkeeping.

        Domain publishes and RPC call entries (``remote_method`` / ``_rpc_event``)
        stay visible in the Events tab.
        """
        service_name = event.get("service_name")
        if not isinstance(service_name, str):
            return False
        return "kontiki_tui" in service_name or service_name == "ServiceRegistry"

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
        service_name = event.get("service_name")
        implied = implied_platform_group(service_name)
        if implied:
            return implied
        key = (service_name, event.get("instance_id"))
        return instance_group_map.get(key, "business")

    async def get_events(
        self, include_internal: bool = False, group_filter: str = "all"
    ) -> list[dict]:
        events = await self.services.get_events()
        events = self._filter_registry_events(events, include_internal=include_internal)
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

    async def get_filtered_events(
        self,
        filter_field: str,
        value,
        include_internal: bool = False,
        group_filter: str = "all",
    ) -> list[dict]:
        events = await self.services.get_filtered_events(filter_field, value)
        events = self._filter_registry_events(events, include_internal=include_internal)
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

        Requires Kontiki >=1.8.1 naming: ``{service_name}-{12hex}.log``.
        The set is the live registry (any status), then the session group.
        Leftover files from deregistered instances, non-Kontiki names, and
        ``ServiceRegistry-*.log`` (not in the registry) are omitted.
        """
        import os
        import re

        if not log_directory or not os.path.isdir(log_directory):
            return []

        instance_group_map = await self._build_instance_group_map()
        result = []
        for (svc, inst_id), group in instance_group_map.items():
            if not matches_group_filter(group, group_filter):
                continue
            sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", svc)
            short_id = inst_id.replace("-", "")[:12]
            full_path = os.path.join(log_directory, f"{sanitized}-{short_id}.log")
            if os.path.isfile(full_path):
                result.append(full_path)
        return sorted(result)

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
