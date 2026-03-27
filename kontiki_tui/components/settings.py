import logging
import os
from pathlib import Path

import yaml
from textual.message import Message
from textual.widgets import Button, Static, TextArea

from kontiki_tui.config import BASE_CONF

# -----------------------------------------------------------------------------


class SettingsTab(Static):
    class SettingsSave(Message):
        def __init__(self, yaml):
            super().__init__()
            self.yaml = yaml

    def __init__(self, id_):
        super().__init__(id=id_)
        self._path = os.path.join(Path.home(), ".config", "kontiki_tui.yaml")

    def compose(self):
        settings = TextArea(language="yaml", id="kontiki_tui_settings")
        if os.path.exists(self._path):
            with open(self._path, "r") as fid:
                settings.load_text(fid.read())
        else:
            settings.load_text(yaml.dump(BASE_CONF))
        settings.border_title = "KontikiTUI settings"
        yield settings
        yield Button("Save & Reload", id="save_settings_button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "save_settings_button":
            try:
                # Get the content from the TextArea
                settings_textarea = self.query_one("#kontiki_tui_settings", TextArea)
                yaml_content = settings_textarea.text
                # Send the SettingsSave message with the YAML content
                self.post_message(self.SettingsSave(yaml_content))
            except Exception as e:
                logger = logging.getLogger("kontiki_tui")
                logger.error(f"Error getting settings content: {e}", exc_info=True)
                # type: ignore
                self.app._show_error_prompt(f"Error reading settings: {e}")
