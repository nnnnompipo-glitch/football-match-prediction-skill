"""Validate links before retaining or rendering provider-supplied references."""
from urllib.parse import urlsplit


def safe_web_url(value):
    if not isinstance(value, str) or not value or "\\" in value or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme.lower() not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None or parts.port == 0):
            return None
    except ValueError:
        return None
    return value
