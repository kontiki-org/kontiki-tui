import logging
from datetime import datetime

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Label, Select, Static


class EventsTab(Static):
    BINDINGS = [
        Binding("r", "refresh_events", description="Refresh events"),
    ]

    def __init__(self, id_="events"):
        super().__init__(id=id_)
        self.events_table = None
        self.field_input = None
        self.value_input = None
        self.limit_input = None
        self._events_cache = []
        self.field_options = [
            ("All", "all"),
            ("Service Name", "service_name"),
            ("Instance ID", "instance_id"),
            ("Event Type", "event_type"),
        ]
        self.headers = (
            "Time",
            "Service",
            "Instance",
            "Event Type",
            "Host",
        )

    def compose(self):
        with Vertical(id="events_vertical"):
            with Horizontal(id="events_filters"):
                yield Label("Field:")
                self.field_input = Select(
                    options=self.field_options,
                    value="all",
                    id="events_field",
                )
                yield self.field_input
                yield Label("Value:")
                self.value_input = Input(placeholder="filter value", id="events_value")
                yield self.value_input
                yield Label("Limit:")
                self.limit_input = Input(value="500", id="events_limit")
                yield self.limit_input

            table = DataTable(
                id="events_table",
                classes="datatables",
                cursor_type="row",
            )
            table.border_title = "Events"
            self.events_table = table
            yield table

    async def action_refresh_events(self) -> None:
        await self.update_table()

    def on_mount(self) -> None:
        self._sync_value_input_state()

    def _sync_value_input_state(self) -> None:
        if not self.value_input or not self.field_input:
            return
        field = (
            str(self.field_input.value).strip().lower()
            if self.field_input.value is not None
            else "all"
        )
        self.value_input.disabled = field == "all"

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"events_value", "events_limit"}:
            self._render_table_from_cache()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "events_field":
            self._sync_value_input_state()
            self._render_table_from_cache()

    def _format_time(self, timestamp: str) -> str:
        if not timestamp:
            return ""
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime(
                "%H:%M:%S.%f"
            )
        except Exception:
            return timestamp

    def _event_sort_key(self, event: dict) -> float:
        """Sort by parsed timestamp with microsecond precision."""
        timestamp = str(event.get("timestamp", "")).strip()
        if not timestamp:
            return float("-inf")
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
        except Exception:
            return float("-inf")

    def _event_type_label(self, event: dict) -> str:
        event_type = str(event.get("event_type", "")).strip()
        if event_type:
            return event_type
        remote_method = str(event.get("remote_method", "")).strip()
        if remote_method:
            # Prefix avoids collisions with domain event names.
            return f"rpc:{remote_method}"
        return ""

    def _get_filter_state(self) -> tuple[str, str, int]:
        field = (
            str(self.field_input.value).strip().lower()
            if self.field_input and self.field_input.value is not None
            else "all"
        )
        value = self.value_input.value.strip() if self.value_input else ""
        raw_limit = self.limit_input.value.strip() if self.limit_input else "500"
        try:
            limit = max(1, int(raw_limit))
        except Exception:
            limit = 500
        return field, value, limit

    def _apply_local_filters(self, events: list[dict]) -> list[dict]:
        field, value, limit = self._get_filter_state()
        filtered = events

        if field and field != "all" and value:
            expected = value.lower()

            def match(event: dict) -> bool:
                if field == "event_type":
                    candidate = self._event_type_label(event)
                else:
                    candidate = event.get(field, "")
                return expected in str(candidate).lower()

            filtered = [event for event in events if match(event)]

        events_sorted = sorted(filtered, key=self._event_sort_key, reverse=True)
        return events_sorted[:limit]

    def _render_table_from_cache(self) -> None:
        if self.events_table is None:
            try:
                self.events_table = self.query_one("#events_table", DataTable)
            except Exception as e:
                logging.error(f"Events table not available: {e}", exc_info=True)
                return

        events_limited = self._apply_local_filters(self._events_cache)

        rows = []
        for event in events_limited:
            rows.append(
                (
                    self._format_time(event.get("timestamp", "")),
                    str(event.get("service_name", "")),
                    str(event.get("instance_id", "")),
                    self._event_type_label(event),
                    str(event.get("host", "")),
                )
            )

        if len(self.events_table.columns) == 0:
            self.events_table.add_columns(*self.headers)

        self.events_table.clear()
        if rows:
            self.events_table.add_rows(rows)
        self.events_table.refresh()

    async def update_table(self) -> None:
        if self.events_table is None:
            try:
                self.events_table = self.query_one("#events_table", DataTable)
            except Exception as e:
                logging.error(f"Events table not available: {e}", exc_info=True)
                return

        services_backend = self.app.services
        if services_backend is None:
            logging.error("Services backend instance not available on app")
            return

        try:
            events = await services_backend.get_events()
        except Exception as e:
            logging.error(f"Error getting events from backend: {e}", exc_info=True)
            return

        self._events_cache = events if isinstance(events, list) else []
        self._render_table_from_cache()
