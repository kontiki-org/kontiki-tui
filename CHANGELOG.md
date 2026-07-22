# Changelog

## [0.2.0] - 2026-07-22

- Services tab defaults to the **business** registration group; switch Group to **All** to include platform services.
- Persist `services.group_filter` in `~/.config/kontiki_tui.yaml`.
- Missing / blank Registry `group` is treated as `business`.
- Require Kontiki `>=1.4.0` (registration `group` on the wire).
- Example `rpc_service` registers with `group: platform` for local filter checks.

## [0.1.1] - 2026-07-17

- Fixes empty Logs tab when `lnav` truncates to `max_lines`: mark visible rows before `:write-raw-to` (lnav requires marks).
- Falls back to the Python log reader when `lnav` reports an error on stderr even with exit code 0.

## [0.1.0] - 2026-03-27

Initial public release.
See `README.md` for an overview of the TUI (services, events, exceptions, logs, settings).
