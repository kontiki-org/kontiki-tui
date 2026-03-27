import logging
import os
import re
import shutil
import subprocess
from typing import Optional

_LNAV_MISSING_WARNED = False


def is_lnav_available() -> bool:
    return shutil.which("lnav") is not None


def _warn_lnav_missing_once() -> None:
    global _LNAV_MISSING_WARNED
    if _LNAV_MISSING_WARNED:
        return
    logging.warning(
        "lnav is not installed; falling back to python log reader with reduced "
        "filtering capabilities."
    )
    _LNAV_MISSING_WARNED = True


def _tail_lines(path: str, max_lines: Optional[int]) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fid:
            lines = fid.readlines()
    except Exception as e:
        logging.warning("Cannot read log file %s: %s", path, e, exc_info=True)
        return ""

    if isinstance(max_lines, int) and max_lines > 0:
        lines = lines[-max_lines:]
    return "".join(lines)


def _python_get_log(
    pattern: str,
    log_folder: str,
    filter_out: list[str],
    max_lines: Optional[int] = None,
) -> str:
    if not log_folder:
        return ""

    if os.path.isfile(log_folder):
        candidate_files = [log_folder]
    elif os.path.isdir(log_folder):
        candidate_files = sorted(
            [
                os.path.join(log_folder, name)
                for name in os.listdir(log_folder)
                if os.path.isfile(os.path.join(log_folder, name))
            ]
        )
    else:
        logging.warning("Log path does not exist: %s", log_folder)
        return ""

    pattern_re = (
        re.compile(re.escape(pattern), flags=re.IGNORECASE) if pattern else None
    )
    filter_out_res = [re.compile(item, flags=re.IGNORECASE) for item in filter_out]
    collected = []

    for file_path in candidate_files:
        raw = _tail_lines(file_path, max_lines=max_lines)
        if not raw:
            continue
        for line in raw.splitlines():
            if pattern_re and not pattern_re.search(line):
                continue
            if any(regex.search(line) for regex in filter_out_res):
                continue
            collected.append(line)

    if isinstance(max_lines, int) and max_lines > 0:
        collected = collected[-max_lines:]
    return "\n".join(collected)


def _lnav_log_line_count(log_path: str) -> Optional[int]:
    """Return total number of rows visible in lnav's all_logs view."""
    count_cmd = [
        "lnav",
        "-n",
        log_path,
        "-c",
        ";select count(*) as n from all_logs",
    ]
    try:
        count_proc = subprocess.run(
            count_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5
        )
        if count_proc.returncode != 0:
            return None
        count_text = count_proc.stdout.decode()
        match = re.search(r"\b(\d+)\b", count_text)
        if match:
            return int(match.group(1))
        return None
    except Exception as e:
        logging.debug("Unable to query log line count via lnav: %s", e, exc_info=True)
        return None


def get_log(pattern, log_folder, filter_out=[], max_lines: Optional[int] = None):
    if not is_lnav_available():
        _warn_lnav_missing_once()
        return _python_get_log(pattern, log_folder, filter_out, max_lines=max_lines)

    if pattern:
        pattern = re.escape(pattern)
        cmd = ["lnav", "-n", "-c", rf":filter-in {pattern}"]
    else:
        cmd = ["lnav", "-n"]
    for f in filter_out:
        cmd.extend(["-c", rf":filter-out {f}"])
    cmd.append(log_folder)

    # If max_lines is set, ask lnav for the row count and only apply
    # slicing commands when the view actually contains more than max_lines.
    should_slice = False
    if isinstance(max_lines, int) and max_lines > 0:
        line_count = _lnav_log_line_count(log_folder)
        should_slice = line_count is not None and line_count > max_lines

    # If there are more than max_lines, restrict the view in lnav:
    #   - goto 100%              -> go to the end of the view
    #   - relative-goto -N       -> move up by N lines
    #   - hide-lines-before here -> hide everything above the current position
    #   - write-raw-to -         -> write the current view to stdout
    if should_slice:
        cmd.extend(
            [
                "-c",
                ":goto 100%",
                "-c",
                f":relative-goto -{max_lines}",
                "-c",
                ":hide-lines-before here",
                "-c",
                ":write-raw-to -",
            ]
        )

    logging.info(f"lnav cmd = {cmd}")

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_output = proc.stdout.decode()

    if proc.returncode == 0:
        return raw_output
    else:
        logging.warning(f"lnav returned non-zero exit code: {proc.returncode}")
        return ""
