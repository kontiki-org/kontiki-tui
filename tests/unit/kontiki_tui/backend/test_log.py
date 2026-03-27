from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kontiki_tui.backend import log as log_backend


@pytest.fixture
def tmp_logs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d


def test_python_get_log_ok(tmp_logs_dir: Path):
    p = tmp_logs_dir / "a.log"
    p.write_text(
        "\n".join(
            [
                "INFO hello world",
                "ERROR bad stuff",
                "INFO hello again",
                "DEBUG noisy",
            ]
        ),
        encoding="utf-8",
    )

    out = log_backend._python_get_log(
        pattern="hello",
        log_folder=str(tmp_logs_dir),
        filter_out=[r"DEBUG", r"ERROR"],
        max_lines=None,
    )
    assert out.splitlines() == ["INFO hello world", "INFO hello again"]


def test_python_get_log_ok_with_max_lines(tmp_logs_dir: Path):
    p = tmp_logs_dir / "a.log"
    p.write_text("\n".join([f"line {i}" for i in range(10)]), encoding="utf-8")

    out = log_backend._python_get_log(
        pattern="",
        log_folder=str(tmp_logs_dir),
        filter_out=[],
        max_lines=3,
    )
    assert out.splitlines() == ["line 7", "line 8", "line 9"]


def test_get_log_ko(tmp_logs_dir: Path):
    p = tmp_logs_dir / "a.log"
    p.write_text("hello\n", encoding="utf-8")

    with patch.object(log_backend, "is_lnav_available", return_value=False):
        out = log_backend.get_log(
            pattern="hello",
            log_folder=str(tmp_logs_dir),
            filter_out=[],
        )
    assert out.strip() == "hello"


def test_get_log_uses_lnav_without_slicing_when_under_limit():
    with (
        patch.object(log_backend, "is_lnav_available", return_value=True),
        patch.object(log_backend, "_lnav_log_line_count", return_value=10),
        patch.object(log_backend.subprocess, "run") as run,
    ):
        run.return_value = Mock(returncode=0, stdout=b"OK\n", stderr=b"")
        out = log_backend.get_log(
            pattern="",
            log_folder="logs",
            filter_out=[],
            max_lines=50,
        )
        assert out == "OK\n"

        called_cmd = run.call_args[0][0]
        assert ":write-raw-to -" not in called_cmd


def test_get_log_uses_lnav_slicing_when_over_limit():
    with (
        patch.object(log_backend, "is_lnav_available", return_value=True),
        patch.object(log_backend, "_lnav_log_line_count", return_value=200),
        patch.object(log_backend.subprocess, "run") as run,
    ):
        run.return_value = Mock(returncode=0, stdout=b"OK\n", stderr=b"")
        out = log_backend.get_log(
            pattern="",
            log_folder="logs",
            filter_out=[],
            max_lines=50,
        )
        assert out == "OK\n"

        called_cmd = run.call_args[0][0]
        assert ":goto 100%" in called_cmd
        assert ":hide-lines-before here" in called_cmd
        assert ":write-raw-to -" in called_cmd
