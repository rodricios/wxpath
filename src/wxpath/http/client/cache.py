try:
    from aiohttp_client_cache import SQLiteBackend
except ImportError:
    CachedSession = None

from wxpath.settings import SETTINGS
from wxpath.util.logging import get_logger

log = get_logger(__name__)

CACHE_SETTINGS = SETTINGS.http.client.cache

def get_cache_backend():
    log.info("cache backend", extra={"backend": CACHE_SETTINGS.backend})
    if CACHE_SETTINGS.backend == "redis":
        from aiohttp_client_cache.backends.redis import RedisBackend
        return RedisBackend(
            expire_after=CACHE_SETTINGS.expire_after,
            urls_expire_after=CACHE_SETTINGS.urls_expire_after or None,
            allowed_methods=CACHE_SETTINGS.allowed_methods,
            allowed_codes=CACHE_SETTINGS.allowed_codes,
            include_headers=CACHE_SETTINGS.include_headers,
            ignored_parameters=CACHE_SETTINGS.ignored_parameters,
            **CACHE_SETTINGS.redis
            # cache_name=CACHE_SETTINGS.redis.cache_name,
            # host=CACHE_SETTINGS.redis.host,
            # port=CACHE_SETTINGS.redis.port,
            # db=CACHE_SETTINGS.redis.db,
            # cache_control=CACHE_SETTINGS.cache_control,
        )
    elif CACHE_SETTINGS.backend == "sqlite":
        return SQLiteBackend(
            cache_name=CACHE_SETTINGS.sqlite.cache_name,
            expire_after=CACHE_SETTINGS.expire_after,
            urls_expire_after=CACHE_SETTINGS.urls_expire_after or None,
            allowed_methods=CACHE_SETTINGS.allowed_methods,
            allowed_codes=CACHE_SETTINGS.allowed_codes,
            include_headers=CACHE_SETTINGS.include_headers,
            ignored_parameters=CACHE_SETTINGS.ignored_parameters,
            # cache_control=CACHE_SETTINGS.cache_control,
        )
    else:
        raise ValueError(f"Unknown cache backend: {CACHE_SETTINGS.backend}")