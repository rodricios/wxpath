"""
Settings for wxpath.

These settings are global and can be accessed from any module in the wxpath package.

They are typically used by various modules to configure Class initializers.

The SETTINGS dict structure follows the structure of wxpath submodules.

Expected usage behavior:

```python
from wxpath.settings import SETTINGS

CACHE_SETTINGS = SETTINGS.http.client.cache
```

Once initialized, the settings are expected to be immutable (not enforced).
"""

from datetime import timedelta

# Settings match 
SETTINGS = {
    'http': {
        'client': {
            'cache': {
                'enabled': False,
                # 'db_path': 'cache.db',
                'expire_after': timedelta(days=7),
                'urls_expire_after': None,
                'allowed_methods': ("GET", "HEAD"),
                'allowed_codes': (200, 203, 301, 302, 307, 308),
                'ignored_parameters': ["utm_*", "fbclid"],
                'include_headers': False,   # don’t vary cache keys on headers by default
                'cache_control': False,     # honor Cache-Control/Expires if present
                # # TODO: size hedges (soft, enforced by wxpath)
                # 'max_entries': None,        # e.g. 1_000_000
                # 'max_response_size': None,  # bytes, e.g. 2_000_000
                # 'max_db_size': None,        # bytes, e.g. 5 * 1024**3
                'backend': "sqlite",
                'sqlite': {
                    'cache_name': "cache.db",
                },
                'redis': {
                    # 'host': "localhost",
                    # 'port': 6379,
                    # 'db': 0,
                    'address': 'redis://localhost:6379/0',
                    'cache_name': "wxpath:",
                }
            },
            'crawler': {
                'concurrency': 16,
                'per_host': 8,
                'timeout': 15,
                'verify_ssl': True,
                'headers': {
                    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" 
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/142.0.0.0 Safari/537.36")
                },
                'proxies': None,
                'auto_throttle_target_concurrency': None,
                'auto_throttle_start_delay': 0.25,
                'auto_throttle_max_delay': 10.0,
                'respect_robots': True,
            },
        },
    },
}


class AttrDict(dict):
    """
    A dictionary subclass that allows dot-notation access while 
    recursively converting nested dictionaries.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Point the instance __dict__ to itself to allow attribute access
        self.__dict__ = self
        # Recursively convert any dicts passed during initialization
        for key, value in self.items():
            self[key] = self._convert(value)

    @classmethod
    def _convert(cls, value):
        """Recursively converts dicts to AttrDicts, leaving other types alone."""
        if isinstance(value, dict):
            return cls(value)
        elif isinstance(value, list):
            # Optional: converts dicts inside lists while keeping the list container
            return [cls._convert(item) for item in value]
        return value

    def __setitem__(self, key, value):
        # Ensure that new items added via dict-syntax are also converted
        super().__setitem__(key, self._convert(value))

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(f"AttrDict object has no attribute '{key}'") from exc


SETTINGS = AttrDict(SETTINGS)
CACHE_SETTINGS = SETTINGS.http.client.cache
CRAWLER_SETTINGS = SETTINGS.http.client.crawler