import logging
import socket

import psutil
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
    """Return True if an instance group should appear for the Services filter.

    group_filter is ``business`` (default view) or ``all``.
    """
    if group_filter == "all":
        return True
    return normalize_registration_group(group) == "business"


class Services:
    def __init__(self, messenger):
        self.services = ServiceRegistryProxy(messenger)

    async def get_services(self):
        return await self.services.get_services()

    def _is_internal_registry_event(self, event: dict) -> bool:
        """Exclude registry/RPC tracking noise from business event views."""
        event_type = event.get("event_type")
        service_name = event.get("service_name")
        # Keep business RPC events. Only hide events emitted by the TUI client.
        if isinstance(service_name, str) and "kontiki_tui" in service_name:
            return True
        return event_type == "_rpc_event" or service_name == "ServiceRegistry"

    def _filter_registry_events(
        self, events: list[dict], include_internal: bool = False
    ) -> list[dict]:
        if include_internal:
            return events
        return [
            event for event in events if not self._is_internal_registry_event(event)
        ]

    async def get_events(self, include_internal: bool = False) -> list[dict]:
        events = await self.services.get_events()
        return self._filter_registry_events(events, include_internal=include_internal)

    async def get_filtered_events(
        self, filter_field: str, value, include_internal: bool = False
    ) -> list[dict]:
        events = await self.services.get_filtered_events(filter_field, value)
        return self._filter_registry_events(events, include_internal=include_internal)

    async def get_exceptions(self) -> list[dict]:
        return await self.services.get_exceptions()

    async def get_filtered_exceptions(self, filter_field: str, value) -> list[dict]:
        return await self.services.get_filtered_exceptions(filter_field, value)

    def get_stats(self, pid: int, host: str) -> dict:
        logger = logging.getLogger("kontiki_tui")

        # Collect stats only for the local host
        local_hostnames = {socket.gethostname(), "localhost", "127.0.0.1"}
        if host not in local_hostnames:
            return {}

        try:
            # Ensure pid is an integer
            try:
                pid_int = int(pid) if pid else None
            except (ValueError, TypeError):
                logger.warning(f"Invalid PID format: {pid}")
                return {}

            if pid_int is None:
                return {}

            p = psutil.Process(pid_int)

            cpu_percent = p.cpu_percent(interval=0.0)

            # RSS memory in MB
            mem_info = p.memory_info()
            mem_mb = round(mem_info.rss / (1024 * 1024), 1)

            logger.debug(f"Stats for PID {pid_int}: CPU={cpu_percent}%, MEM={mem_mb}MB")

            try:
                fd_count = p.num_fds()
            except AttributeError:
                fd_count = ""

            return {
                "cpu_percent": cpu_percent,
                "mem_mb": mem_mb,
                "fd_count": fd_count,
            }

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"psutil cannot access pid {pid}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error collecting stats for pid {pid}: {e}", exc_info=True)
            return {}
