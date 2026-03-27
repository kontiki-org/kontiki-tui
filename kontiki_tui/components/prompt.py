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
        def __init__(self, confirmed: bool, row_key: int):
            self.confirmed = confirmed
            self.row_key = row_key
            super().__init__()

    def __init__(self, text: str, row_key: int):
        super().__init__(text, markup=False)
        self._row_key = row_key

    def on_mount(self) -> None:
        self.focus()

    def action_confirm(self) -> None:
        logging.getLogger("kontiki_tui").info(
            f"ConfirmPrompt: confirm pressed for row_key={self._row_key}"
        )
        # Envoyer le message directement au ViewTab (#view)
        try:
            view = self.app.query_one("#view")
            view.post_message(self.Result(confirmed=True, row_key=self._row_key))
        except Exception as e:
            logging.getLogger("kontiki_tui").error(
                f"ConfirmPrompt: unable to post confirm result to #view: {e}",
                exc_info=True,
            )
        self.remove()

    def action_cancel(self) -> None:
        logging.getLogger("kontiki_tui").info(
            f"ConfirmPrompt: cancel pressed for row_key={self._row_key}"
        )
        try:
            view = self.app.query_one("#view")
            view.post_message(self.Result(confirmed=False, row_key=self._row_key))
        except Exception as e:
            logging.getLogger("kontiki_tui").error(
                f"ConfirmPrompt: unable to post cancel result to #view: {e}",
                exc_info=True,
            )
        self.remove()


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


class InfoPrompt(Prompt):
    def __init__(self, message: str, timeout: float = 5.0):
        super().__init__(message, timeout, prefix="")
