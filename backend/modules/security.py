"""Security module for WebVid.

Implements Security-by-Design Directive + CLAUDE #1 Constitution as core.
- All external URLs + scraped content treated as hostile.
- SSRF protection (private IP blocks, metadata endpoints).
- Strict rate limiting on expensive operations (render video = high CPU + potential cost).
- Input sanitization, length caps, logging of security events.
- No secrets in code. Least privilege.
"""

import re
import time
import logging
import ipaddress
import shutil
from urllib.parse import urlparse
from typing import Dict, Tuple, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [webvid.security] %(levelname)s %(message)s'
)
security_logger = logging.getLogger("webvid.security")


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}

    def allow(self, key: str) -> Tuple[bool, Optional[int]]:
        now = time.time()
        if key not in self.requests:
            self.requests[key] = []
        self.requests[key] = [t for t in self.requests[key] if now - t < self.window_seconds]
        if len(self.requests[key]) < self.max_requests:
            self.requests[key].append(now)
            return True, None
        oldest = self.requests[key][0]
        retry_after = int(self.window_seconds - (now - oldest)) + 1
        security_logger.warning(f"Rate limit hit key={key} retry_after={retry_after}s")
        return False, retry_after


# V0.1 limiters. Render is the profit/DoS sensitive one (CPU, disk, time).
# Freemium: very low daily-like via larger window or small count.
scrape_rate_limiter = RateLimiter(max_requests=8, window_seconds=60)
script_rate_limiter = RateLimiter(max_requests=20, window_seconds=60)
# Strict for render: e.g. 3 free per ~10min window for demo; in real would be daily + user quota.
render_rate_limiter = RateLimiter(max_requests=3, window_seconds=600)


def validate_and_sanitize_url(url: str) -> str:
    """SSRF + hostile URL defense. Called on every user-supplied URL."""
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP/HTTPS URLs allowed")
    if not parsed.netloc:
        raise ValueError("Invalid URL: missing host")

    # SSRF: block private, loopback, reserved, link-local, metadata
    try:
        host = parsed.hostname
        if host:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                security_logger.warning(f"Blocked private/internal IP in URL: {url}")
                raise ValueError("Access to private or internal networks is not allowed")
    except ValueError:
        pass  # hostname not IP, continue

    dangerous = {
        "169.254.169.254", "metadata.google.internal", "metadata.packet.net",
        "169.254.0.0/16", "localhost", "127.0.0.1", "::1"
    }
    if parsed.hostname in dangerous or any(parsed.hostname.endswith(d) for d in [".internal", ".local"]):
        security_logger.warning(f"Blocked dangerous host: {url}")
        raise ValueError("Access to metadata or internal services is not allowed")

    if re.search(r'[<>"\']', url):
        raise ValueError("URL contains invalid characters")

    # Reasonable length
    if len(url) > 2048:
        raise ValueError("URL too long")

    security_logger.info(f"URL validated: {url[:80]}...")
    return url


def sanitize_web_content(data: dict) -> dict:
    """Treat all scraped content as untrusted. Cap lengths, drop junk."""
    if not isinstance(data, dict):
        return {}
    out = {}
    for k in ("title", "description", "main_text"):
        v = data.get(k, "")
        if isinstance(v, str):
            out[k] = v.strip()[:4000]
    out["key_points"] = [str(p).strip()[:300] for p in (data.get("key_points") or [])[:8] if p]
    imgs = data.get("images") or []
    out["images"] = [str(i).strip()[:500] for i in imgs[:6] if i and str(i).startswith(("http://", "https://"))]
    out["url"] = data.get("url", "")[:500]
    out["meta"] = {k: str(v)[:200] for k, v in (data.get("meta") or {}).items()}
    return out


def check_rate_limit(limiter: RateLimiter, key: str = "default") -> None:
    allowed, retry = limiter.allow(key)
    if not allowed:
        security_logger.error(f"Rate limit exceeded for {key}")
        raise Exception(f"Rate limit exceeded. Try again in {retry} seconds.")


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None
