from textual.widgets import Static, TabbedContent

from kontiki_tui.components.events import EventsTab
from kontiki_tui.components.exceptions import ExceptionsTab
from kontiki_tui.components.log import LogTab
from kontiki_tui.components.services import ServicesTab
from kontiki_tui.components.settings import SettingsTab

# -----------------------------------------------------------------------------


class KontikiTabs(Static):
    class KontikiContent(TabbedContent):
        def __init__(self):
            super().__init__(
                "Services",
                "Events",
                "Exceptions",
                "Logs",
                "Settings",
                id="kontiki_tabs",
            )

    def __init__(self):
        super().__init__(id="commands")

    def compose(self):
        with self.KontikiContent():
            yield ServicesTab(id_="services")
            yield EventsTab(id_="events")
            yield ExceptionsTab(id_="exceptions")
            yield LogTab(id_="log")
            yield SettingsTab(id_="settings")
