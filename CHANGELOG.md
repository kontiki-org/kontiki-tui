# Changelog

## [1.0.0] - 2026-09-03

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
- Require Kontiki `>=1.8.1` (`logging.directory` / predictable log file naming).
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
