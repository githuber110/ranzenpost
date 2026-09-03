import ipaddress
from urllib.parse import urlparse

from .crypto import looks_like_base32


def normalize_school_url(raw):
    value = (raw or "").strip()
    if not value:
        raise ValueError("empty url")
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if not host or "." not in host:
        raise ValueError("invalid host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        raise ValueError("blocked host")
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{host}{port}"


def clean_totp_secret(raw):
    return (raw or "").replace(" ", "").replace("-", "").upper()


def is_valid_secret(cleaned):
    return looks_like_base32(cleaned)


def is_valid_code(raw):
    value = (raw or "").strip()
    return len(value) == 6 and value.isdigit()
