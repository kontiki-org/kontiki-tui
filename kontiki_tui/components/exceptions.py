import json
import logging
from datetime import datetime

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Label, Select, Static


class ExceptionsTab(Static):
    BINDINGS = [
        Binding("r", "refresh_exceptions", description="Refresh exceptions"),
    ]

    def __init__(self, id_="exceptions"):
        super().__init__(id=id_)
        self.exceptions_table = None
        self.field_input = None
        self.value_input = None
        self.limit_input = None
        self._exceptions_cache = []
        self.field_options = [
            ("All", "all"),
            ("Service Name", "service_name"),
            ("Instance ID", "instance_id"),
            ("Exception Type", "exception_type"),
            ("Message", "message"),
        ]
        self.headers = (
            "Time",
            "Service",
            "Instance",
            "Type",
            "Message",
            "Context",
        )

    def compose(self):
        with Vertical(id="exceptions_vertical"):
            with Horizontal(id="exceptions_filters"):
                yield Label("Field:")
                self.field_input = Select(
                    options=self.field_options,
                    value="all",
                    id="exceptions_field",
                )
                yield self.field_input
                yield Label("Value:")
                self.value_input = Input(
                    placeholder="filter value", id="exceptions_value"
                )
                yield self.value_input
                yield Label("Limit:")
                self.limit_input = Input(value="500", id="exceptions_limit")
                yield self.limit_input

            table = DataTable(
                id="exceptions_table",
                classes="datatables",
                cursor_type="row",
            )
            table.border_title = "Registry exceptions"
            self.exceptions_table = table
            yield table

    async def action_refresh_exceptions(self) -> None:
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
        if event.input.id in {"exceptions_value", "exceptions_limit"}:
            self._render_table_from_cache()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "exceptions_field":
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
            return str(timestamp)

    def _exception_sort_key(self, row: dict) -> float:
        timestamp = str(row.get("timestamp", "")).strip()
        if not timestamp:
            return float("-inf")
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
        except Exception:
            return float("-inf")

    def _format_context(self, context) -> str:
        if context is None or context == "":
            return ""
        if isinstance(context, (dict, list)):
            try:
                text = json.dumps(context, default=str, ensure_ascii=False)
            except Exception:
                text = str(context)
        else:
            text = str(context)
        max_len = 96
        if len(text) > max_len:
            return text[: max_len - 3] + "..."
        return text

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

    def _apply_local_filters(self, rows: list[dict]) -> list[dict]:
        field, value, limit = self._get_filter_state()
        filtered = rows

        if field and field != "all" and value:
            expected = value.lower()

            def match(exc: dict) -> bool:
                candidate = exc.get(field, "")
                return expected in str(candidate).lower()

            filtered = [exc for exc in rows if match(exc)]

        sorted_rows = sorted(filtered, key=self._exception_sort_key, reverse=True)
        return sorted_rows[:limit]

    def _render_table_from_cache(self) -> None:
        if self.exceptions_table is None:
            try:
                self.exceptions_table = self.query_one("#exceptions_table", DataTable)
            except Exception as e:
                logging.error(f"Exceptions table not available: {e}", exc_info=True)
                return

        limited = self._apply_local_filters(self._exceptions_cache)

        table_rows = []
        for exc in limited:
            table_rows.append(
                (
                    self._format_time(str(exc.get("timestamp", "") or "")),
                    str(exc.get("service_name", "")),
                    str(exc.get("instance_id", "")),
                    str(exc.get("exception_type", "")),
                    str(exc.get("message", "")),
                    self._format_context(exc.get("context")),
                )
            )

        if len(self.exceptions_table.columns) == 0:
            self.exceptions_table.add_columns(*self.headers)

        self.exceptions_table.clear()
        if table_rows:
            self.exceptions_table.add_rows(table_rows)
        self.exceptions_table.refresh()

    async def update_table(self) -> None:
        if self.exceptions_table is None:
            try:
                self.exceptions_table = self.query_one("#exceptions_table", DataTable)
            except Exception as e:
                logging.error(f"Exceptions table not available: {e}", exc_info=True)
                return

        services_backend = self.app.services
        if services_backend is None:
            logging.error("Services backend instance not available on app")
            return

        try:
            exc_list = await services_backend.get_exceptions()
        except Exception as e:
            logging.error(f"Error getting exceptions from backend: {e}", exc_info=True)
            return

        self._exceptions_cache = exc_list if isinstance(exc_list, list) else []
        self._render_table_from_cache()
