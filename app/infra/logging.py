import logging
import logging.config
import os


def setup_logging(level: str = "INFO", logs_dir: str = "logs") -> None:
    os.makedirs(logs_dir, exist_ok=True)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
                "compact": {
                    "format": "%(asctime)s | %(levelname)s | %(message)s",
                    "datefmt": "%H:%M:%S",
                },
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "compact"},
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": os.path.join(logs_dir, "app.log"),
                    "maxBytes": 10_000_000,
                    "backupCount": 5,
                    "formatter": "default",
                    "encoding": "utf-8",
                },
            },
            "root": {"handlers": ["console", "file"], "level": level.upper()},
        }
    )
