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
    return "all"


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


def _options_with_session_value(discovered, value):
    options = group_filter_select_options(discovered)
    if value and value != "all" and value not in {opt[1] for opt in options}:
        options.append((value, value))
    return options


def make_group_filter_select(app, select_id):
    """Build a Group Select bound to the app session filter."""
    value = current_group_filter(app)
    options = _options_with_session_value([], value)
    select = Select(
        options=options,
        value=value,
        id=select_id,
        classes=GROUP_FILTER_SELECT_CLASS,
        allow_blank=False,
    )
    return Label("Group:"), select


def _apply_options_to_select(select, options, value):
    new_values = tuple(opt[1] for opt in options)
    with select.prevent(Select.Changed):
        if _select_option_values(select) != new_values:
            select.set_options(options)
        if select.value != value:
            select.value = value


async def refresh_group_filter_options(app):
    """Load registry groups once and apply the same options to every Select."""
    discovered = []
    services = getattr(app, "services", None)
    if services is not None:
        discovered = await services.list_registration_groups()
    value = current_group_filter(app)
    options = _options_with_session_value(discovered, value)

    _begin_group_filter_sync(app)
    try:
        for select in app.query(f".{GROUP_FILTER_SELECT_CLASS}"):
            _apply_options_to_select(select, options, value)
    finally:
        _end_group_filter_sync(app)


def sync_group_filter_selects(app, group_filter):
    """Align every group-filter Select with the session value."""
    _begin_group_filter_sync(app)
    try:
        for select in app.query(f".{GROUP_FILTER_SELECT_CLASS}"):
            if group_filter not in _select_option_values(select):
                options = list(select._options)
                options.append((group_filter, group_filter))
                _apply_options_to_select(select, options, group_filter)
            elif select.value != group_filter:
                with select.prevent(Select.Changed):
                    select.value = group_filter
    finally:
        _end_group_filter_sync(app)
