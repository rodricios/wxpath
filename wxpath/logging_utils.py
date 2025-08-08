import logging
from logging.config import dictConfig
from typing import Any, Mapping


_DEFAULT_LOGGING_CONF = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {
            "format": (
                "%(asctime)s [%(levelname).1s] "
                "%(name)s | %(funcName)s | "
                "%(message)s | depth=%(depth)s op=%(op)s url=%(url)s"
            )
        }
    },
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "plain",
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

    Parameters
    ----------
    level
        "DEBUG"|"INFO"|... or `logging.DEBUG`, overrides the root wxpath logger.
    overrides
        Dict that is merged (shallow) into the default dictConfig.
        Lets advanced users swap formatters/handlers.
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