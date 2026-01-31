"""Persistent TUI settings: load/save crawler-related options from a config file.

pre-1.0.0 - APIs and contracts may change.

Settings are stored in a single JSON file (e.g. ~/.config/wxpath/tui_settings.json).
The schema is defined in TUISettingsSchema; adding a new setting requires one new
entry in the schema and, if needed, use of that value where the crawler/engine
is created.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from wxpath.settings import CRAWLER_SETTINGS


def _config_dir() -> Path:
    """Return the wxpath config directory, creating it if needed."""
    xdg_env = os.environ.get("XDG_CONFIG_HOME")
    if xdg_env:
        base = Path(xdg_env)
    else:
        base = Path.home() / ".config"
    path = base / "wxpath"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_tui_settings_path() -> Path:
    """Return the path to the TUI settings JSON file."""
    return _config_dir() / "tui_settings.json"


# Schema: one dict per setting. 
# Keys: key (file/API), label (display), type, default, optional min/max, help.
# Defaults are taken from CRAWLER_SETTINGS so there is a single source of truth for built-in values.
TUISettingsSchema: list[dict[str, Any]] = [
    {
        "key": "concurrency",
        "label": "CONCURRENCY",
        "type": "int",
        "default": getattr(CRAWLER_SETTINGS, "concurrency", 16),
        "min": 1,
        "max": 256,
        "help": "Maximum number of concurrent HTTP requests.",
    },
    {
        "key": "per_host",
        "label": "PER_HOST",
        "type": "int",
        "default": getattr(CRAWLER_SETTINGS, "per_host", 8),
        "min": 1,
        "max": 64,
        "help": "Maximum concurrent requests per host.",
    },
    {
        "key": "respect_robots",
        "label": "RESPECT_ROBOTS",
        "type": "bool",
        "default": getattr(CRAWLER_SETTINGS, "respect_robots", True),
        "help": "Whether to respect robots.txt directives.",
    },
    {
        "key": "verify_ssl",
        "label": "VERIFY_SSL",
        "type": "bool",
        "default": getattr(CRAWLER_SETTINGS, "verify_ssl", True),
        "help": "Verify SSL certificates. Disable for sites with broken certificate chains.",
    },
]


def _defaults_from_schema() -> dict[str, Any]:
    """Build a dict of default values from the schema."""
    return {s["key"]: s["default"] for s in TUISettingsSchema}


def validate_tui_settings(settings: dict[str, Any]) -> list[str]:
    """Validate all schema keys; return list of error messages (empty if valid)."""
    errors = []
    for key, value in settings.items():
        try:
            _validate_value(key, value, TUISettingsSchema)
        except ValueError as e:
            errors.append(str(e))
    return errors


def _validate_value(key: str, value: Any, schema: list[dict[str, Any]]) -> Any:
    """Validate and coerce a single value. Returns the coerced value or raises ValueError."""
    entry = next((e for e in schema if e["key"] == key), None)
    if not entry:
        raise ValueError(f"Unknown setting: {key}")
    t = entry["type"]
    if t == "int":
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key}: expected integer, got {type(value).__name__}") from None
        min_v = entry.get("min")
        max_v = entry.get("max")
        if min_v is not None and v < min_v:
            raise ValueError(f"{key}: must be >= {min_v}")
        if max_v is not None and v > max_v:
            raise ValueError(f"{key}: must be <= {max_v}")
        return v
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    return value


def load_tui_settings() -> dict[str, Any]:
    """Load TUI settings from the config file. Missing or invalid keys use schema defaults."""
    path = get_tui_settings_path()
    defaults = _defaults_from_schema()
    if not path.exists():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    result = dict(defaults)
    for key in result:
        if key not in raw:
            continue
        try:
            result[key] = _validate_value(key, raw[key], TUISettingsSchema)
        except ValueError:
            pass
    return result


def save_tui_settings(settings: dict[str, Any]) -> None:
    """Save TUI settings to the config file. Only schema keys are written."""
    path = get_tui_settings_path()
    schema_keys = {s["key"] for s in TUISettingsSchema}
    to_write = {k: v for k, v in settings.items() if k in schema_keys}
    for key in schema_keys:
        if key not in to_write:
            to_write[key] = _defaults_from_schema()[key]
    path.write_text(json.dumps(to_write, indent=2), encoding="utf-8")
