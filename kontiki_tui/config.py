import logging
import os

import yaml

# -----------------------------------------------------------------------------

BASE_CONF = {
    "amqp": {"url": "amqp://guest:guest@localhost:5672"},
    "logs": {
        "directory": "logs",
        # Maximum number of log lines to display in the UI.
        # If not set in the user config, this default will be used.
        "max-lines": 2000,
    },
}

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
