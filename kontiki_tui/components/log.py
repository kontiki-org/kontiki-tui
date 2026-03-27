import re

from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Input, Label, RichLog, Static, Switch

# -----------------------------------------------------------------------------


def render_log_output(raw_output, pattern, widget):
    """Render raw log output into the given widget, with optional highlighting."""
    widget.clear()

    if raw_output:
        text = Text(raw_output)
        if pattern:
            # Highlight matches in the output
            escaped_pattern = re.escape(pattern)
            for match in re.finditer(escaped_pattern, raw_output, flags=re.IGNORECASE):
                start_idx, end_idx = match.span()
                text.stylize("bold red", start_idx, end_idx)
        widget.write(text)
    else:
        widget.write(Text("No log output", style="bold red"))


# -----------------------------------------------------------------------------


class LogTab(Static):
    BINDINGS = [
        Binding("r", "refresh_logs", description="Refresh logs"),
    ]

    class UpdateLog(Message):
        def __init__(self, pattern, exclude_noise):
            super().__init__()
            self.pattern = pattern
            self.exclude_noise = exclude_noise

    def __init__(self, id_="log"):
        super().__init__(id=id_)
        self.border_title = "Logs"

    def compose(self):
        rich = RichLog(id="logs", highlight=True, auto_scroll=True, markup=True)
        yield Vertical(
            Horizontal(
                Input(placeholder="Pattern to search", id="pattern_input"),
                Label("exclude noise:", id="noise_label"),
                Switch(value=False, id="noise_switch"),
                id="pattern_horizontal",
            ),
            rich,
            id="log_vertical",
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        exclude_noise = self.query_one("#noise_switch", Switch).value
        self.post_message(self.UpdateLog(event.value.strip(), exclude_noise))

    def on_switch_changed(self, event):
        value = self.query_one("#pattern_input", Input).value
        self.post_message(self.UpdateLog(value.strip(), event.value))

    def action_refresh_logs(self) -> None:
        pattern_input = self.query_one("#pattern_input", Input).value
        exclude_noise = self.query_one("#noise_switch", Switch).value
        self.post_message(self.UpdateLog(pattern_input.strip(), exclude_noise))
