import json
import logging

from kontiki.messaging.flow import short_instance_id
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Label, Select, Static, TextArea

from kontiki_tui.backend.services import (
    format_degraded_reason,
    format_last_heartbeat,
    matches_group_filter,
    normalize_registration_group,
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

_BASE_HEADERS = {
    "service_name": "Service ID",
    "instance_id": "Short Instance ID",
    "service_version": "Version",
    "kontiki_version": "Kontiki",
    "status": "Status",
    "host": "Host",
    "pid": "PID",
    "last_heartbeat": "Last Heartbeat",
    "degraded_reason": "Degraded Reason",
}

_FIELD_OPTIONS = [
    ("All", "all"),
    ("Service Name", "service_name"),
    ("Instance ID", "instance_id"),
    ("Status", "status"),
    ("Host", "host"),
    ("Version", "service_version"),
    ("Kontiki", "kontiki_version"),
]


def apply_service_field_filter(rows, field, value):
    """Keep rows matching Field/Value (substring, case-insensitive).

    ``all`` or empty value returns the list unchanged. Instance ID matches
    the displayed short id and the full UUID in metadata. Status matches
    the raw registry status, not the emoji.
    """
    if not field or field == "all" or not value:
        return list(rows)
    expected = value.lower()
    return [row for row in rows if _service_row_matches_field(row, field, expected)]


def _service_row_matches_field(row, field, expected):
    if field == "instance_id":
        short = str(row.get("instance_id", "")).lower()
        metadata = row.get("metadata") or {}
        full = str(metadata.get("instance_id", "")).lower()
        return expected in short or expected in full
    return expected in str(row.get(field, "")).lower()


class ServicesTab(Static):
    BINDINGS = [
        Binding("r", "refresh_services", description="Refresh services table"),
    ]

    def __init__(self, id_="services"):
        super().__init__(id=id_)
        self.services_table = None
        self.config_view = None
        self.field_input = None
        self.value_input = None
        self.group_filter_select = None
        self.row_data_map = {}  # Map row_key -> dict of original values
        self._services_cache = []
        self.headers = dict(_BASE_HEADERS)

    def _headers_for_filter(self, group_filter):
        headers = dict(_BASE_HEADERS)
        if group_filter == "all":
            # Insert group after the two version columns when showing the full fleet.
            ordered = {}
            for key, label in _BASE_HEADERS.items():
                ordered[key] = label
                if key == "kontiki_version":
                    ordered["group"] = "Group"
            return ordered
        return headers

    def _add_table_columns(self):
        for index, (key, label) in enumerate(self.headers.items()):
            if index == 0:
                self.services_table.add_column(label)
                continue
            header = Text(str(label), justify="center")
            # Header "Kontiki" is as wide as "1.10.0"; a min width lets both center.
            if key == "kontiki_version":
                self.services_table.add_column(header, width=11)
            else:
                self.services_table.add_column(header)

    def compose(self):
        with Vertical(id="services_split"):
            with Horizontal(id="services_filters"):
                yield Label("Field:")
                self.field_input = Select(
                    options=_FIELD_OPTIONS,
                    value="all",
                    id="services_field",
                )
                yield self.field_input
                yield Label("Value:")
                self.value_input = Input(
                    placeholder="filter value", id="services_value"
                )
                yield self.value_input
                label, select = make_group_filter_select(
                    self.app, "services_group_filter"
                )
                self.group_filter_select = select
                yield label
                yield select
            table = DataTable(
                id="services_table",
                classes="datatables",
                cursor_type="row",
            )
            self.services_table = table
            table.border_title = "Services"
            yield table
            config_view = TextArea(
                id="service_config",
                language="json",
                read_only=True,
            )
            config_view.border_title = "Configuration"
            self.config_view = config_view
            yield config_view

    def _session_group_filter(self):
        return current_group_filter(self.app)

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
        if event.input.id == "services_value":
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
        if event.select.id == "services_field":
            self._sync_value_input_state()
            self._render_table_from_cache()

    async def action_refresh_services(self) -> None:
        """Refresh the services table from the registry."""
        logging.info("action_refresh_services called")
        await self.update_table()

    def _status_to_emoji(self, status: str) -> str:
        """Convert status text to emoji."""
        status_lower = status.lower() if status else ""
        if status_lower == "active":
            return "🟢"
        elif status_lower == "degraded":
            return "🟠"
        elif status_lower == "down":
            return "🔴"
        else:
            return status  # Return original if unknown

    def _row_to_tuple(self, row_dict: dict) -> tuple:
        """Convert an internal row dict to a tuple in the correct column order."""
        display_dict = row_dict.copy()
        display_dict["status"] = self._status_to_emoji(row_dict.get("status", ""))
        cells = []
        for index, key in enumerate(self.headers.keys()):
            value = str(display_dict.get(key, "") or "")
            if index == 0:
                cells.append(value)
            else:
                cells.append(Text(value, justify="center"))
        return tuple(cells)

    async def update_table(self) -> None:
        """Fetch services from backend and update the services table."""
        if self.services_table is None:
            # The table has not been created yet; this should not normally happen,
            # but guard against it to avoid hard crashes.
            try:
                self.services_table = self.query_one("#services_table", DataTable)
            except Exception as e:
                logging.error(f"Analyses table not available: {e}", exc_info=True)
                return

        services_backend = getattr(self.app, "services", None)
        if services_backend is None:
            logging.error("Services backend instance not available on app")
            return

        try:
            raw_services = await services_backend.get_services()
        except Exception as e:
            logging.error(f"Error getting services from backend: {e}", exc_info=True)
            return

        group_filter = self._session_group_filter()
        if self.group_filter_select is not None:
            await refresh_group_filter_options(self.app, self.group_filter_select)
        self.headers = self._headers_for_filter(group_filter)

        cache = []
        for service_name, instances in raw_services.items():
            if not isinstance(instances, dict):
                continue
            for instance_id, entry in instances.items():
                if not isinstance(entry, dict):
                    continue

                status = entry.get("status", "")
                metadata = entry.get("metadata", {}) or {}
                config = metadata.get("config", {})

                group = normalize_registration_group(metadata.get("group"))
                if not matches_group_filter(group, group_filter):
                    continue

                pid = metadata.get("pid", "")
                host = metadata.get("host", "")
                version = metadata.get("service_version", "")
                kontiki_version = metadata.get("kontiki_version", "")

                full_instance_id = metadata.get("instance_id", instance_id)
                cache.append(
                    {
                        "service_name": metadata.get("service_name", service_name),
                        "instance_id": short_instance_id(str(full_instance_id or "")),
                        "status": status,
                        "last_heartbeat": format_last_heartbeat(
                            entry.get("last_heartbeat")
                        ),
                        "degraded_reason": format_degraded_reason(
                            entry.get("degraded_reason")
                        ),
                        "pid": pid,
                        "host": host,
                        "service_version": version,
                        "kontiki_version": kontiki_version,
                        "group": group,
                        # Extra fields not displayed in the table but used
                        # for the config view
                        "config": config,
                        "metadata": metadata,
                    }
                )

        self._services_cache = cache
        if not cache:
            logging.warning("No services to display")
        else:
            logging.info("Cached %s service instance(s)", len(cache))

        # Rebuild columns so business vs all can show/hide the group column.
        self.services_table.clear(columns=True)
        self._add_table_columns()
        logging.info(f"Added {len(self.headers)} columns to services table")

        self._render_table_from_cache()
        logging.info("Services table updated successfully")

    def _render_table_from_cache(self):
        if self.services_table is None:
            try:
                self.services_table = self.query_one("#services_table", DataTable)
            except Exception as e:
                logging.error(f"Analyses table not available: {e}", exc_info=True)
                return

        if len(self.services_table.columns) == 0:
            self._add_table_columns()

        field, value = self._get_filter_state()
        filtered = apply_service_field_filter(self._services_cache, field, value)
        rows = [self._row_to_tuple(row_dict) for row_dict in filtered]

        self.services_table.clear()
        self.row_data_map = {}
        if rows:
            row_keys = self.services_table.add_rows(rows)
            for row_key, row_dict in zip(row_keys, filtered):
                self.row_data_map[row_key] = row_dict
        else:
            self._update_config_view({})

        self.services_table.refresh()

    def _get_row_values(self, row_key) -> dict:
        """Return a copy of the stored row values for a given row key."""
        if row_key in self.row_data_map:
            return self.row_data_map[row_key].copy()

        logging.warning(f"Row key {row_key} not found in services row_data_map")
        return {}

    def _update_config_view(self, row_values: dict | None) -> None:
        """Update the JSON config view based on the selected service."""
        if self.config_view is None:
            try:
                self.config_view = self.query_one("#service_config", TextArea)
            except Exception as e:
                logging.error(f"Config view widget not available: {e}", exc_info=True)
                return

        if not row_values:
            self.config_view.text = ""
            return

        # Prefer an explicit "config" field if present in metadata,
        # otherwise show metadata
        config = row_values.get("config")
        if config is None:
            metadata = row_values.get("metadata", {})
            config = metadata.get("config", metadata)

        try:
            self.config_view.text = json.dumps(config, indent=2, sort_keys=True)
        except TypeError:
            # Fallback if config contains non-serializable objects
            self.config_view.text = repr(config)

    @on(DataTable.RowHighlighted)
    @on(DataTable.RowSelected)
    def on_row_changed(self, event) -> None:
        """When the selected service changes, update the config view."""
        if self.services_table is None:
            return

        cursor_row = event.cursor_row
        if cursor_row is None:
            return

        # Convert cursor_row index to actual row key
        # cursor_row is an index (0, 1, 2...), but we need the actual row key
        row_keys = list(self.services_table.rows.keys())
        if cursor_row < len(row_keys):
            row_key = row_keys[cursor_row]
            row_values = self._get_row_values(row_key)
            self._update_config_view(row_values)
        else:
            logging.warning(
                f"cursor_row {cursor_row} out of range (max: {len(row_keys) - 1})"
            )
