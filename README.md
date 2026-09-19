# KontikiTUI

> **Part of the Kontiki suite** — a compact open-source stack for startups and
> small teams that need ops without the heavy stack.
>
> Full suite overview → https://kontiki-org.github.io/
>
> Ops demo → [kontiki-monitor Quickstart](https://github.com/kontiki-org/kontiki-monitor#quickstart--demo-app--telegram).


## Overview

**KontikiTUI** is a terminal UI for a [Kontiki](https://github.com/kontiki-org/kontiki)
fleet: one SSH entry point for registry census, open ops alerts, flows,
events, exceptions, logs, and silences.

It is built with [Textual](https://textual.textualize.io/). A session **Group**
Select slices every monitoring tab the same way (`all` plus groups discovered
in the registry).

- **Services** — registered instances (status, heartbeat, host/pid, versions,
  mute).
- **Incidents** — open alerts from `kontiki-monitor` and `host-check-service`.
- **Flows** / **Events** / **Exceptions** — registry trackers (chains by
  `flow_id`, flat journal, exceptions).
- **Logs** — log files of instances currently in the registry.
- **Silences** — persisted monitor mutes, including names no longer registered.

The Header subtitle is the installed KontikiTUI version.

---

## Tabs

- **Services**: registered services with status, last heartbeat, degraded reason,
  host/pid, service version, and Kontiki runtime version (`kontiki_version` on
  `get_services`; empty when the instance does not report it; Kontiki ≥1.10.0).
  Selecting a row shows the **public** configuration in JSON (top-level
  `public` mapping on the instance, Kontiki ≥1.14.0). Empty when the service
  publishes none. Local filters
  (`Field`/`Value`): Service, Instance, Status, Host, Version, Kontiki.

  Mute column (`🔇`) reflects kontiki-monitor silences (`service_name`). `s`
  toggles the selected service; `S` mutes or unmutes all live names in the
  current Group (always confirmed). Activating the tab warns if silenced
  names are no longer in the registry (`WarningPrompt`).

  Defaults to **all** via the session **Group** Select on each monitoring tab.
  Options are `all` plus groups discovered in the live registry. Changing it in
  one tab updates all tabs. Missing/blank Registry `group` counts as business.
  Instance is the Kontiki 12-hex id (same on Events, Exceptions, Flows hops).

  ![Services tab](assets/services.png)

- **Incidents**: open ops alerts (`list_open_alerts`) from `kontiki-monitor`
  (fleet / exception fingerprints) and every live `host-check-service` instance
  (disk). Session Group Select and local `Field`/`Value` filters. Selecting a
  row shows the full alert JSON. `e` confirms the file path then writes a
  Markdown export of the selected alert to `export.directory`. Mute does not
  cover host-check disk alerts.
  Requires Kontiki ≥1.14.0 and `boomerang-contracts` (pickled `NormalizedAlert`).

  ![Incidents tab](assets/incidents.png)

- **Flows**: chains from the same event tracker, grouped by `flow_id`.
  Top table is one row per flow (Flow Id, window, Messages count, origin
  service, first type); bottom table is that flow's message tree
  (Type `↪️  [+12ms]` / `💥` by depth, `hop_id` / `parent_hop_id`, including hops
  outside the session Group). Exceptions nest under the consumed hop as
  red `💥 exc:…` rows (no Time). A flow is listed when at
  least one hop's emitter is in the selected Group.
  Events without `flow_id` stay on Events only. Same census-RPC hide as
  Events. `e` confirms the file path then writes a Markdown export of the
  selected flow (Messages table; Type repeats `↪️` by depth; Logs section
  with `[flow={id}]` records including traceback) to `export.directory`.
  Requires Kontiki ≥1.16.0.

- **Events**: events tracked by the registry, with local filters (`Field`/`Value`/`Limit`:
  Service, Instance, Event Type). Instance is the 12-hex id.
  Domain publishes and RPC calls are shown (`rpc:<remote_method>` when there is no
  `event_type`). Hides registry bookkeeping, TUI observer traffic, and census
  RPCs (`get_services`, `list_instances`, tracker and silence/open-alert reads).
  Filtered by the same session Group Select (registry jointure).
  Deregistered instances fall back to `business`.

  ![Events tab](assets/events.png)

- **Exceptions**: registry exception index (`flow_id`, entrypoint, operation,
  type, message). Instance is the 12-hex id. Same local filters and session
  Group Select. Empty cells when `flow_id` / entrypoint / operation are null.
  Traceback stays in Logs (`[flow=…]`). Requires Kontiki ≥1.15.0.
  `e` confirms the file path then writes a Markdown export of the selected
  exception to `export.directory`.

  ![Exceptions tab](assets/exceptions.png)

- **Logs**: reads log files of instances currently in the registry, from
  `logs.directory`. Uses `lnav` when available; otherwise a Python reader.
  Files follow Kontiki ≥1.8.1 naming `{service_name}-{short_instance_id}.log`
  plus numeric RotatingFileHandler backups (`.log.N`), filtered by the
  session Group Select. Leftover files from deregistered instances,
  deregistered instances, `ServiceRegistry-*.log`, dated TimedRotating
  suffixes, and non-Kontiki filenames are not opened.

  ![Logs tab](assets/logs.png)

- **Silences**: monitor silences (`list_silences`), including names missing from
  the registry. `s` clears the selected silence. Session Group Select: absent
  names show as `business`. Mute is still posed from Services.

  ![Silences tab](assets/silences.png)

- **Settings**: edit `~/.config/kontiki_tui.yaml` (the app reloads configuration on save).
  `export.directory` (default `/tmp/kontiki-tui-exports`) is the folder for Markdown
  exports (`e` then `y` on Incidents, Flows, Exceptions). Each export also
  overwrites `kontiki-tui-last.md` in that folder.

  ![Settings tab](assets/settings.png)

---

## Requirements

- **Optional**: [lnav](https://lnav.org/) for richer log filtering; without it, a built-in Python reader is used

## Quickstart

### Install from PyPI

```bash
pip install kontiki-tui
kontiki-tui
```

([package on PyPI](https://pypi.org/project/kontiki-tui/))

### Install from source (Poetry)

```bash
make install
make run
```

### Test stack (RabbitMQ + registry + example services + kontiki-monitor)

In one terminal:

```bash
make stack-up
```

In another terminal:

```bash
make run
```

Launch examples to view events and exceptions
```
make run-rpc-example
make run-simple-event-example
```

To stop:

```bash
make stack-down
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
