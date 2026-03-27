import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kontiki_tui.backend.services import Services


@pytest.fixture
def messenger():
    return Mock(name="messenger")


@pytest.fixture
def services(messenger):
    return Services(messenger=messenger)


def test_is_internal_registry_event(services):
    assert services._is_internal_registry_event({"event_type": "_rpc_event"})
    assert services._is_internal_registry_event({"service_name": "ServiceRegistry"})
    assert services._is_internal_registry_event({"service_name": "kontiki_tui"})
    assert services._is_internal_registry_event(
        {"service_name": "kontiki_tui-standalone-x"}
    )

    assert not services._is_internal_registry_event({"service_name": "kontiki"})
    assert not services._is_internal_registry_event({"service_name": "MyService"})


def test_filter_registry_events(services):
    events = [
        {"event_type": "_rpc_event", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "ServiceRegistry"},
        {"event_type": "business", "service_name": "kontiki_tui"},
        {"event_type": "business", "service_name": "SvcB"},
    ]

    kept = services._filter_registry_events(events, include_internal=False)
    assert kept == [
        {"event_type": "business", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcB"},
    ]

    kept_internal = services._filter_registry_events(events, include_internal=True)
    assert kept_internal == events


def test_get_stats_returns_empty_for_non_local_host(services):
    assert services.get_stats(pid=123, host="some-remote-host") == {}


def test_get_stats_returns_empty_for_invalid_pid(services):
    with patch(
        "kontiki_tui.backend.services.socket.gethostname", return_value="myhost"
    ):
        assert services.get_stats(pid="not-a-pid", host="myhost") == {}


def test_get_stats_returns_cpu_mem_fd_for_local_pid(services):
    proc = Mock()
    proc.cpu_percent.return_value = 12.5

    mem_info = Mock()
    mem_info.rss = 50 * 1024 * 1024  # 50 MB
    proc.memory_info.return_value = mem_info
    proc.num_fds.return_value = 42

    with (
        patch("kontiki_tui.backend.services.socket.gethostname", return_value="myhost"),
        patch("kontiki_tui.backend.services.psutil.Process", return_value=proc),
    ):
        stats = services.get_stats(pid=123, host="myhost")
        assert stats["cpu_percent"] == 12.5
        assert stats["mem_mb"] == 50.0
        assert stats["fd_count"] == 42


def test_get_stats_returns_empty_when_psutil_raises(services):
    # psutil exceptions are swallowed and should return {}
    with (
        patch("kontiki_tui.backend.services.socket.gethostname", return_value="myhost"),
        patch(
            "kontiki_tui.backend.services.psutil.Process",
            side_effect=Exception("boom"),
        ),
    ):
        assert services.get_stats(pid=123, host="myhost") == {}


def test_get_events_filters_registry_noise(services):
    raw = [
        {"event_type": "_rpc_event", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "ServiceRegistry"},
        {"event_type": "business", "service_name": "kontiki_tui"},
        {"event_type": "business", "service_name": "SvcB"},
    ]

    services.services.get_events = AsyncMock(return_value=raw)
    out = asyncio.run(services.get_events())
    assert out == [
        {"event_type": "business", "service_name": "SvcA"},
        {"event_type": "business", "service_name": "SvcB"},
    ]
