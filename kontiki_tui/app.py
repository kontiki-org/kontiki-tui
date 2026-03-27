import logging
import os
from pathlib import Path
from typing import Type

from kontiki.messaging import Messenger
from textual import on, work
from textual.app import App
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, RichLog, TabbedContent

from kontiki_tui.backend.log import get_log, is_lnav_available
from kontiki_tui.backend.services import Services
from kontiki_tui.components.events import EventsTab
from kontiki_tui.components.exceptions import ExceptionsTab
from kontiki_tui.components.log import LogTab, render_log_output
from kontiki_tui.components.prompt import ErrorPrompt, InfoPrompt, Prompt
from kontiki_tui.components.services import ServicesTab
from kontiki_tui.components.settings import SettingsTab
from kontiki_tui.components.tabs import KontikiTabs
from kontiki_tui.config import BASE_CONF, load

# -----------------------------------------------------------------------------

# Application file logging (debugging); normal app output is the TUI.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="kontiki_tui.log",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


CONF_FILE = os.path.join(Path.home(), ".config", "kontiki_tui.yaml")


# -----------------------------------------------------------------------------


def _select_css_path() -> str:
    user_css = Path.home() / ".config" / "kontiki_tui.tcss"
    pkg_css = Path(__file__).with_name("app.css")

    if user_css.is_file():
        return str(user_css)
    if pkg_css.is_file():
        return str(pkg_css)

    # No CSS found: log a clear error and exit cleanly.
    msg = (
        "No CSS file found for kontiki_tui UI.\n"
        f"Expected either '{user_css}' or '{pkg_css}'.\n"
        "Please create one of these files (you can copy the packaged app.css "
        "into ~/.config/kontiki_tui.tcss) and retry."
    )
    logging.getLogger("kontiki_tui").error(msg)
    raise SystemExit(msg)


class KontikiTuiApp(App):
    CSS_PATH = _select_css_path()

    BINDINGS = [
        Binding(key="q", action="quit", description="Quit the app"),
    ]

    def __init__(self):
        super().__init__()
        self.messenger = None
        self._amqp_url = None
        self.conf = {}
        self.services = None

    async def action_quit(self) -> None:
        if self.messenger is not None:
            try:
                await self.messenger.stop()
            except Exception as e:
                logging.getLogger("kontiki_tui").warning(
                    f"Error while stopping messenger during quit: {e}", exc_info=True
                )
        self.exit()

    def compose(self):
        yield Header(show_clock=True)
        yield KontikiTabs()
        yield Container(id="prompt-area")
        yield Footer(id="app_footer")  # type: ignore[attr-defined]

    def _show_prompt(
        self,
        message: str,
        timeout: float = 5.0,
        prompt_type: Type[Prompt] = ErrorPrompt,
    ) -> None:
        logger = logging.getLogger("kontiki_tui")
        try:
            prompt_area = self.query_one("#prompt-area")
            prompt_area.remove_children()
            prompt_area.mount(prompt_type(message, timeout))
            logger.info(f"{prompt_type.__name__} shown: {message}")
        except Exception as e:
            logger.error(
                f"Could not display {prompt_type.__name__} in prompt: {e}",
                exc_info=True,
            )

    def _show_error_prompt(self, message: str, timeout: float = 5.0) -> None:
        self._show_prompt(message, timeout, ErrorPrompt)

    def _show_info_prompt(self, message: str, timeout: float = 5.0) -> None:
        self._show_prompt(message, timeout, InfoPrompt)

    @work(thread=True, exclusive=True, exit_on_error=False)
    def load_logs_worker(self, pattern: str, exclude_noise: bool) -> None:
        """Background worker to load logs with lnav without blocking the UI."""
        logger = logging.getLogger("kontiki_tui")
        try:
            logger.info(
                "load_logs_worker started (pattern=%r, exclude_noise=%s)",
                pattern,
                exclude_noise,
            )
            logs_conf = self.conf.get("logs", {})
            log_folder = logs_conf.get("directory")
            if not log_folder:
                logger.error("Log directory not configured under 'logs.directory'")
                return

            filter_out = logs_conf.get("filter-out", []) if exclude_noise else []
            # If not configured by the user, fall back to the default in BASE_CONF.
            max_lines = logs_conf.get(
                "max-lines", BASE_CONF.get("logs", {}).get("max-lines")
            )

            raw_output = get_log(pattern, log_folder, filter_out, max_lines=max_lines)

            def update_ui() -> None:
                try:
                    log_tab = self.query_one("#log", LogTab)
                    log_widget = log_tab.query_one("#logs", RichLog)
                    render_log_output(raw_output, pattern, log_widget)
                except Exception as e:
                    logger.warning(f"Could not update logs view: {e}", exc_info=True)

            self.call_from_thread(update_ui)
            logger.info(
                "load_logs_worker finished (pattern=%r, exclude_noise=%s, bytes=%d)",
                pattern,
                exclude_noise,
                len(raw_output),
            )
        except Exception as e:
            logger.warning(f"Error in load_logs_worker: {e}", exc_info=True)

    async def _init_from_conf(self):
        self.conf = load(CONF_FILE)

        # Initialize AMQP messenger safely to avoid crashing on bad configuration.
        try:
            amqp_url = self.conf["amqp"]["url"]
        except Exception as e:
            logger.error(
                f"AMQP URL not configured correctly in conf file {CONF_FILE}: {e}",
                exc_info=True,
            )
            self._show_error_prompt(
                "AMQP URL is not configured correctly in kontiki_tui.yaml",
                timeout=10.0,
            )
            return False
        # Close existing messenger and recreate only if AMQP URL changed.
        old_url = self._amqp_url
        old_messenger = self.messenger
        url_changed = old_url is not None and old_url != amqp_url

        # Close existing messenger only if URL changed (or if we need to recreate).
        if old_messenger is not None and url_changed:
            try:
                logger.info(
                    f"AMQP URL changed from '{old_url}' to '{amqp_url}', stopping "
                    "existing messenger."
                )
                await old_messenger.stop()
            except Exception as e:
                logger.warning(
                    f"Error while stopping previous messenger: {e}", exc_info=True
                )
            # Clear the reference after stopping
            self.messenger = None

        # Create or re-create the messenger only if needed (no messenger yet,
        # or URL has changed).
        if old_messenger is None or url_changed:
            try:
                self.messenger = Messenger(
                    amqp_url=amqp_url,
                    standalone=True,
                    client_name="kontiki_tui",
                )
                await self.messenger.setup()
            except Exception as e:
                logger.error(
                    f"Failed to set up AMQP messenger with URL '{amqp_url}': {e}",
                    exc_info=True,
                )
                # Do not crash the TUI; instead, display a clear error to the user.
                self.messenger = None
                self._show_error_prompt(
                    f"Cannot connect to AMQP broker with URL: {amqp_url}",
                    timeout=10.0,
                )
                return False

        # Remember the URL we successfully initialized with.
        self._amqp_url = amqp_url

        self.services = Services(self.messenger)

        # Initialize focus for the default tab (View) after configuration load
        # to avoid focus conflicts during mount
        self.call_after_refresh(self._init_default_tab_focus)

        return True

    async def on_mount(self):
        self.title = "KontikiTUI"
        self.sub_title = "Kontiki monitoring software."

        await self._init_from_conf()
        if not is_lnav_available():
            self._show_info_prompt(
                "lnav is not installed: using Python log fallback (reduced filtering).",
                timeout=8.0,
            )

    def _init_default_tab_focus(self) -> None:
        """Initialize focus for the default tab (View) at startup."""
        try:
            service_tab = self.query_one("#services", ServicesTab)
            if service_tab.services_table is not None:
                service_tab.services_table.focus()
        except Exception as e:
            logging.getLogger("kontiki_tui").warning(
                f"Could not initialize default tab focus: {e}", exc_info=True
            )

    @on(TabbedContent.TabActivated)
    async def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        tab_id = event.tab.id if hasattr(event.tab, "id") else None
        tab_label_raw = event.tab.label if hasattr(event.tab, "label") else None
        tab_label = str(tab_label_raw) if tab_label_raw is not None else None
        logging.getLogger("kontiki_tui").info(
            f"Tab activated: id={tab_id}, label={tab_label}"
        )

        if tab_label == "Services":
            services_tab = self.query_one("#services", ServicesTab)
            self.run_worker(services_tab.update_table())
            if services_tab.services_table is not None:
                services_tab.services_table.focus()
        elif tab_label == "Logs":
            log_tab = self.query_one("#log", LogTab)
            log_tab.action_refresh_logs()
        elif tab_label == "Events":
            events_tab = self.query_one("#events", EventsTab)
            self.run_worker(events_tab.update_table())
            if events_tab.events_table is not None:
                events_tab.events_table.focus()
        elif tab_label == "Exceptions":
            exceptions_tab = self.query_one("#exceptions", ExceptionsTab)
            self.run_worker(exceptions_tab.update_table())
            if exceptions_tab.exceptions_table is not None:
                exceptions_tab.exceptions_table.focus()

    @on(LogTab.UpdateLog)
    def on_update_log(self, event: LogTab.UpdateLog) -> None:
        """Start log loading in background without blocking the UI."""
        logger = logging.getLogger("kontiki_tui")
        try:
            log_tab = self.query_one("#log", LogTab)
            log_widget = log_tab.query_one("#logs", RichLog)
            log_widget.clear()
            log_widget.write("Loading logs...")
            # Launch background worker; returns immediately
            self.load_logs_worker(event.pattern, event.exclude_noise)
        except Exception as e:
            logger.warning(f"Could not start log worker: {e}", exc_info=True)

    @on(SettingsTab.SettingsSave)
    async def on_settings_save(self, event: SettingsTab.SettingsSave) -> None:
        """Handle Save & Reload from the Settings tab."""
        logger = logging.getLogger("kontiki_tui")
        try:
            # Write new YAML configuration to disk.
            with open(CONF_FILE, "w") as fid:
                fid.write(event.yaml)
            logger.info(f"Configuration saved to {CONF_FILE}")
        except Exception as e:
            logger.error(
                f"Error saving configuration to {CONF_FILE}: {e}", exc_info=True
            )
            self._show_error_prompt(f"Error saving configuration: {e}")
            return

        # Re-initialize the app from the updated configuration.
        success = await self._init_from_conf()
        if success:
            self._show_info_prompt("Configuration reloaded successfully", timeout=3.0)
        # If initialization failed, _init_from_conf() already displayed an error message


def main():
    KontikiTuiApp().run()


if __name__ == "__main__":
    main()
