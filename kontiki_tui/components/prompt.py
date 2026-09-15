import logging

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static


class ConfirmPrompt(Static):
    can_focus = True

    BINDINGS = [
        Binding("y", "confirm", show=False),
        Binding("n", "cancel", show=False),
        Binding("escape", "cancel", show=False),
    ]

    class Result(Message):
        def __init__(self, confirmed, action, payload=None):
            self.confirmed = confirmed
            self.action = action
            self.payload = payload or {}
            super().__init__()

    def __init__(self, text, action, payload=None):
        super().__init__(text, markup=False)
        self._action = action
        self._payload = payload or {}

    def on_mount(self):
        self.focus()

    def action_confirm(self):
        logging.getLogger("kontiki_tui").info(
            "ConfirmPrompt: confirm action=%s", self._action
        )
        self._post_result(True)
        self.remove()

    def action_cancel(self):
        logging.getLogger("kontiki_tui").info(
            "ConfirmPrompt: cancel action=%s", self._action
        )
        self._post_result(False)
        self.remove()

    def _post_result(self, confirmed):
        try:
            tab = self.app.query_one("#services")
            tab.post_message(self.Result(confirmed, self._action, self._payload))
        except Exception as exc:
            logging.getLogger("kontiki_tui").error(
                "ConfirmPrompt: unable to post result: %s", exc, exc_info=True
            )


class Prompt(Static):
    can_focus = True

    BINDINGS = [
        Binding("escape", "dismiss", show=False),
    ]

    def __init__(self, message: str, timeout: float = 5.0, prefix: str = ""):
        display_message = f"{prefix}{message}" if prefix else message
        super().__init__(display_message, markup=False)
        self.timeout = timeout

    def on_mount(self) -> None:
        # Set a timer to remove the prompt after 5 seconds
        self.set_timer(self.timeout, self.remove)
        self.focus()  # Give the focus to capture Escape

    def action_dismiss(self) -> None:
        self.remove()


class ErrorPrompt(Prompt):
    def __init__(self, message: str, timeout: float = 5.0):
        super().__init__(message, timeout, prefix="Error: ")


class WarningPrompt(Prompt):
    def __init__(self, message: str, timeout: float = 5.0):
        super().__init__(message, timeout, prefix="Warning: ")


class InfoPrompt(Prompt):
    def __init__(self, message: str, timeout: float = 5.0):
        super().__init__(message, timeout, prefix="")
