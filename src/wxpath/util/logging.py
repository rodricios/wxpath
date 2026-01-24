import logging
from logging.config import dictConfig
from typing import Any, Mapping


class KeyValueFormatter(logging.Formatter):
    """
    Formatter that automatically renders any 'extra' context added to the record
    as key=value pairs at the end of the log line.
    """
    # Reserved keys that already exist in LogRecord and shouldn't be printed again
    _RESERVED = {
        'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
        'funcName', 'levelname', 'levelno', 'lineno', 'message', 'module',
        'msecs', 'msg', 'name', 'pathname', 'process', 'processName',
        'relativeCreated', 'stack_info', 'thread', 'threadName', 'taskName'
    }

    def format(self, record: logging.LogRecord) -> str:
        # 1. Format the standard message first
        s = super().format(record)
        
        # 2. Find all 'extra' keys
        extras = {k: v for k, v in record.__dict__.items() if k not in self._RESERVED}
        
        # 3. Append them as key=value
        if extras:
            # Sort for deterministic logs
            context_str = " ".join(f"{k}={v}" for k, v in sorted(extras.items()))
            s = f"{s} | {context_str}"
            
        return s


_DEFAULT_LOGGING_CONF = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "kv": {
            # Note: We use the class path to our custom class
            "()": KeyValueFormatter, 
            "format": "%(asctime)s [%(levelname).1s] %(name)s | %(funcName)s | %(message)s"
        }
    },
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "kv",
        }
    },
    "loggers": {
        "wxpath": {"level": "INFO", "handlers": ["stderr"]},
    },
}

def configure_logging(level: str | int = "INFO", **overrides) -> None:
    """
    Configure wxpath's logger.

    Call this once in an application entry-point **or** rely on defaults.

    Args:
        level (str | int): Logging level to configure. Defaults to "INFO".
        **overrides: Additional logging configuration overrides
    """
    conf = {**_DEFAULT_LOGGING_CONF, **overrides}
    conf["loggers"]["wxpath"]["level"] = level
    dictConfig(conf)
    
    
class CrawlAdapter(logging.LoggerAdapter):
    """
    Inject crawl context (depth, op, url) so the handler/formatter
    never needs to know scraping internals.
    """
    def process(self, msg: str, kwargs: Mapping[str, Any]):
        extra = self.extra.copy()
        extra.update(kwargs.pop("extra", {}))
        kwargs["extra"] = extra
        return msg, kwargs

def get_logger(name: str, **ctx) -> CrawlAdapter:
    base = logging.getLogger(name)
    # default placeholders so formatter never blows up
    defaults = {"depth": "-", "op": "-", "url": "-"}
    defaults.update(ctx)
    return CrawlAdapter(base, defaults)