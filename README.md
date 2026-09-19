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

Every monitoring tab uses the same session **Group** Select (`all` plus
groups from the live registry). Changing it in one tab updates all tabs.
Instance ids are the Kontiki 12-hex short id. `r` refreshes the active tab.

- **Services**: live instances (status, heartbeat, host/pid, versions).
  Row → public config JSON. `s` / `S` mute via kontiki-monitor (confirmed).

  ![Services tab](assets/services.png)

- **Incidents**: open alerts from `kontiki-monitor` and `host-check-service`.
  Row → alert JSON. `e` exports Markdown.

  ![Incidents tab](assets/incidents.png)

- **Flows**: AMQP chains by `flow_id` (list + message tree). Exceptions nest
  under the hop that failed. `e` exports the tree and matching log lines
  (`[flow=…]`, including traceback). Requires Kontiki ≥1.16.0.

  ![Flows tab](assets/flows.png)

- **Events**: flat journal of publishes and RPC calls.

  ![Events tab](assets/events.png)

- **Exceptions**: registry exception index. Tracebacks stay in Logs.
  `e` exports Markdown.

  ![Exceptions tab](assets/exceptions.png)

- **Logs**: current instance log files under `logs.directory` (`lnav` if
  installed). Group Select applies.

  ![Logs tab](assets/logs.png)

- **Silences**: monitor mutes, including names no longer registered.
  `s` clears the selected row. Mute is set from Services.

  ![Silences tab](assets/silences.png)

- **Settings**: `~/.config/kontiki_tui.yaml` (reload on save).
  Markdown exports go to `export.directory` (`e` then `y`).

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
