from pathlib import Path

import yaml

from kontiki_tui.config import BASE_CONF, load


def test_load_creates_default_config_when_missing(tmp_path: Path):
    conf_path = tmp_path / "kontiki_tui.yaml"
    assert not conf_path.exists()

    conf = load(str(conf_path))
    assert conf == BASE_CONF
    assert conf_path.exists()


def test_load_reads_existing_yaml(tmp_path: Path):
    conf_path = tmp_path / "kontiki_tui.yaml"
    data = {
        "amqp": {"url": "amqp://guest:guest@localhost/"},
        "logs": {"directory": "logs", "max-lines": 10},
    }
    conf_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

    conf = load(str(conf_path))
    assert conf == data
