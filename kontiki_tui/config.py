import logging
import os
from pathlib import Path

import yaml

# -----------------------------------------------------------------------------

CONF_FILE = os.path.join(Path.home(), ".config", "kontiki_tui.yaml")

BASE_CONF = {
    "amqp": {"url": "amqp://guest:guest@localhost:5672"},
    "logs": {
        "directory": "logs",
        # Maximum number of log lines to display in the UI.
        # If not set in the user config, this default will be used.
        "max-lines": 2000,
    },
    # Services tab: default to business workloads; use "all" to include platform.
    "services": {
        "group_filter": "business",
    },
}

VALID_GROUP_FILTERS = ("business", "all")

# -----------------------------------------------------------------------------


def load(conf_file):
    if os.path.exists(conf_file):
        try:
            with open(conf_file, "r") as file:
                logging.debug(f"Loading {conf_file} configuration file.")
                return yaml.load(file, Loader=yaml.FullLoader)
        except OSError:
            msg = f"Internal error: '{conf_file}' load in memory failed."
            raise RuntimeError(msg)
    else:
        os.makedirs(os.path.dirname(conf_file), exist_ok=True)
        try:
            with open(conf_file, "w") as file:
                logging.debug(f"Writing {conf_file} configuration file.")
                yaml.dump(BASE_CONF, file, sort_keys=False)
            return BASE_CONF
        except OSError:
            msg = f"Internal error: '{conf_file}' write on disk failed."
            raise RuntimeError(msg)


def get_group_filter(conf):
    """Return the Services tab group filter (``business`` or ``all``)."""
    if not isinstance(conf, dict):
        return "business"
    services = conf.get("services")
    if not isinstance(services, dict):
        return "business"
    value = services.get("group_filter", "business")
    if value not in VALID_GROUP_FILTERS:
        return "business"
    return value


def save_group_filter(conf_file, group_filter):
    """Persist the Services group filter into the user config file."""
    if group_filter not in VALID_GROUP_FILTERS:
        group_filter = "business"
    conf = load(conf_file)
    if not isinstance(conf, dict):
        conf = dict(BASE_CONF)
    services = conf.get("services")
    if not isinstance(services, dict):
        services = {}
        conf["services"] = services
    services["group_filter"] = group_filter
    try:
        with open(conf_file, "w") as file:
            yaml.dump(conf, file, sort_keys=False)
    except OSError:
        msg = f"Internal error: '{conf_file}' write on disk failed."
        raise RuntimeError(msg)
    return conf
