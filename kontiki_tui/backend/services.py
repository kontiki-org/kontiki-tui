import logging
from datetime import datetime, timezone

from kontiki.registry import ServiceRegistryProxy


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
    """Build Select options: All first, then known groups (sorted)."""
    groups = set(discovered_groups or [])
    groups.add("business")
    groups.add("platform")
    options = [("All", "all")]
    for name in sorted(groups):
        options.append((name, name))
    return options


class Services:
    def __init__(self, messenger):
        self.services = ServiceRegistryProxy(messenger)

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
        """Return log file paths under ``log_directory`` matching ``group_filter``.

        Requires Kontiki >=1.8.1 naming: ``{service_name}-{12hex}.log``.
        Files whose stem cannot be matched to a registry instance fall back to
        ``business`` (they are included in ``business`` and ``all`` views).
        Files that do not match the Kontiki naming pattern are always included.

        ``ServiceRegistry-*.log`` is always omitted (registry process does not
        self-register; its logs are mostly TUI observer RPC noise).
        """
        import os
        import re

        if not log_directory or not os.path.isdir(log_directory):
            return []

        # Pattern: anything ending with -{12 lowercase hex}.log
        kontiki_pattern = re.compile(r"^(.+)-([0-9a-f]{12})\.log$")
        instance_group_map = (
            {} if group_filter == "all" else await self._build_instance_group_map()
        )

        result = []
        for name in sorted(os.listdir(log_directory)):
            full_path = os.path.join(log_directory, name)
            if not os.path.isfile(full_path):
                continue
            m = kontiki_pattern.match(name)
            if not m:
                # Non-Kontiki file: always include (no group info available).
                result.append(full_path)
                continue
            service_name, short_id = m.group(1), m.group(2)
            if implied_platform_group(service_name):
                # ServiceRegistry logs: never shown in the TUI Logs tab.
                continue
            if group_filter == "all":
                result.append(full_path)
                continue
            group = "business"
            for (svc, inst_id), grp in instance_group_map.items():
                sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", svc)
                if sanitized == service_name and inst_id.replace("-", "").startswith(
                    short_id
                ):
                    group = grp
                    break
            if matches_group_filter(group, group_filter):
                result.append(full_path)
        return result


def format_last_heartbeat(last_heartbeat):
    """Return ``last_heartbeat`` as ``YYYY-MM-DD HH:MM:SS`` UTC, or empty."""
    if last_heartbeat is None:
        return ""
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
