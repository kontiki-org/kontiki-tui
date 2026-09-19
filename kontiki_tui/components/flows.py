import logging

from kontiki.messaging.flow import short_instance_id
from rich.cells import cell_len
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Label, Select, Static

from kontiki_tui.backend.export import flow_stem, render_flow
from kontiki_tui.backend.services import (
    KIND_EXCEPTION,
    apply_flow_field_filter,
    format_flow_index_time,
    format_hop_time,
    tree_row_type_label,
)
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

_FIELD_OPTIONS = [
    ("All", "all"),
    ("Flow ID", "flow_id"),
    ("Origin", "origin"),
    ("First Type", "event_type"),
    ("Service", "service_name"),
    ("Group", "group"),
]

_FLOW_HEADERS = (
    "Flow Id",
    "Started",
    "Last",
    "Messages",
    "Origin",
    "First",
)

_HOP_HEADERS = (
    "Time",
    "Group",
    "Service",
    "Instance",
    "Type",
    "Host",
)


class FlowsTab(Static):
    BINDINGS = [
        Binding("r", "refresh_flows", description="Refresh flows"),
        Binding("e", "export_flow", description="Export"),
    ]

    def __init__(self, id_="flows"):
        super().__init__(id=id_)
        self.flows_table = None
        self.hops_table = None
        self.field_input = None
        self.value_input = None
        self.limit_input = None
        self.group_filter_select = None
        self._flows_cache = []
        self._selected_flow_id = None
        self._hops_shown_id = None
        self.row_data_map = {}

    def compose(self):
        with Vertical(id="flows_split"):
            with Horizontal(id="flows_filters"):
                yield Label("Field:")
                self.field_input = Select(
                    options=_FIELD_OPTIONS,
                    value="all",
                    id="flows_field",
                )
                yield self.field_input
                yield Label("Value:")
                self.value_input = Input(placeholder="filter value", id="flows_value")
                yield self.value_input
                yield Label("Limit:")
                self.limit_input = Input(value="500", id="flows_limit")
                yield self.limit_input
                label, select = make_group_filter_select(self.app, "flows_group_filter")
                self.group_filter_select = select
                yield label
                yield select
            flows_table = DataTable(
                id="flows_table",
                classes="datatables",
                cursor_type="row",
            )
            flows_table.border_title = "Flows"
            self.flows_table = flows_table
            yield flows_table
            hops_table = DataTable(
                id="hops_table",
                classes="datatables",
                cursor_type="row",
            )
            hops_table.border_title = "Messages"
            hops_table.show_row_labels = False
            self.hops_table = hops_table
            yield hops_table

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
        raw_limit = self.limit_input.value.strip() if self.limit_input else "500"
        try:
            limit = max(1, int(raw_limit))
        except Exception:
            limit = 500
        return field, value, limit

    def on_input_changed(self, event: Input.Changed):
        if event.input.id in {"flows_value", "flows_limit"}:
            self._render_from_cache()

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
        if event.select.id == "flows_field":
            self._sync_value_input_state()
            self._render_from_cache()

    async def action_refresh_flows(self):
        await self.update_table()

    def action_export_flow(self):
        request_markdown_export(
            self,
            self._selected_flow(),
            "No flow selected",
            flow_stem,
            render_flow,
        )

    @on(ConfirmPrompt.Result)
    def on_confirm_prompt_result(self, event):
        finish_markdown_export(self, event)

    def _visible_flows(self):
        field, value, limit = self._get_filter_state()
        filtered = apply_flow_field_filter(self._flows_cache, field, value)
        return filtered[:limit]

    def _flow_row_tuple(self, flow):
        return (
            str(flow.get("flow_id", "") or ""),
            format_flow_index_time(flow.get("started")),
            format_flow_index_time(flow.get("last")),
            str(len(flow.get("hops") or [])),
            str(flow.get("origin", "") or ""),
            str(flow.get("first_type", "") or ""),
        )

    def _hop_row_tuple(self, row):
        is_exc = row.get("_kind") == KIND_EXCEPTION
        type_label = tree_row_type_label(row)
        return (
            "—" if is_exc else format_hop_time(row.get("timestamp")),
            str(row.get("_group", "") or ""),
            str(row.get("service_name", "") or ""),
            short_instance_id(str(row.get("instance_id") or "")),
            Text(type_label, style="red") if is_exc else type_label,
            str(row.get("host", "") or ""),
        )

    def _ensure_columns(self, table, headers):
        if len(table.columns) == 0:
            table.add_columns(*headers)

    def _fit_hops_columns(self, rows):
        columns = self.hops_table.ordered_columns
        widths = [cell_len(header) for header in _HOP_HEADERS]
        for row in rows:
            for index, cell in enumerate(row):
                if isinstance(cell, Text):
                    width = cell.cell_len
                else:
                    width = cell_len(str(cell))
                if width > widths[index]:
                    widths[index] = width
        for column, width in zip(columns, widths):
            column.auto_width = False
            column.width = width
            column.content_width = width

    def _selected_flow(self):
        if self.flows_table is None:
            return None
        row_keys = list(self.flows_table.rows.keys())
        if not row_keys:
            return None
        cursor_row = self.flows_table.cursor_row
        if cursor_row is None or cursor_row < 0 or cursor_row >= len(row_keys):
            return None
        return self.row_data_map.get(row_keys[cursor_row])

    def _restore_flow_cursor(self, visible):
        if self.flows_table is None or not visible:
            self._selected_flow_id = None
            return
        target = 0
        if self._selected_flow_id:
            for index, flow in enumerate(visible):
                if flow.get("flow_id") == self._selected_flow_id:
                    target = index
                    break
        self.flows_table.move_cursor(row=target)
        self._selected_flow_id = visible[target].get("flow_id")

    def _render_hops(self, flow):
        if self.hops_table is None:
            return
        if flow is None:
            self.hops_table.border_title = "Messages"
            tree_rows = []
            shown_id = None
        else:
            flow_id = str(flow.get("flow_id", "") or "")
            self.hops_table.border_title = flow_id or "Messages"
            tree_rows = flow.get("tree_rows")
            if tree_rows is None:
                tree_rows = flow.get("hops") or []
            shown_id = flow_id or None
        rows = [self._hop_row_tuple(row) for row in tree_rows]
        self._ensure_columns(self.hops_table, _HOP_HEADERS)
        self._fit_hops_columns(rows)
        self.hops_table.clear()
        if rows:
            self.hops_table.add_rows(rows)
        self.hops_table.refresh(layout=True)
        self._hops_shown_id = shown_id

    def _render_from_cache(self):
        if self.flows_table is None:
            return
        self._ensure_columns(self.flows_table, _FLOW_HEADERS)
        visible = self._visible_flows()
        rows = [self._flow_row_tuple(flow) for flow in visible]
        self.flows_table.clear()
        self.row_data_map = {}
        if rows:
            row_keys = self.flows_table.add_rows(rows)
            for row_key, flow in zip(row_keys, visible):
                self.row_data_map[row_key] = flow
        self.flows_table.refresh()
        self._restore_flow_cursor(visible)
        self._render_hops(self._selected_flow())

    async def update_table(self):
        if self.flows_table is None:
            return
        backend = self.app.services
        if backend is None:
            logging.error("Services backend instance not available on app")
            return

        if self.group_filter_select is not None:
            await refresh_group_filter_options(self.app)
        group_filter = current_group_filter(self.app)

        try:
            flows = await backend.get_flows(group_filter=group_filter)
        except Exception as e:
            logging.error("Error getting flows from backend: %s", e, exc_info=True)
            return

        self._flows_cache = flows if isinstance(flows, list) else []
        self._render_from_cache()

    @on(DataTable.RowHighlighted)
    @on(DataTable.RowSelected)
    def on_flow_row_changed(self, event):
        if event.control is not self.flows_table:
            return
        flow = self._selected_flow()
        if flow is not None:
            self._selected_flow_id = flow.get("flow_id")
        shown = None if flow is None else str(flow.get("flow_id") or "") or None
        if shown == self._hops_shown_id:
            return
        self._render_hops(flow)
