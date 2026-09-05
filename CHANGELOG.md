# Changelog

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
