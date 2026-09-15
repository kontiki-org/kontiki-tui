import logging

from kontiki.messaging import RpcClientError, RpcTimeoutError
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Label, Select, Static

from kontiki_tui.backend.services import (
    apply_silence_field_filter,
    silence_matches_group,
)
from kontiki_tui.components.group_filter import (
    GROUP_FILTER_SELECT_CLASS,
    GroupFilterChanged,
    current_group_filter,
    is_group_filter_sync,
    make_group_filter_select,
    refresh_group_filter_options,
)

# -----------------------------------------------------------------------------

_FIELD_OPTIONS = [
    ("All", "all"),
    ("Service", "service_name"),
    ("Registry", "registry"),
    ("Group", "group"),
]

_HEADERS = (
    ("service_name", "Service"),
    ("registry", "Registry"),
    ("group", "Group"),
    ("live", "Live"),
)

_ERROR_MESSAGES = {
    "registry": "ServiceRegistry unreachable",
    "monitor_missing": "kontiki-monitor is not registered",
    "monitor_unreachable": "kontiki-monitor unreachable",
}


class SilencesTab(Static):
    BINDINGS = [
        Binding("r", "refresh_silences", description="Refresh silences"),
        Binding("s", "clear_silence", description="Clear silence"),
    ]

    def __init__(self, id_="silences"):
        super().__init__(id=id_)
        self.silences_table = None
        self.field_input = None
        self.value_input = None
        self.group_filter_select = None
        self._silences_cache = []
        self.row_data_map = {}

    def compose(self):
        with Vertical(id="silences_split"):
            with Horizontal(id="silences_filters"):
                yield Label("Field:")
                self.field_input = Select(
                    options=_FIELD_OPTIONS,
                    value="all",
                    id="silences_field",
                )
                yield self.field_input
                yield Label("Value:")
                self.value_input = Input(
                    placeholder="filter value", id="silences_value"
                )
                yield self.value_input
                label, select = make_group_filter_select(
                    self.app, "silences_group_filter"
                )
                self.group_filter_select = select
                yield label
                yield select
            table = DataTable(
                id="silences_table",
                classes="datatables",
                cursor_type="row",
            )
            self.silences_table = table
            table.border_title = "Silences"
            yield table

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

    def _get_filter_state(self):
        field = (
            str(self.field_input.value).strip().lower()
            if self.field_input and self.field_input.value is not None
            else "all"
        )
        value = self.value_input.value.strip() if self.value_input else ""
        return field, value

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "silences_value":
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
        if event.select.id == "silences_field":
            self._sync_value_input_state()
            self._render_table_from_cache()

    async def action_refresh_silences(self):
        await self.update_table()

    def _row_to_tuple(self, row):
        cells = []
        for index, (key, _label) in enumerate(_HEADERS):
            value = str(row.get(key, "") or "")
            if index == 0:
                cells.append(value)
            else:
                cells.append(Text(value, justify="center"))
        return tuple(cells)

    def _render_table_from_cache(self):
        if self.silences_table is None:
            return
        if len(self.silences_table.columns) == 0:
            for index, (_key, label) in enumerate(_HEADERS):
                if index == 0:
                    self.silences_table.add_column(label)
                else:
                    self.silences_table.add_column(Text(label, justify="center"))

        field, value = self._get_filter_state()
        filtered = apply_silence_field_filter(self._silences_cache, field, value)
        rows = [self._row_to_tuple(row) for row in filtered]

        self.silences_table.clear()
        self.row_data_map = {}
        if rows:
            row_keys = self.silences_table.add_rows(rows)
            for row_key, row in zip(row_keys, filtered):
                self.row_data_map[row_key] = row
        self.silences_table.refresh()

    def _selected_row(self):
        if self.silences_table is None:
            return None
        cursor_row = self.silences_table.cursor_row
        if cursor_row is None:
            return None
        row_keys = list(self.silences_table.rows.keys())
        if cursor_row < 0 or cursor_row >= len(row_keys):
            return None
        return self.row_data_map.get(row_keys[cursor_row])

    async def update_table(self):
        if self.silences_table is None:
            return
        backend = self.app.services
        if backend is None:
            logging.error("Services backend instance not available on app")
            return

        if self.group_filter_select is not None:
            await refresh_group_filter_options(self.app)
        group_filter = current_group_filter(self.app)

        rows, error = await backend.fetch_silence_rows()
        visible = [row for row in rows if silence_matches_group(row, group_filter)]
        self._silences_cache = visible
        self._render_table_from_cache()

        if error:
            self.app._show_error_prompt(_ERROR_MESSAGES[error])

    async def action_clear_silence(self):
        row = self._selected_row()
        if not row:
            self.app._show_error_prompt("No silence selected")
            return
        backend = self.app.services
        if backend is None:
            return
        try:
            ids = await backend.list_monitor_instances()
        except Exception:
            self.app._show_error_prompt("ServiceRegistry unreachable")
            return
        if not ids:
            self.app._show_error_prompt("kontiki-monitor is not registered")
            return
        service_name = row.get("service_name")
        try:
            await backend.clear_silence(service_name)
        except RpcTimeoutError:
            self.app._show_error_prompt("kontiki-monitor unreachable")
            return
        except RpcClientError as exc:
            self.app._show_error_prompt(exc.message)
            return
        except Exception as exc:
            logging.error("clear_silence failed: %s", exc, exc_info=True)
            self.app._show_error_prompt("kontiki-monitor unreachable")
            return
        logging.info("Silence cleared for service_name=%s", service_name)
        await self.update_table()
