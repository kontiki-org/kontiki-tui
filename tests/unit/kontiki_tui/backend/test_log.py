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
        assert ";UPDATE all_logs SET log_mark = 1" in called_cmd
        assert ":write-raw-to -" in called_cmd


def test_get_log_falls_back_to_python_when_lnav_stderr_has_error(tmp_logs_dir):
    p = tmp_logs_dir / "a.log"
    p.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    with (
        patch.object(log_backend, "is_lnav_available", return_value=True),
        patch.object(log_backend, "_lnav_log_line_count", return_value=10),
        patch.object(log_backend.subprocess, "run") as run,
    ):
        run.return_value = Mock(
            returncode=0,
            stdout=b"",
            stderr=b"error: no lines marked to write, use 'm' to mark lines\n",
        )
        out = log_backend.get_log(
            pattern="",
            log_folder=str(tmp_logs_dir),
            filter_out=[],
            max_lines=50,
        )
    assert out.splitlines() == ["line 1", "line 2", "line 3"]


# ---------------------------------------------------------------------------
# log_files parameter (group-filtered list)
# ---------------------------------------------------------------------------


def test_python_get_log_with_log_files(tmp_logs_dir: Path):
    biz = tmp_logs_dir / "OrderSvc-aabbccddeeff.log"
    plat = tmp_logs_dir / "PlatformSvc-112233445566.log"
    biz.write_text("biz line\n", encoding="utf-8")
    plat.write_text("plat line\n", encoding="utf-8")

    # Only pass the business file.
    out = log_backend._python_get_log(
        pattern="",
        log_folder=str(tmp_logs_dir),
        filter_out=[],
        log_files=[str(biz)],
    )
    assert out.strip() == "biz line"
    assert "plat line" not in out


def test_python_get_log_empty_log_files_list(tmp_logs_dir: Path):
    (tmp_logs_dir / "a.log").write_text("something\n", encoding="utf-8")
    out = log_backend._python_get_log(
        pattern="",
        log_folder=str(tmp_logs_dir),
        filter_out=[],
        log_files=[],
    )
    assert out == ""


def test_get_log_passes_log_files_to_lnav():
    with (
        patch.object(log_backend, "is_lnav_available", return_value=True),
        patch.object(log_backend, "_lnav_log_line_count", return_value=5),
        patch.object(log_backend.subprocess, "run") as run,
    ):
        run.return_value = Mock(returncode=0, stdout=b"ok\n", stderr=b"")
        log_backend.get_log(
            pattern="",
            log_folder="logs",
            filter_out=[],
            log_files=["logs/OrderSvc-aabbccddeeff.log"],
        )
        called_cmd = run.call_args[0][0]
        assert "logs/OrderSvc-aabbccddeeff.log" in called_cmd
        assert "logs" not in [arg for arg in called_cmd if arg == "logs"]


def test_instance_log_files_numeric_rotations_oldest_first(tmp_logs_dir: Path):
    stem = "OrderSvc-aabbccddeeff"
    (tmp_logs_dir / ("%s.log" % stem)).write_text("cur\n", encoding="utf-8")
    (tmp_logs_dir / ("%s.log.1" % stem)).write_text("r1\n", encoding="utf-8")
    (tmp_logs_dir / ("%s.log.2" % stem)).write_text("r2\n", encoding="utf-8")
    (tmp_logs_dir / ("%s.log.2026-09-19" % stem)).write_text(
        "dated\n", encoding="utf-8"
    )
    (tmp_logs_dir / "OtherSvc-ffffffffffff.log.1").write_text(
        "nope\n", encoding="utf-8"
    )
    paths = log_backend.instance_log_files(
        str(tmp_logs_dir),
        "OrderSvc",
        "aabbccddeeff-0000-0000-0000-000000000000",
    )
    names = [Path(path).name for path in paths]
    assert names == [
        "%s.log.2" % stem,
        "%s.log.1" % stem,
        "%s.log" % stem,
    ]


def test_collect_flow_log_excerpt_filters_and_caps(tmp_logs_dir: Path):
    uuid = "aabbccddeeff-0000-0000-0000-000000000000"
    current = tmp_logs_dir / "OrderSvc-aabbccddeeff.log"
    rotated = tmp_logs_dir / "OrderSvc-aabbccddeeff.log.1"
    rotated.write_text(
        "[flow=deadbeef0000] old other\n[flow=a1b2c3d4e5f6] from rotated\n",
        encoding="utf-8",
    )
    current.write_text(
        "no flow here\n[flow=a1b2c3d4e5f6] from current\n[flow=a1b2c3d4e5f6] latest\n",
        encoding="utf-8",
    )
    lines = log_backend.collect_flow_log_excerpt(
        str(tmp_logs_dir),
        "a1b2c3d4e5f6",
        [("OrderSvc", uuid)],
        max_lines=2,
    )
    assert lines == [
        "[flow=a1b2c3d4e5f6] from current",
        "[flow=a1b2c3d4e5f6] latest",
    ]


def test_collect_flow_log_excerpt_keeps_traceback(tmp_logs_dir: Path):
    uuid = "aabbccddeeff-0000-0000-0000-000000000000"
    (tmp_logs_dir / "OrderSvc-aabbccddeeff.log").write_text(
        "\n".join(
            [
                "2026-09-19 11:40:10,123 [flow=a1b2c3d4e5f6] Uncaught in rpc_example",
                "Traceback (most recent call last):",
                '  File "rpc_service.py", line 42, in rpc_example',
                '    raise RuntimeError("Unexpected Server error")',
                "RuntimeError: Unexpected Server error",
                "2026-09-19 11:40:10,200 INFO other line without this flow",
                "2026-09-19 11:40:10,300 [flow=deadbeef0000] other flow",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    lines = log_backend.collect_flow_log_excerpt(
        str(tmp_logs_dir),
        "a1b2c3d4e5f6",
        [("OrderSvc", uuid)],
        max_lines=20,
    )
    assert lines == [
        "2026-09-19 11:40:10,123 [flow=a1b2c3d4e5f6] Uncaught in rpc_example",
        "Traceback (most recent call last):",
        '  File "rpc_service.py", line 42, in rpc_example',
        '    raise RuntimeError("Unexpected Server error")',
        "RuntimeError: Unexpected Server error",
    ]


def test_collect_flow_log_excerpt_merges_instances_chronologically(
    tmp_logs_dir: Path,
):
    uuid_a = "aaaaaaaaaaaa-0000-0000-0000-000000000000"
    uuid_b = "bbbbbbbbbbbb-0000-0000-0000-000000000000"
    (tmp_logs_dir / "ServiceA-aaaaaaaaaaaa.log").write_text(
        "\n".join(
            [
                "2026-09-28 09:00:00,100 - hostA - INFO - [flow=f1] publish",
                "2026-09-28 09:00:00,300 - hostA - INFO - [flow=f1] done",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_logs_dir / "ServiceB-bbbbbbbbbbbb.log").write_text(
        "\n".join(
            [
                "2026-09-28 09:00:00,200 - hostB - ERROR - [flow=f1] handler failed",
                "Traceback (most recent call last):",
                "ValueError: boom",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    lines = log_backend.collect_flow_log_excerpt(
        str(tmp_logs_dir), "f1", [("ServiceA", uuid_a), ("ServiceB", uuid_b)], 2000
    )
    assert lines == [
        "2026-09-28 09:00:00,100 - hostA - INFO - [flow=f1] publish",
        "2026-09-28 09:00:00,200 - hostB - ERROR - [flow=f1] handler failed",
        "Traceback (most recent call last):",
        "ValueError: boom",
        "2026-09-28 09:00:00,300 - hostA - INFO - [flow=f1] done",
    ]


def test_collect_flow_log_excerpt_unparsable_records_stay_last(
    tmp_logs_dir: Path,
):
    uuid = "aabbccddeeff-0000-0000-0000-000000000000"
    (tmp_logs_dir / "OrderSvc-aabbccddeeff.log").write_text(
        "\n".join(
            [
                "[flow=f1] no timestamp scanned first",
                "2026-09-28 09:00:00,100 - host - INFO - [flow=f1] dated record",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    lines = log_backend.collect_flow_log_excerpt(
        str(tmp_logs_dir), "f1", [("OrderSvc", uuid)], 2000
    )
    assert lines == [
        "2026-09-28 09:00:00,100 - host - INFO - [flow=f1] dated record",
        "[flow=f1] no timestamp scanned first",
    ]
