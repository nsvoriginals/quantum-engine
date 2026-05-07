import logging
import os


def configure_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    use_json = os.getenv("LOG_FORMAT", "json").lower() == "json"

    handler = logging.StreamHandler()
    if use_json:
        try:
            from pythonjsonlogger import jsonlogger

            formatter = jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ",
            )
            handler.setFormatter(formatter)
        except ImportError:
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s")
            )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s")
        )

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)
