import json
import logging

from kontiki.messaging import RpcClientError, RpcTimeoutError
from rich.cells import cell_len
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Label, Select, Static, TextArea

from kontiki_tui.backend.entrypoints import (
    apply_entrypoint_service_filter,
    build_service_rows,
    entrypoint_failed_display,
    line_key,
    service_failed_display,
)
from kontiki_tui.components.group_filter import (
    GROUP_FILTER_SELECT_CLASS,
    GroupFilterChanged,
    current_group_filter,
    is_group_filter_sync,
    make_group_filter_select,
    refresh_group_filter_options,
)
from kontiki_tui.components.prompt import ConfirmPrompt, show_confirm

_SERVICE_HEADERS = ("Service", "Instances", "Catalog", "Failed")
_SERVICE_JUSTIFY = ("left", "center", "center", "center")
_ENTRY_HEADERS = (
    "Type",
    "Name",
    "Handler",
    "Mode",
    "Attempts",
    "Declared",
    "Failed",
)
_ENTRY_JUSTIFY = (
    "left",
    "left",
    "left",
    "center",
    "center",
    "center",
    "center",
)
_FIELD_OPTIONS = [
    ("All", "all"),
    ("Service", "service_name"),
]
_UNREACHABLE = "ServiceRegistry unreachable"


class EntrypointsTab(Static):
    BINDINGS = [
        Binding("r", "refresh_entrypoints", description="Refresh entrypoints"),
        Binding("p", "replay", description="Replay oldest failed"),
        Binding("d", "drop", description="Drop oldest failed"),
    ]

    def __init__(self, id_="entrypoints"):
        super().__init__(id=id_)
        self.services_table = None
        self.entrypoints_table = None
        self.message_view = None
        self.field_input = None
        self.value_input = None
        self.group_filter_select = None
        self._services_cache = []
        self._service_rows = {}
        self._entrypoint_rows = {}
        self._counts = {}
        self._bodies = {}
        self._unavailable = {}
        self._rendering = 0

    def compose(self):
        with Vertical(id="entrypoints_split"):
            with Horizontal(id="entrypoints_filters"):
                yield Label("Field:")
                self.field_input = Select(
                    options=_FIELD_OPTIONS,
                    value="all",
                    id="entrypoints_field",
                )
                yield self.field_input
                yield Label("Value:")
                self.value_input = Input(
                    placeholder="filter value", id="entrypoints_value"
                )
                yield self.value_input
                label, select = make_group_filter_select(
                    self.app, "entrypoints_group_filter"
                )
                self.group_filter_select = select
                yield label
                yield select
            with Horizontal(id="entrypoints_tables"):
                services_table = DataTable(
                    id="entrypoints_services_table",
                    classes="datatables",
                    cursor_type="row",
                )
                services_table.border_title = "Services"
                self.services_table = services_table
                yield services_table
                entrypoints_table = DataTable(
                    id="entrypoints_table",
                    classes="datatables",
                    cursor_type="row",
                )
                entrypoints_table.border_title = "Entrypoints"
                self.entrypoints_table = entrypoints_table
                yield entrypoints_table
            message_view = TextArea(
                id="entrypoint_message",
                language="json",
                read_only=True,
            )
            message_view.border_title = "Message"
            message_view.tooltip = (
                "Body of the oldest retained message for the selected "
                "competing event. Empty when that row has nothing retained."
            )
            message_view.can_focus = False
            self.message_view = message_view
            yield message_view

    def on_mount(self):
        self._ensure_columns(self.services_table, _SERVICE_HEADERS, _SERVICE_JUSTIFY)
        self._ensure_columns(self.entrypoints_table, _ENTRY_HEADERS, _ENTRY_JUSTIFY)
        self._sync_value_input_state()

    def _session_group_filter(self):
        return current_group_filter(self.app)

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
        if event.input.id == "entrypoints_value":
            self._render_services()

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
        if event.select.id == "entrypoints_field":
            self._sync_value_input_state()
            self._render_services()

    async def action_refresh_entrypoints(self):
        logging.info("action_refresh_entrypoints called")
        await self.update_table()

    def action_replay(self):
        self._confirm_oldest_failed(
            "Replay oldest failed message for %s %s ? [y/n]",
            "replay_failed",
        )

    def action_drop(self):
        self._confirm_oldest_failed(
            "Drop oldest failed message for %s %s ? [y/n]",
            "drop_failed",
        )

    def _confirm_oldest_failed(self, prompt, action):
        if self.entrypoints_table is None or not self.entrypoints_table.has_focus:
            return
        row = self._selected_entrypoint()
        if not row or not row["competing"]:
            return
        key = (row["service_name"], row["event_name"])
        if key in self._unavailable:
            self.app._show_error_prompt(self._unavailable[key])
            return
        count = self._counts.get(key)
        if count is None or count < 1:
            return
        show_confirm(
            self.app,
            self,
            prompt % (row["service_name"], row["name"]),
            action,
            {"service_name": row["service_name"], "event_name": row["event_name"]},
        )

    @on(ConfirmPrompt.Result)
    async def on_confirm_prompt_result(self, event):
        if not event.confirmed:
            return
        if event.action == "replay_failed":
            await self._apply_oldest_failed(event, "replay")
        elif event.action == "drop_failed":
            await self._apply_oldest_failed(event, "drop")

    async def _apply_oldest_failed(self, event, kind):
        backend = self.app.services
        if backend is None:
            return
        service_name = event.payload["service_name"]
        event_name = event.payload["event_name"]
        if kind == "replay":
            call = backend.replay_failed_messages
            counted = "replayed"
            started = "Replay oldest failed message for %s %s"
            finished = "Replayed %s failed message(s) for %s %s"
            failed = "replay_failed_messages failed: %s"
        else:
            call = backend.drop_failed_messages
            counted = "dropped"
            started = "Drop oldest failed message for %s %s"
            finished = "Dropped %s failed message(s) for %s %s"
            failed = "drop_failed_messages failed: %s"
        logging.info(started, service_name, event_name)
        try:
            result = await call(service_name, event_name, 1)
        except RpcClientError as exc:
            if exc.code == "ENTRYPOINT_UNAVAILABLE":
                self.app._show_error_prompt(exc.message)
                return
            logging.warning(failed, exc)
            self.app._show_error_prompt(_UNREACHABLE)
            return
        except RpcTimeoutError:
            self.app._show_error_prompt(_UNREACHABLE)
            return
        except Exception as exc:
            logging.error(failed, exc, exc_info=True)
            self.app._show_error_prompt(_UNREACHABLE)
            return
        logging.info(finished, result[counted], service_name, event_name)
        await self.update_table()

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event):
        if self._rendering:
            return
        control_id = event.control.id
        if control_id == "entrypoints_services_table":
            self._render_entrypoints(self._selected_line_key())
        elif control_id == "entrypoints_table":
            self._render_message()

    async def update_table(self):
        if self.services_table is None:
            return
        backend = self.app.services
        if backend is None:
            logging.error("Services backend instance not available on app")
            return
        try:
            raw_services = await backend.get_services()
        except Exception as exc:
            logging.error("Error getting services from backend: %s", exc, exc_info=True)
            return
        if self.group_filter_select is not None:
            await refresh_group_filter_options(self.app)
        rows = build_service_rows(raw_services, self._session_group_filter())
        counts, bodies, unavailable = await self._load_failed(backend, rows)
        self._services_cache = rows
        self._counts = counts
        self._bodies = bodies
        self._unavailable = unavailable
        logging.info("Entrypoints refreshed: %s service(s)", len(rows))
        self._render_services()

    async def _load_failed(self, backend, rows):
        counts = {}
        bodies = {}
        unavailable = {}
        for row in rows:
            if row["catalogue"] != "ok":
                continue
            seen = []
            for entry in row["entrypoints"]:
                if not entry["competing"]:
                    continue
                event_name = entry["event_name"]
                if event_name in seen:
                    continue
                seen.append(event_name)
                key = (row["service_name"], event_name)
                try:
                    listed = await backend.list_failed_messages(
                        row["service_name"], event_name, 1
                    )
                except RpcClientError as exc:
                    if exc.code == "ENTRYPOINT_UNAVAILABLE":
                        logging.warning(
                            "list_failed_messages refused for %s %s: %s",
                            row["service_name"],
                            event_name,
                            exc.message,
                        )
                        unavailable[key] = exc.message
                        continue
                    logging.warning(
                        "list_failed_messages failed for %s %s: %s",
                        row["service_name"],
                        event_name,
                        exc,
                    )
                    self.app._show_error_prompt(_UNREACHABLE)
                    return counts, bodies, unavailable
                except Exception as exc:
                    logging.warning(
                        "list_failed_messages failed for %s %s: %s",
                        row["service_name"],
                        event_name,
                        exc,
                    )
                    self.app._show_error_prompt(_UNREACHABLE)
                    return counts, bodies, unavailable
                counts[key] = listed["count"]
                messages = listed["messages"]
                bodies[key] = messages[0] if messages else None
        return counts, bodies, unavailable

    def _render_services(self):
        if self.services_table is None:
            return
        self._rendering += 1
        try:
            self._render_services_body()
        finally:
            self._rendering -= 1

    def _render_services_body(self):
        self._ensure_columns(self.services_table, _SERVICE_HEADERS, _SERVICE_JUSTIFY)
        selected_service = self._selected_name(self.services_table, self._service_rows)
        selected_entry = self._selected_line_key()
        field, value = self._get_filter_state()
        filtered = apply_entrypoint_service_filter(self._services_cache, field, value)
        service_rows = [self._service_cells(row) for row in filtered]
        self._fit_columns(self.services_table, _SERVICE_HEADERS, service_rows)
        self.services_table.clear()
        self._service_rows = {}
        if filtered:
            keys = self.services_table.add_rows(service_rows)
            for key, row in zip(keys, filtered):
                self._service_rows[key] = row
            self._move_to(
                self.services_table,
                filtered,
                lambda row: row["service_name"] == selected_service,
            )
        self._render_entrypoints(selected_entry)

    def _render_entrypoints(self, restore_key=None):
        if self.entrypoints_table is None:
            return
        self._ensure_columns(self.entrypoints_table, _ENTRY_HEADERS, _ENTRY_JUSTIFY)
        service = self._selected_service()
        self.entrypoints_table.clear()
        self._entrypoint_rows = {}
        if service:
            visible = []
            for entry in service["entrypoints"]:
                item = dict(entry)
                item["service_name"] = service["service_name"]
                visible.append(item)
            if visible:
                entry_rows = [self._entry_cells(entry) for entry in visible]
                self._fit_columns(self.entrypoints_table, _ENTRY_HEADERS, entry_rows)
                keys = self.entrypoints_table.add_rows(entry_rows)
                for key, entry in zip(keys, visible):
                    self._entrypoint_rows[key] = entry
                if restore_key is not None:
                    self._move_to(
                        self.entrypoints_table,
                        visible,
                        lambda entry: line_key(entry) == restore_key,
                    )
        self._render_message()

    def _render_message(self):
        if self.message_view is None:
            return
        entry = self._selected_entrypoint()
        body = None
        if entry and entry["competing"]:
            body = self._bodies.get((entry["service_name"], entry["event_name"]))
        self.message_view.text = _format_body(body)

    def _service_cells(self, row):
        values = (
            row["service_name"],
            str(row["instances"]),
            row["catalogue"],
            service_failed_display(row, self._counts),
        )
        return tuple(
            _text(value, justify) for value, justify in zip(values, _SERVICE_JUSTIFY)
        )

    def _entry_cells(self, entry):
        failed = entrypoint_failed_display(entry["service_name"], entry, self._counts)
        if not entry["competing"]:
            failed_cell = _na()
        else:
            failed_cell = _text(failed, "center")
        return (
            _text(entry["type"], "left"),
            _text(entry["name"], "left"),
            _text(entry["handler"], "left"),
            _value_or_na(entry["mode"]),
            _value_or_na(entry["attempts"]),
            _text(entry["declared"], "center"),
            failed_cell,
        )

    def _selected_service(self):
        return self._selected_row(self.services_table, self._service_rows)

    def _selected_entrypoint(self):
        return self._selected_row(self.entrypoints_table, self._entrypoint_rows)

    def _selected_line_key(self):
        entry = self._selected_entrypoint()
        if not entry:
            return None
        return line_key(entry)

    def _selected_name(self, table, row_map):
        row = self._selected_row(table, row_map)
        if not row:
            return None
        return row.get("service_name")

    def _selected_row(self, table, row_map):
        if table is None:
            return None
        cursor_row = table.cursor_row
        if cursor_row is None:
            return None
        row_keys = list(table.rows.keys())
        if cursor_row < 0 or cursor_row >= len(row_keys):
            return None
        return row_map.get(row_keys[cursor_row])

    def _move_to(self, table, rows, predicate):
        for index, row in enumerate(rows):
            if predicate(row):
                table.move_cursor(row=index)
                return

    def _ensure_columns(self, table, headers, justifies):
        if table is not None and len(table.columns) == 0:
            for label, justify in zip(headers, justifies):
                table.add_column(Text(label, justify=justify))

    def _fit_columns(self, table, headers, rows):
        # Set the width before the first paint. Auto width measures the
        # centered cells on idle, after a render has cached them clipped
        # to the header.
        widths = [cell_len(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                width = cell.cell_len
                if width > widths[index]:
                    widths[index] = width
        for column, width in zip(table.ordered_columns, widths):
            column.auto_width = False
            column.width = width
            column.content_width = width


def _text(value, justify):
    return Text(str(value), justify=justify)


def _na():
    return Text("n/a", style="dim", justify="center")


def _value_or_na(value):
    if value:
        return _text(value, "center")
    return _na()


def _format_body(body):
    if body is None:
        return ""
    try:
        return json.dumps(body, indent=2, sort_keys=True)
    except TypeError:
        return repr(body)
