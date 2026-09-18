import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from kontiki.messaging.flow import short_instance_id

from kontiki_tui.backend.services import (
    display_alert_dict,
    event_type_label,
    format_flow_index_time,
    format_hop_time,
    format_last_heartbeat,
    incident_host_display,
)
from kontiki_tui.config import BASE_CONF

LAST_EXPORT_NAME = "kontiki-tui-last.md"


def export_directory(conf):
    export = (conf or {}).get("export") or {}
    directory = export.get("directory")
    if directory is None or not str(directory).strip():
        directory = BASE_CONF.get("export", {}).get("directory")
    if directory is None or not str(directory).strip():
        raise ValueError("export.directory is not configured")
    return str(directory).strip()


def sanitize_filename_part(value):
    text = str(value or "").strip() or "no-id"
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)


def format_export_stamp(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S")


def exception_stem(exc, now=None):
    flow_id = str(exc.get("flow_id") or "").strip() or "no-flow"
    return "exception-%s-%s" % (
        sanitize_filename_part(flow_id),
        format_export_stamp(now),
    )


def flow_stem(flow, now=None):
    flow_id = str(flow.get("flow_id") or "").strip() or "no-flow"
    return "flow-%s-%s" % (sanitize_filename_part(flow_id), format_export_stamp(now))


def incident_stem(alert, now=None):
    alert_id = str(alert.get("alert_id") or "").strip() or "no-id"
    return "incident-%s-%s" % (
        sanitize_filename_part(alert_id),
        format_export_stamp(now),
    )


def _export_time(value):
    text = format_last_heartbeat(value)
    if not text:
        return ""
    return text + " UTC"


def _field(label, value):
    if value is None:
        text = ""
    else:
        text = str(value).strip()
    if not text:
        text = "—"
    return "- %s: %s" % (label, text)


def render_exception(exc):
    service = str(exc.get("service_name") or "").strip()
    instance = short_instance_id(str(exc.get("instance_id") or ""))
    title = "Exception"
    bits = [part for part in (service, instance) if part]
    if bits:
        title = "Exception — " + " ".join(bits)
    lines = [
        "# %s" % title,
        "",
        _field("Time", _export_time(exc.get("timestamp"))),
        _field("Service", service),
        _field("Instance", instance),
        _field("Flow", exc.get("flow_id")),
        _field("Entrypoint", exc.get("entrypoint")),
        _field("Operation", exc.get("operation")),
        _field("Type", exc.get("exception_type")),
        _field("Message", exc.get("message")),
        "",
    ]
    return "\n".join(lines)


def render_flow(flow):
    flow_id = str(flow.get("flow_id") or "").strip()
    hops = flow.get("hops") or []
    lines = [
        "# Flow %s" % (flow_id or "—"),
        "",
        _field("Started", format_flow_index_time(flow.get("started"))),
        _field("Last", format_flow_index_time(flow.get("last"))),
        _field("Origin", flow.get("origin")),
        _field("First", flow.get("first_type")),
        _field("Hops", len(hops)),
        "",
        "## Hops",
        "",
    ]
    if not hops:
        lines.append("—")
    else:
        for hop in hops:
            parts = [
                format_hop_time(hop.get("timestamp")) or "—",
                str(hop.get("_group") or "").strip() or "—",
                str(hop.get("service_name") or "").strip() or "—",
                short_instance_id(str(hop.get("instance_id") or "")) or "—",
                event_type_label(hop) or "—",
                str(hop.get("host") or "").strip() or "—",
            ]
            lines.append("- " + " · ".join(parts))
    lines.append("")
    return "\n".join(lines)


def render_incident(alert):
    payload = display_alert_dict(alert)
    attributes = payload.get("attributes") or {}
    title = str(payload.get("title") or "").strip() or "Incident"
    body = str(payload.get("body") or "").strip() or "—"
    lines = [
        "# %s" % title,
        "",
        _field("Severity", payload.get("severity")),
        _field("Source", payload.get("source")),
        _field("Type", payload.get("event_type")),
        _field("Service", attributes.get("service_name")),
        _field("Host", incident_host_display(alert)),
        _field("Occurred", format_last_heartbeat(payload.get("occurred_at"))),
        _field("Alert ID", payload.get("alert_id")),
        "",
        "## Body",
        "",
        body,
        "",
    ]
    return "\n".join(lines)


def write_markdown_export(directory, stem, markdown):
    target_dir = Path(directory).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    unique = target_dir / ("%s.md" % stem)
    last = target_dir / LAST_EXPORT_NAME
    unique.write_text(markdown, encoding="utf-8")
    last.write_text(markdown, encoding="utf-8")
    logging.getLogger("kontiki_tui").info("Wrote export %s", unique)
    return str(unique)


def planned_export_path(conf, stem):
    directory = Path(export_directory(conf)).expanduser()
    return str(directory / ("%s.md" % stem))


def export_markdown(conf, stem, markdown):
    return write_markdown_export(export_directory(conf), stem, markdown)
