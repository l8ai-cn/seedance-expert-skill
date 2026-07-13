from __future__ import annotations

from urllib.parse import urlsplit


DEFAULT_API_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_API_HOST = "ark.cn-beijing.volces.com"


def validate_https_url(
    url: str,
    *,
    label: str,
    allowed_hosts: set[str] | None = None,
    allow_fragment: bool = False,
) -> str:
    if not isinstance(url, str) or not url:
        raise ValueError(f"{label} is required")
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"{label} must use HTTPS")
    if not parsed.hostname:
        raise ValueError(f"{label} must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} must not include credentials")
    try:
        parsed.port
    except ValueError as error:
        raise ValueError(f"{label} has an invalid port") from error
    if parsed.fragment and not allow_fragment:
        raise ValueError(f"{label} must not include a fragment")
    host = parsed.hostname.lower()
    if allowed_hosts is not None and host not in {item.lower() for item in allowed_hosts}:
        raise ValueError(f"{label} host {host!r} is not allowed")
    return url


def validate_api_base_url(url: str, allowed_hosts: set[str] | None = None) -> str:
    normalized = url.strip().rstrip("/")
    validated = validate_https_url(
        normalized,
        label="API base URL",
        allowed_hosts=allowed_hosts or {DEFAULT_API_HOST},
    )
    parsed = urlsplit(validated)
    if parsed.query:
        raise ValueError("API base URL must not include a query")
    return validated
