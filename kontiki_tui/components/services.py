import json
import logging

from textual import on
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Static, TextArea

# -----------------------------------------------------------------------------


class ServicesTab(Static):
    BINDINGS = [
        Binding("r", "refresh_services", description="Refresh services table"),
    ]

    def __init__(self, id_="services"):
        super().__init__(id=id_)
        self.services_table = None
        self.config_view = None
        self.row_data_map = {}  # Map row_key -> dict of original values
        self.headers = {
            "service_name": "Service Name",
            "instance_id": "Service Instance ID",
            "status": "Status",
            "pid": "PID",
            "host": "Host",
            "service_version": "Version",
            "cpu_percent": "CPU (%)",
            "mem_mb": "Memory (MB)",
            "fd_count": "Open FDs",
        }

    def compose(self):
        with Vertical(id="services_split"):
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

    def on_mount(self) -> None:
        # Focus will be set when the tab is activated, not on mount
        # to avoid focus conflicts between tabs
        # Start a periodic refresh of psutil-based stats (CPU, MEM, FDs)
        # without re-querying the service registry each time.
        self.set_interval(5.0, self._refresh_stats_only)

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
        # Create a copy and convert status to emoji for display
        display_dict = row_dict.copy()
        display_dict["status"] = self._status_to_emoji(row_dict.get("status", ""))
        return tuple(display_dict.get(key, "") for key in self.headers.keys())

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

        rows = []
        row_data_list = []  # Temporary list to store row_dicts in order

        for service_name, instances in raw_services.items():
            if not isinstance(instances, dict):
                continue
            for instance_id, entry in instances.items():
                if not isinstance(entry, dict):
                    continue

                status = entry.get("status", "")
                metadata = entry.get("metadata", {}) or {}
                config = metadata.get("config", {})

                pid = metadata.get("pid", "")
                host = metadata.get("host", "")
                version = metadata.get("service_version", "")

                # Stats CPU/memory/I/O, retrieved via get_stats(pid, host)
                stats = {}
                if pid and host:
                    try:
                        # Convert pid to int if it's a string
                        pid_for_stats = (
                            int(pid) if isinstance(pid, str) and pid.isdigit() else pid
                        )
                        stats = services_backend.get_stats(pid_for_stats, host)
                        logging.debug(
                            f"Stats for PID {pid_for_stats} on {host}: {stats}"
                        )
                    except (ValueError, TypeError) as e:
                        logging.warning(f"Invalid PID format '{pid}': {e}")
                        stats = {}
                    except Exception as e:
                        logging.warning(
                            f"Error getting stats for pid {pid}: {e}", exc_info=True
                        )
                        stats = {}

                # If we have enough metadata but can't collect stats
                # (e.g. docker/remote), show N/A instead of empty cells.
                stats_available = bool(stats) if (pid and host) else False
                cpu_value = (
                    stats.get("cpu_percent", "")
                    if stats_available
                    else ("N/A" if (pid and host) else "")
                )
                mem_value = (
                    stats.get("mem_mb", "")
                    if stats_available
                    else ("N/A" if (pid and host) else "")
                )
                fd_value = (
                    stats.get("fd_count", "")
                    if stats_available
                    else ("N/A" if (pid and host) else "")
                )

                row_dict = {
                    "service_name": metadata.get("service_name", service_name),
                    "instance_id": metadata.get("instance_id", instance_id),
                    "status": status,
                    "pid": pid,
                    "host": host,
                    "service_version": version,
                    "cpu_percent": cpu_value,
                    "mem_mb": mem_value,
                    "fd_count": fd_value,
                    # Extra fields not displayed in the table but used
                    # for the config view
                    "config": config,
                    "metadata": metadata,
                }

                rows.append(self._row_to_tuple(row_dict))
                row_data_list.append(row_dict)

        # Add columns if they don't exist yet
        if len(self.services_table.columns) == 0:
            self.services_table.add_columns(*tuple(self.headers.values()))
            logging.info(f"Added {len(self.headers)} columns to services table")

        self.services_table.clear()
        self.row_data_map = {}  # Reset the mapping
        if rows:
            # add_rows returns the row keys that Textual generated
            row_keys = self.services_table.add_rows(rows)
            # Map the returned row keys to our row_dicts
            for row_key, row_dict in zip(row_keys, row_data_list):
                self.row_data_map[row_key] = row_dict
            logging.info(f"Added {len(rows)} rows to services table")
        else:
            logging.warning("No services to display")

        self.services_table.refresh()
        logging.info("Services table updated successfully")

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

    def _refresh_stats_only(self) -> None:
        """Refresh only psutil-based stats (CPU, MEM, FDs) for local services."""
        if self.services_table is None or not self.row_data_map:
            return

        services_backend = getattr(self.app, "services", None)
        if services_backend is None:
            logging.error("Services backend instance not available on app")
            return

        for row_key, row_dict in self.row_data_map.items():
            pid = row_dict.get("pid")
            host = row_dict.get("host")
            if not pid or not host:
                continue

            try:
                stats = services_backend.get_stats(pid, host)
            except Exception as e:
                logging.warning(
                    f"Error refreshing stats for pid {pid}: {e}", exc_info=True
                )
                continue

            if not stats:
                continue

            # Update the values in memory
            row_dict["cpu_percent"] = stats.get("cpu_percent", "")
            row_dict["mem_mb"] = stats.get("mem_mb", "")
            row_dict["fd_count"] = stats.get("fd_count", "")

            # Update the cells in the DataTable with update_cell
            # row_key is the actual row key returned by add_rows()

            # Check that the row exists in the table
            if row_key not in self.services_table.rows:
                logging.warning(f"Row key {row_key} not found in services table")
                continue

            # Get the actual column keys from the DataTable
            column_keys = list(self.services_table.columns.keys())
            try:
                # Find the indices of the columns to update
                cpu_col_idx = list(self.headers.keys()).index("cpu_percent")
                mem_col_idx = list(self.headers.keys()).index("mem_mb")
                fd_col_idx = list(self.headers.keys()).index("fd_count")

                # Check that the indices are valid
                if (
                    cpu_col_idx < len(column_keys)
                    and mem_col_idx < len(column_keys)
                    and fd_col_idx < len(column_keys)
                ):
                    self.services_table.update_cell(
                        row_key, column_keys[cpu_col_idx], row_dict["cpu_percent"]
                    )
                    self.services_table.update_cell(
                        row_key, column_keys[mem_col_idx], row_dict["mem_mb"]
                    )
                    self.services_table.update_cell(
                        row_key, column_keys[fd_col_idx], row_dict["fd_count"]
                    )
                else:
                    logging.warning(f"Column indices out of range for row {row_key}")
            except Exception as e:
                logging.warning(
                    f"Error updating services table row {row_key}: {e}",
                    exc_info=True,
                )
