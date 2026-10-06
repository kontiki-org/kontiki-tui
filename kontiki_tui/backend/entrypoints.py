"""Catalogue and failed-message rows for the Entrypoints tab.

Live instances are active or degraded, the same predicate as Registry
``list_instances``. A service is ``unknown`` when any of those instances
has no ``entrypoints`` field. A line is the displayed tuple; replicas
that disagree are separate rows.
"""

from kontiki_tui.backend.services import (
    matches_group_filter,
    normalize_registration_group,
)

CATALOGUE_OK = "ok"
CATALOGUE_UNKNOWN = "unknown"
LIVE_STATUSES = ("active", "degraded")


def line_key(entry):
    return (
        entry["type"],
        entry["name"],
        entry["handler"],
        entry["mode"],
        entry["attempts"],
    )


def entrypoint_view(entry):
    kind = entry.get("type") or ""
    handler = entry.get("handler") or ""
    if kind == "event":
        mode = entry.get("mode") or ""
        attempts = ""
        if mode == "competing" and entry.get("max_attempts") is not None:
            attempts = str(entry["max_attempts"])
        return {
            "type": "event",
            "name": entry.get("name") or "",
            "handler": handler,
            "mode": mode,
            "attempts": attempts,
            "competing": mode == "competing",
            "event_name": entry.get("name") or "",
        }
    if kind == "rpc":
        return _plain("rpc", entry.get("name") or "", handler)
    if kind == "http":
        name = "%s %s" % (entry.get("method") or "", entry.get("path") or "")
        return _plain("http", name, handler)
    if kind == "task":
        schedule = entry.get("schedule")
        mode = "" if schedule is None else str(schedule)
        view = _plain("task", handler, handler)
        view["mode"] = mode
        return view
    return _plain(kind, entry.get("name") or handler, handler)


def service_failed_display(row, counts):
    """Sum of retained messages for each competing event, once per name."""
    if row["catalogue"] != CATALOGUE_OK:
        return ""
    names = []
    for entry in row["entrypoints"]:
        if entry["competing"] and entry["event_name"] not in names:
            names.append(entry["event_name"])
    if not names:
        return "0"
    total = 0
    for name in names:
        count = counts.get((row["service_name"], name))
        if count is None:
            return ""
        total += count
    return str(total)


def entrypoint_failed_display(service_name, entry, counts):
    if not entry["competing"]:
        return ""
    count = counts.get((service_name, entry["event_name"]))
    if count is None:
        return ""
    return str(count)


def apply_entrypoint_service_filter(rows, field, value):
    if not field or field == "all" or not value:
        return list(rows)
    expected = value.lower()
    return [
        row
        for row in rows
        if expected in str(row.get("service_name", "") or "").lower()
    ]


def build_service_rows(raw_services, group_filter):
    """One row per service that has a live instance in the session group."""
    rows = []
    for service_name in sorted((raw_services or {}).keys()):
        instances = raw_services.get(service_name)
        if not isinstance(instances, dict):
            continue
        live = _live_in_group(instances, group_filter)
        if not live:
            continue
        unknown = any("entrypoints" not in metadata for _, metadata in live)
        rows.append(
            {
                "service_name": service_name,
                "instances": len(live),
                "catalogue": CATALOGUE_UNKNOWN if unknown else CATALOGUE_OK,
                "entrypoints": [] if unknown else _merge_entrypoints(live),
            }
        )
    return rows


def _plain(kind, name, handler):
    return {
        "type": kind,
        "name": name,
        "handler": handler,
        "mode": "",
        "attempts": "",
        "competing": False,
        "event_name": None,
    }


def _live_in_group(instances, group_filter):
    live = []
    for instance_id, entry in instances.items():
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "").lower()
        if status not in LIVE_STATUSES:
            continue
        metadata = entry.get("metadata") or {}
        group = normalize_registration_group(metadata.get("group"))
        if not matches_group_filter(group, group_filter):
            continue
        live.append((str(instance_id), metadata))
    live.sort(key=lambda item: item[0])
    return live


def _merge_entrypoints(live):
    total = len(live)
    order = []
    counts = {}
    views = {}
    for _, metadata in live:
        seen = set()
        for entry in metadata["entrypoints"]:
            view = entrypoint_view(entry)
            key = line_key(view)
            if key in seen:
                continue
            seen.add(key)
            if key not in counts:
                order.append(key)
                counts[key] = 0
                views[key] = view
            counts[key] += 1
    merged = []
    for key in order:
        view = dict(views[key])
        view["declared"] = "%s/%s" % (counts[key], total)
        merged.append(view)
    return merged
