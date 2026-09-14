import json
import logging

from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Label, Select, Static, TextArea

from kontiki_tui.backend.services import (
    apply_incident_field_filter,
    display_alert_dict,
    format_instance_unreachable,
    format_last_heartbeat,
    open_alert_matches_group,
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
    ("Severity", "severity"),
    ("Source", "source"),
    ("Type", "event_type"),
    ("Title", "title"),
    ("Service", "service_name"),
    ("Host", "host"),
    ("Alert ID", "alert_id"),
]

_HEADERS = (
    ("severity", "Severity"),
    ("source", "Source"),
    ("event_type", "Type"),
    ("title", "Title"),
    ("service_name", "Service"),
    ("host", "Host"),
    ("occurred_at", "Occurred"),
    ("alert_id", "Alert ID"),
)


class IncidentsTab(Static):
    BINDINGS = [
        Binding("r", "refresh_incidents", description="Refresh incidents"),
    ]

    def __init__(self, id_="incidents"):
        super().__init__(id=id_)
        self.incidents_table = None
        self.detail_view = None
        self.field_input = None
        self.value_input = None
        self.group_filter_select = None
        self._incidents_cache = []
        self.row_data_map = {}

    def compose(self):
        with Vertical(id="incidents_split"):
            with Horizontal(id="incidents_filters"):
                yield Label("Field:")
                self.field_input = Select(
                    options=_FIELD_OPTIONS,
                    value="all",
                    id="incidents_field",
                )
                yield self.field_input
                yield Label("Value:")
                self.value_input = Input(
                    placeholder="filter value", id="incidents_value"
                )
                yield self.value_input
                label, select = make_group_filter_select(
                    self.app, "incidents_group_filter"
                )
                self.group_filter_select = select
                yield label
                yield select
            table = DataTable(
                id="incidents_table",
                classes="datatables",
                cursor_type="row",
            )
            self.incidents_table = table
            table.border_title = "Open incidents"
            yield table
            detail_view = TextArea(
                id="incident_detail",
                language="json",
                read_only=True,
            )
            detail_view.border_title = "Alert"
            self.detail_view = detail_view
            yield detail_view

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
        if event.input.id == "incidents_value":
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
        if event.select.id == "incidents_field":
            self._sync_value_input_state()
            self._render_table_from_cache()

    async def action_refresh_incidents(self):
        await self.update_table()

    def _cell_value(self, alert, key):
        if key in ("service_name", "host"):
            attributes = alert.get("attributes") or {}
            return str(attributes.get(key, "") or "")
        if key == "occurred_at":
            return format_last_heartbeat(alert.get("occurred_at"))
        return str(alert.get(key, "") or "")

    def _row_to_tuple(self, alert):
        cells = []
        for index, (key, _label) in enumerate(_HEADERS):
            value = self._cell_value(alert, key)
            if index == 0:
                cells.append(value)
            else:
                cells.append(Text(value, justify="center"))
        return tuple(cells)

    def _update_detail_view(self, alert):
        if self.detail_view is None:
            return
        if not alert:
            self.detail_view.text = ""
            return
        payload = display_alert_dict(alert)
        self.detail_view.text = json.dumps(
            payload, indent=2, sort_keys=True, default=str
        )

    def _render_table_from_cache(self):
        if self.incidents_table is None:
            return
        if len(self.incidents_table.columns) == 0:
            for index, (_key, label) in enumerate(_HEADERS):
                if index == 0:
                    self.incidents_table.add_column(label)
                else:
                    self.incidents_table.add_column(Text(label, justify="center"))

        field, value = self._get_filter_state()
        filtered = apply_incident_field_filter(self._incidents_cache, field, value)
        rows = [self._row_to_tuple(alert) for alert in filtered]

        self.incidents_table.clear()
        self.row_data_map = {}
        if rows:
            row_keys = self.incidents_table.add_rows(rows)
            for row_key, alert in zip(row_keys, filtered):
                self.row_data_map[row_key] = alert
        else:
            self._update_detail_view({})
        self.incidents_table.refresh()

    async def update_table(self):
        if self.incidents_table is None:
            return
        backend = self.app.services
        if backend is None:
            logging.error("Services backend instance not available on app")
            return

        if self.group_filter_select is not None:
            await refresh_group_filter_options(self.app)
        group_filter = current_group_filter(self.app)

        alerts, registry_failed, instance_errors = await backend.fetch_open_alerts()
        instance_group_map = await backend.instance_groups()
        visible = [
            alert
            for alert in alerts
            if open_alert_matches_group(alert, group_filter, instance_group_map)
        ]
        self._incidents_cache = visible
        self._render_table_from_cache()

        if registry_failed:
            self.app._show_error_prompt("ServiceRegistry unreachable")
            return
        if not instance_errors:
            return
        messages = [
            format_instance_unreachable(service_name, instance_id)
            for service_name, instance_id in instance_errors
        ]
        self.app._show_error_prompt("; ".join(messages))

    @on(DataTable.RowHighlighted)
    @on(DataTable.RowSelected)
    def on_row_changed(self, event):
        if self.incidents_table is None:
            return
        cursor_row = event.cursor_row
        if cursor_row is None:
            return
        row_keys = list(self.incidents_table.rows.keys())
        if cursor_row < len(row_keys):
            alert = self.row_data_map.get(row_keys[cursor_row], {})
            self._update_detail_view(alert)
