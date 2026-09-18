import logging
from datetime import datetime

from kontiki.messaging.flow import short_instance_id
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Label, Select, Static

from kontiki_tui.backend.export import exception_stem, render_exception
from kontiki_tui.backend.services import instance_id_filter_matches
from kontiki_tui.components.group_filter import (
    GROUP_FILTER_SELECT_CLASS,
    GroupFilterChanged,
    current_group_filter,
    is_group_filter_sync,
    make_group_filter_select,
    refresh_group_filter_options,
)
from kontiki_tui.components.markdown_export import (
    finish_markdown_export,
    request_markdown_export,
)
from kontiki_tui.components.prompt import ConfirmPrompt


def _cell(value):
    if value is None:
        return ""
    return str(value)


class ExceptionsTab(Static):
    BINDINGS = [
        Binding("r", "refresh_exceptions", description="Refresh exceptions"),
        Binding("e", "export_exception", description="Export"),
    ]

    def __init__(self, id_="exceptions"):
        super().__init__(id=id_)
        self.exceptions_table = None
        self.field_input = None
        self.value_input = None
        self.limit_input = None
        self.group_filter_select = None
        self._exceptions_cache = []
        self.row_data_map = {}
        self.field_options = [
            ("All", "all"),
            ("Service", "service_name"),
            ("Instance", "instance_id"),
            ("Flow ID", "flow_id"),
            ("Entrypoint", "entrypoint"),
            ("Operation", "operation"),
            ("Exception Type", "exception_type"),
            ("Message", "message"),
        ]
        self.headers = (
            "Time",
            "Service",
            "Instance",
            "Flow",
            "Entrypoint",
            "Operation",
            "Type",
            "Message",
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
                label, select = make_group_filter_select(
                    self.app, "exceptions_group_filter"
                )
                self.group_filter_select = select
                yield label
                yield select

            table = DataTable(
                id="exceptions_table",
                classes="datatables",
                cursor_type="row",
            )
            table.border_title = "Registry exceptions"
            self.exceptions_table = table
            yield table

    async def action_refresh_exceptions(self):
        await self.update_table()

    def action_export_exception(self):
        request_markdown_export(
            self,
            self._selected_exception(),
            "No exception selected",
            exception_stem,
            render_exception,
        )

    @on(ConfirmPrompt.Result)
    def on_confirm_prompt_result(self, event):
        finish_markdown_export(self, event)

    def on_mount(self):
        self._sync_value_input_state()

    def _sync_value_input_state(self):
        if not self.value_input or not self.field_input:
            return
        field = (
            str(self.field_input.value).strip().lower()
            if self.field_input.value is not None
            else "all"
        )
        self.value_input.disabled = field == "all"

    def on_input_changed(self, event: Input.Changed):
        if event.input.id in {"exceptions_value", "exceptions_limit"}:
            self._render_table_from_cache()

    @on(Select.Changed)
    def on_select_changed(self, event: Select.Changed):
        if GROUP_FILTER_SELECT_CLASS in event.select.classes:
            if is_group_filter_sync(self.app):
                return
            value = event.value
            if value is None or value is Select.BLANK:
                return
            value = str(value)
            if value == current_group_filter(self.app):
                return
            self.post_message(GroupFilterChanged(value))
            return
        if event.select.id == "exceptions_field":
            self._sync_value_input_state()
            self._render_table_from_cache()

    def _format_time(self, timestamp):
        if not timestamp:
            return ""
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime(
                "%H:%M:%S.%f"
            )
        except Exception:
            return str(timestamp)

    def _exception_sort_key(self, row):
        timestamp = str(row.get("timestamp") or "").strip()
        if not timestamp:
            return float("-inf")
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
        except Exception:
            return float("-inf")

    def _get_filter_state(self):
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

    def _apply_local_filters(self, rows):
        field, value, limit = self._get_filter_state()
        filtered = rows

        if field and field != "all" and value:
            expected = value.lower()

            def match(exc):
                if field == "instance_id":
                    return instance_id_filter_matches(exc.get("instance_id"), expected)
                return expected in _cell(exc.get(field)).lower()

            filtered = [exc for exc in rows if match(exc)]

        sorted_rows = sorted(filtered, key=self._exception_sort_key, reverse=True)
        return sorted_rows[:limit]

    def _render_table_from_cache(self):
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
                    self._format_time(_cell(exc.get("timestamp"))),
                    _cell(exc.get("service_name")),
                    short_instance_id(_cell(exc.get("instance_id"))),
                    _cell(exc.get("flow_id")),
                    _cell(exc.get("entrypoint")),
                    _cell(exc.get("operation")),
                    _cell(exc.get("exception_type")),
                    _cell(exc.get("message")),
                )
            )

        if len(self.exceptions_table.columns) == 0:
            self.exceptions_table.add_columns(*self.headers)

        self.exceptions_table.clear()
        self.row_data_map = {}
        if table_rows:
            row_keys = self.exceptions_table.add_rows(table_rows)
            for row_key, exc in zip(row_keys, limited):
                self.row_data_map[row_key] = exc
        self.exceptions_table.refresh()

    def _selected_exception(self):
        if self.exceptions_table is None:
            return None
        cursor_row = self.exceptions_table.cursor_row
        if cursor_row is None:
            return None
        row_keys = list(self.exceptions_table.rows.keys())
        if cursor_row < 0 or cursor_row >= len(row_keys):
            return None
        return self.row_data_map.get(row_keys[cursor_row])

    async def update_table(self):
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

        if self.group_filter_select is not None:
            await refresh_group_filter_options(self.app)
        group_filter = current_group_filter(self.app)

        try:
            exc_list = await services_backend.get_exceptions(group_filter=group_filter)
        except Exception as e:
            logging.error(f"Error getting exceptions from backend: {e}", exc_info=True)
            return

        self._exceptions_cache = exc_list if isinstance(exc_list, list) else []
        self._render_table_from_cache()
