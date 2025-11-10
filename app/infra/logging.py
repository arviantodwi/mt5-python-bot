import logging
import logging.config
import os
# from typing import Literal, Optional

# LogTag = Literal["CANDLE", "EXECUTOR", "GUARD", "INDICATOR", "KERNEL", "SCHEDULER", "SIGNAL"]


# Handles logging, including conditional extra data for backward compatibility with v0.0.9.
# This feature is temporary and will be removed in the next minor release.
# class ConditionalTagFormatter(logging.Formatter):
#     """
#     A custom logging formatter that applies different formats based on the presence of a 'tag' attribute in the log record.
#     - If a 'tag' is present, it uses the 'fmt_tagged' format.
#     - Otherwise, it uses the 'fmt_untagged' format.
#     """

#     def __init__(self, fmt_tagged: str, fmt_untagged: str, datefmt: Optional[str] = None):
#         super().__init__(datefmt=datefmt)
#         self.fmt_tagged = fmt_tagged
#         self.fmt_untagged = fmt_untagged

#     def format(self, record: logging.LogRecord) -> str:
#         # Store original format
#         original_format = self._style._fmt

#         if hasattr(record, "tag"):
#             self._style._fmt = self.fmt_tagged
#         else:
#             self._style._fmt = self.fmt_untagged

#         # Call the parent class's format method
#         result = super().format(record)

#         # Restore the original format
#         self._style._fmt = original_format

#         return result


def setup_logging(level: str = "INFO", logs_dir: str = "logs") -> None:
    os.makedirs(logs_dir, exist_ok=True)

    # DEFAULT_FORMAT_TAGGED = "%(asctime)s | %(name)-27s | %(levelname)-8s | %(tag)-9s ▶ %(message)s"
    DEFAULT_FORMAT = "%(asctime)s | %(name)-27s | [%(levelname)-8s] (%(tag)s) %(message)s"
    COMPACT_FORMAT = "%(asctime)s [%(levelname)-8s] (%(tag)s) %(message)s"

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": DEFAULT_FORMAT,
                    # "()": ConditionalTagFormatter,
                    # "fmt_tagged": DEFAULT_FORMAT_TAGGED,
                    # "fmt_untagged": DEFAULT_FORMAT_UNTAGGED,
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
                "compact": {
                    "format": COMPACT_FORMAT,
                    # "()": ConditionalTagFormatter,
                    # "fmt_tagged": COMPACT_FORMAT_TAGGED,
                    # "fmt_untagged": COMPACT_FORMAT_UNTAGGED,
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "compact",
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "default",
                    "encoding": "utf-8",
                    "filename": os.path.join(logs_dir, "app.log"),
                    "maxBytes": 10_000_000,
                    "backupCount": 5,
                },
            },
            "root": {"handlers": ["console", "file"], "level": level.upper()},
        }
    )
