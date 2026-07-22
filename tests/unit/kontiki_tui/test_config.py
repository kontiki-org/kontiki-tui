from pathlib import Path

import yaml

from kontiki_tui.config import (
    BASE_CONF,
    get_group_filter,
    load,
    save_group_filter,
)


def test_load_creates_default_config_when_missing(tmp_path: Path):
    conf_path = tmp_path / "kontiki_tui.yaml"
    assert not conf_path.exists()

    conf = load(str(conf_path))
    assert conf == BASE_CONF
    assert conf_path.exists()
    assert conf["services"]["group_filter"] == "business"


def test_load_reads_existing_yaml(tmp_path: Path):
    conf_path = tmp_path / "kontiki_tui.yaml"
    data = {
        "amqp": {"url": "amqp://guest:guest@localhost/"},
        "logs": {"directory": "logs", "max-lines": 10},
    }
    conf_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

    conf = load(str(conf_path))
    assert conf == data


def test_get_group_filter_defaults():
    assert get_group_filter({}) == "business"
    assert get_group_filter(None) == "business"
    assert get_group_filter({"services": {}}) == "business"
    assert get_group_filter({"services": {"group_filter": "nope"}}) == "business"


def test_get_group_filter_reads_value():
    assert get_group_filter({"services": {"group_filter": "all"}}) == "all"
    assert get_group_filter({"services": {"group_filter": "business"}}) == "business"


def test_save_group_filter_persists(tmp_path: Path):
    conf_path = tmp_path / "kontiki_tui.yaml"
    conf_path.write_text(
        yaml.dump(
            {
                "amqp": {"url": "amqp://guest:guest@localhost/"},
                "logs": {"directory": "logs"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    conf = save_group_filter(str(conf_path), "all")
    assert conf["services"]["group_filter"] == "all"
    assert conf["amqp"]["url"] == "amqp://guest:guest@localhost/"

    reloaded = load(str(conf_path))
    assert reloaded["services"]["group_filter"] == "all"
