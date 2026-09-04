"""Shared group-filter Select for Services / Events / Exceptions / Logs."""

from textual.message import Message
from textual.widgets import Label, Select

from kontiki_tui.backend.services import group_filter_select_options

GROUP_FILTER_SELECT_CLASS = "group-filter-select"


class GroupFilterChanged(Message):
    """Posted when the user picks a group in any tab Select."""

    def __init__(self, group_filter):
        super().__init__()
        self.group_filter = group_filter


def current_group_filter(app):
    value = getattr(app, "group_filter", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "business"


def is_group_filter_sync(app):
    """True while Selects are updated programmatically (ignore Changed)."""
    return getattr(app, "_syncing_group_filter", 0) > 0


def _begin_group_filter_sync(app):
    app._syncing_group_filter = getattr(app, "_syncing_group_filter", 0) + 1


def _end_group_filter_sync(app):
    depth = getattr(app, "_syncing_group_filter", 0)
    app._syncing_group_filter = max(0, depth - 1)


def _select_option_values(select):
    return tuple(value for _, value in select._options)


def make_group_filter_select(app, select_id):
    """Build a Group Select bound to the app session filter."""
    value = current_group_filter(app)
    options = group_filter_select_options([])
    # Ensure the current value is present even if not in the default set.
    if value != "all" and value not in {opt[1] for opt in options}:
        options.append((value, value))
    select = Select(
        options=options,
        value=value,
        id=select_id,
        classes=GROUP_FILTER_SELECT_CLASS,
        allow_blank=False,
    )
    return Label("Group:"), select


async def refresh_group_filter_options(app, select):
    """Refresh Select options from the registry; keep the session value."""
    discovered = []
    services = getattr(app, "services", None)
    if services is not None:
        discovered = await services.list_registration_groups()
    options = group_filter_select_options(discovered)
    value = current_group_filter(app)
    if value != "all" and value not in {opt[1] for opt in options}:
        options.append((value, value))

    new_values = tuple(opt[1] for opt in options)
    same_options = _select_option_values(select) == new_values

    # set_options always resets to the first option ("all") and posts Changed.
    # Suppress that so a concurrent refresh cannot overwrite the session filter.
    _begin_group_filter_sync(app)
    try:
        with select.prevent(Select.Changed):
            if not same_options:
                select.set_options(options)
            if select.value != value:
                select.value = value
    finally:
        _end_group_filter_sync(app)


def sync_group_filter_selects(app, group_filter):
    """Align every group-filter Select with the session value."""
    _begin_group_filter_sync(app)
    try:
        for select in app.query(f".{GROUP_FILTER_SELECT_CLASS}"):
            if select.value == group_filter:
                continue
            with select.prevent(Select.Changed):
                select.value = group_filter
    finally:
        _end_group_filter_sync(app)
