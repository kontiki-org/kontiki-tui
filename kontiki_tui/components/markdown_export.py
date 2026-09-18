import logging

from kontiki_tui.backend.export import export_markdown, planned_export_path
from kontiki_tui.components.prompt import show_confirm

EXPORT_ACTION = "export_markdown"


def request_markdown_export(tab, selected, missing_message, stem_fn, render_fn):
    if not selected:
        tab.app._show_error_prompt(missing_message)
        return
    stem = stem_fn(selected)
    try:
        path = planned_export_path(tab.app.conf, stem)
    except ValueError as exc:
        tab.app._show_error_prompt(str(exc))
        return
    markdown = render_fn(selected)
    show_confirm(
        tab.app,
        tab,
        "Export %s? [y/n]" % path,
        EXPORT_ACTION,
        {"stem": stem, "markdown": markdown},
    )


def finish_markdown_export(tab, event):
    if event.action != EXPORT_ACTION or not event.confirmed:
        return
    stem = event.payload.get("stem")
    markdown = event.payload.get("markdown")
    try:
        path = export_markdown(tab.app.conf, stem, markdown)
    except ValueError as exc:
        tab.app._show_error_prompt(str(exc))
        return
    except OSError as exc:
        logging.error("Cannot write export: %s", exc, exc_info=True)
        tab.app._show_error_prompt("Cannot write export: %s" % exc)
        return
    logging.info("Exported markdown to %s", path)
    tab.app._show_info_prompt(path)
