# Changelog

## [Unreleased]

- Entrypoints tab: catalogue declared by live instances, retained competing
  messages, and replay of the oldest one (`p`).
- Require Kontiki `>=2.1.0` (`entrypoints` on registration,
  `list_failed_messages`, `replay_failed_messages`). The demo image installs
  that release from PyPI.

## [2.0.0] 2026-09-29

- Require Kontiki `>=2.0.0` (`hop_id` / `parent_hop_id` / `rpc_service` on
  bus emissions; `hop_id` / `exception_id` on exception records;
  `add_context` / `activity_tracker` for Flow annotations).
- Require `boomerang-contracts` `>=2.0.0`. Incidents reads `list_open_alerts`
  as JSON (`NormalizedAlert` dict or `model_dump`); the alert fields are
  unchanged.
- Flow Markdown export: the Logs section merges the flow instances records
  in chronological order (tracebacks stay attached to their record).
- Flows: `registry.context.recorded` entries (Kontiki registry 2.0)
  render as annotations, not hops. A hop's contexts aggregate into one
  `💡 N context values [context_id]` row (cyan) at its chronological
  place among the hop's rows; exception and annotation rows show their
  record time. Hovering shows the `context` payloads in a tooltip.
  Markdown export: the row appears in the Timeline table plus a
  `## Contexts` section with one `### [<context_id>] - <service>: <operation>` block per record
  (keys in the first column, values in the second).
- Examples and demo stack conform to Kontiki 2.0: `max_attempts=2`
  replaces the removed `requeue_on_error` / `reject_on_redelivered`
  (`bounded_retry_event`), `rpc_example` records contexts, registry
  config uses `activity_tracker.*`, RabbitMQ 4.3. The demo image overlays
  Kontiki from the `2.0.0_alpha` GitHub branch (`--no-deps` after Poetry).
- Events tab omits `registry.context.recorded` (Flow annotations).

## [1.6.0] - 2026-09-19

- Require Kontiki `>=1.16.0` (`hop_id` / `parent_hop_id` / `rpc_service` on
  bus emissions; `hop_id` / `exception_id` on exception records).
- Flows tree: Type prefix `↪️  [+12ms]` (child hop) / `💥` (exception),
  indent by depth. No Δ column. Roots unmarked. Exception rows in red,
  after the hop's message children.
- Flows hops: column widths follow cell content (Type included), so
  long labels stay fully visible when switching flows.
- Flow Markdown export: Timeline is a table (Time, Group, Service,
  Instance, Type, Host). Type repeats `↪️` by depth (`↪️↪️ …`) so
  nesting survives GFM. Empty hops stay `—`. Logs section is the last
  `[flow={id}]` lines from those instances' files (`logs.directory`,
  including `.log.N`), plus traceback lines until the next log record.
- Logs tab (and flow export) reads numeric RotatingFileHandler backups
  (`{service}-{12hex}.log.N`), oldest first then the current file.
- Example `simple_example` gives each publish its own `flow_id`.
  `SimpleEventService` calls `RpcService.rpc_example` on `simple_event` ;
  `standard_case` publishes `chain.b`, then `chain.c` (depth 3).
  `make run-simple-event-example`.

## [1.5.0] - 2026-09-18

- Require Kontiki `>=1.15.0` (exception record: `flow_id`, `entrypoint`,
  `operation`).
- Exceptions tab: Flow, Entrypoint, Operation columns. No Context column.
  Local filters include Flow ID, Entrypoint, Operation.
- Flows tab: AMQP chains grouped by `flow_id` (hops in chronological
  order). Session Group lists flows that touch the group and still shows
  the full chain. Events stays the flat journal. Census RPCs
  (`get_services`, `list_instances`, tracker/silence/open-alert reads)
  are hidden on Events and Flows.
- Events, Exceptions, and Flows hops show the same 12-hex Instance as
  Services. Field labels: Service, Instance.
- Tab order: Services, Incidents, Flows, Events, Exceptions, Logs,
  Silences, Settings.
- `e` on Incidents, Flows, and Exceptions confirms the target path
  (`Export …? [y/n]`), then writes a Markdown file of the selected row to
  `export.directory` (default `/tmp/kontiki-tui-exports`) and overwrites
  `kontiki-tui-last.md` in the same folder.

## [1.4.0] - 2026-09-16

- Require Kontiki `>=1.14.0` (registration `public` mapping).
- Example Docker stack runs `kontiki-monitor` (fleet expectations on
  `RpcService` and `SimpleEventService`).
- Services Configuration pane: tooltip for the top-level `public` mapping.
  Example `SimpleEventService` publishes `event` there.

## [1.3.0] - 2026-09-15

- Silences tab: inventory of monitor `list_silences` (present / absent in the
  registry). `s` clears the selected silence.
- Incidents Host column shows `N/A` for `kontiki-monitor` opens (disk alerts
  still use `attributes.host`).

## [1.2.1] - 2026-09-14

- Depend on `boomerang-contracts` so pickled `NormalizedAlert` payloads from
  `list_open_alerts` can be decoded (Incidents tab).

## [1.2.0] - 2026-09-14

- Incidents tab: open `NormalizedAlert` snapshots from `kontiki-monitor` and
  `host-check-service` (`list_instances` then `list_open_alerts` per instance).
- Services tab: Mute column and bindings `s` / `S` (monitor silences).
- Require Kontiki `>=1.13.0`.

## [1.1.3] - 2026-09-12

- Logs tab opens only log files of instances currently in the registry (same
  Group Select as the other tabs). Leftover files from deregistered instances
  and non-Kontiki filenames are omitted.
- Rollback of 1.1.2: Logs pattern search is live again (each keystroke), not
  Enter.

## [1.1.2] - 2026-09-12

- Logs tab: pattern search runs on Enter, not on each keystroke.

## [1.1.1] - 2026-09-05

- Fix crash (`InvalidSelectValueError`) when picking a Group that other tabs
  had not loaded yet.
- Group Select options are `all` plus groups discovered in the registry (no
  hardcoded `business` / `platform`). The same list is loaded once at startup
  on every tab. Default at startup is `all`.

## [1.1.0] - 2026-09-05

- Services tab: local `Field` / `Value` filters (service name, instance id,
  status, host, service version, Kontiki version). Instance id matches the short
  id and the full UUID. Status matches the registry value (`active` /
  `degraded` / `down`), not the emoji. No `Limit` (fleet snapshot).
- Services tab shows instance `kontiki_version` (column **Kontiki**; empty when
  absent). Header subtitle is the KontikiTUI package version.
- Require Kontiki `>=1.10.0` (`kontiki_version` on `get_services`).

## [1.0.0] - 2026-09-04

- Session **Group** Select on Services / Events / Exceptions / Logs: change in one
  tab updates all tabs. Default at startup is `business`. Options: `all` + groups
  from the registry (`business` / `platform` always listed).
- Group filtering for Events / Exceptions (registry jointure) and Logs (Kontiki
  ≥1.8.1 `{service_name}-{12hex}.log` naming). Unknown / deregistered instances
  fall back to `business`. Events hide `ServiceRegistry` bookkeeping and
  `kontiki_tui` observer traffic (domain publishes and RPC calls stay visible);
  Logs never open `ServiceRegistry-*.log`.
- Removed config key `services.group_filter` (UI-only session filter).
- Services tab shows Kontiki **short instance id** (12 hex) instead of the full UUID.
- Services tab shows registry **Last Heartbeat** (full ISO timestamp) and
  **Degraded Reason** from Kontiki `get_services` (`last_heartbeat`,
  `degraded_reason`; reason shows `-` when absent).
- Removed local CPU / memory / open-FD columns (`psutil`).
- Require Kontiki `>=1.9.0` (instance health on `get_services`; log file naming
  from ≥1.8.1).
- Updated example stack (`common.docker.yaml`) to use `logging.directory: logs`;
  removed manual `filename` from service configs.

## [0.2.0] - 2026-07-22

- Services tab defaults to the **business** registration group via `services.group_filter`
  in `~/.config/kontiki_tui.yaml` (`business` | `all`; edit in Settings).
- Missing / blank Registry `group` is treated as `business`.
- Require Kontiki `>=1.4.0` (registration `group` on the wire).
- Example `rpc_service` registers with `group: platform` for local filter checks.

## [0.1.1] - 2026-07-17

- Fixes empty Logs tab when `lnav` truncates to `max_lines`: mark visible rows before `:write-raw-to` (lnav requires marks).
- Falls back to the Python log reader when `lnav` reports an error on stderr even with exit code 0.

## [0.1.0] - 2026-03-27

Initial public release.
See `README.md` for an overview of the TUI (services, events, exceptions, logs, settings).
