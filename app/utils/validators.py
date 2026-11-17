import ipaddress
import socket
from urllib.parse import urlparse


class URLValidationError(ValueError):
    """Raised when a URL is malformed or points to a disallowed/private network."""


_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".arpa")


def _is_disallowed_ip(ip_str: str) -> bool:
    """Return True if the IP address is private, loopback, link-local, or reserved."""
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(raw_url: str) -> str:
    """Validate URL format and enforce SSRF protection against internal networks."""
    url = (raw_url or "").strip()
    if not url:
        raise URLValidationError("URL must not be empty.")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise URLValidationError("URL scheme must be http or https.")

    if not parsed.netloc or not parsed.hostname:
        raise URLValidationError("URL must include a valid hostname.")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in _BLOCKED_HOSTNAMES or any(
        hostname.endswith(suffix) for suffix in _BLOCKED_SUFFIXES
    ):
        raise URLValidationError("Access to local or internal hostnames is not allowed.")

    # Direct IP literal check
    try:
        if _is_disallowed_ip(hostname):
            raise URLValidationError("Access to private or reserved IP addresses is not allowed.")
        return url
    except ValueError:
        pass  # Not an IP literal; resolve DNS below

    # Resolve hostname and verify all resolved IPs are public
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise URLValidationError(f"Could not resolve hostname '{hostname}'.") from exc

    if not addr_info:
        raise URLValidationError(f"No DNS records found for hostname '{hostname}'.")

    for entry in addr_info:
        ip_str = entry[4][0].split("%")[0]
        if _is_disallowed_ip(ip_str):
            raise URLValidationError(
                "Target hostname resolves to a private or internal IP address."
            )

    return url
