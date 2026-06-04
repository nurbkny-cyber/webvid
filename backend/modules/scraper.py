"""Scraper module for WebVid.

General-purpose extraction from arbitrary public websites.
Security wrapped from the first line (validate + rate limit + sanitize).
No domain-specific logic (no real-estate, no listings).
Uses only stdlib for V0.1 (regex + html + urllib). Later can plug trafilatura etc.
"""

import re
import json
import html as htmlmod
import ssl
import time
import hashlib
import os
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Dict, Any, List

from .models import WebContent
from .security import (
    validate_and_sanitize_url,
    sanitize_web_content,
    check_rate_limit,
    scrape_rate_limiter,
    security_logger,
)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".cache")
CACHE_TTL = 3600
SSL_CTX = ssl._create_unverified_context()  # tolerate bad certs on user sites; still https enforced upstream

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


def _get_cached(url: str) -> Optional[Dict[str, Any]]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.md5(url.encode()).hexdigest()
    p = os.path.join(CACHE_DIR, f"{h}.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            if time.time() - d.get("_ts", 0) < CACHE_TTL:
                d.pop("_ts", None)
                return d
        except Exception:
            pass
    return None


def _set_cache(url: str, data: Dict[str, Any]):
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.md5(url.encode()).hexdigest()
    p = os.path.join(CACHE_DIR, f"{h}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({**data, "_ts": time.time()}, f)


def clean_text(t: str) -> str:
    if not t:
        return ""
    t = htmlmod.unescape(str(t))
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:2000]


def _extract_meta(html: str) -> Dict[str, str]:
    out = {}
    # og:title, og:description, twitter, standard title
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    if m: out["og_title"] = clean_text(m.group(1))
    m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    if m: out["og_description"] = clean_text(m.group(1))
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    if m: out["meta_description"] = clean_text(m.group(1))
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if m: out["title"] = clean_text(m.group(1))
    # Also try h1 as last resort for title
    if not out.get("title") and not out.get("og_title"):
        m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
        if m: out["title"] = clean_text(m.group(1))
    return out


def _extract_images(html: str, base_url: str) -> List[str]:
    imgs = []
    # og:image first (most relevant)
    for m in re.finditer(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I):
        u = m.group(1).strip()
        if u.startswith("//"): u = "https:" + u
        if u.startswith("/"): u = urllib.parse.urljoin(base_url, u)
        if u.startswith("http"): imgs.append(u)
    # img tags, prefer larger or data
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I):
        u = m.group(1).strip()
        if u.startswith("data:"): continue
        if u.startswith("//"): u = "https:" + u
        if u.startswith("/"): u = urllib.parse.urljoin(base_url, u)
        if u.startswith("http") and u not in imgs:
            imgs.append(u)
        if len(imgs) >= 5: break
    return imgs[:5]


def _extract_main_text(html: str) -> str:
    # Try article/main content heuristically (no bs4)
    # Remove scripts/styles/nav
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<nav[^>]*>.*?</nav>", " ", html)
    html = re.sub(r"(?is)<footer[^>]*>.*?</footer>", " ", html)
    # Grab long paragraphs
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
    text = " ".join(clean_text(p) for p in paras if len(p) > 40)
    if len(text) < 120:
        # fallback to body text
        body = re.search(r"(?is)<body[^>]*>(.*?)</body>", html)
        if body:
            text = clean_text(body.group(1))[:1500]
    return text[:1800]


def fetch_page(url: str) -> str:
    security_logger.info(f"[fetch] {url}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=12, context=SSL_CTX) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        raw = resp.read()
        data = raw.decode(charset, errors="replace")
        security_logger.info(f"[fetch] {len(data)} chars")
        return data


def extract_web_content(url: str) -> WebContent:
    """Main entry: secure fetch + general extraction -> WebContent."""
    url = validate_and_sanitize_url(url)
    check_rate_limit(scrape_rate_limiter, key="global")  # simple; could key by client later

    cached = _get_cached(url)
    if cached:
        security_logger.info("[scrape] cache hit")
        return WebContent.from_dict(cached)

    try:
        page = fetch_page(url)
    except Exception as e:
        msg = str(e)
        if any(x in msg for x in ["nodename nor servname", "Name or service not known", "getaddrinfo", "Temporary failure in name resolution"]):
            raise ValueError("Could not resolve the website (DNS error). Check the URL for typos or try a working public site like https://httpbin.org/html .")
        if "timed out" in msg.lower() or "timeout" in msg.lower():
            raise ValueError("Connection to the website timed out. The site may be slow, down, or blocking scrapers. Try a different URL.")
        raise ValueError(f"Could not fetch content from the site: {msg[:120]}. Some sites block automated requests or require login/JS.")
    meta = _extract_meta(page)
    title = meta.get("og_title") or meta.get("title") or ""
    if not title:
        try:
            title = urllib.parse.urlparse(url).netloc or "Website"
        except Exception:
            title = "Website"
    desc = meta.get("og_description") or meta.get("meta_description") or ""
    main = _extract_main_text(page)
    images = _extract_images(page, url)

    # key points: split on sentences or bullets if present
    points = []
    for m in re.findall(r"(?:^|[\.\!\?])\s*([A-Z][^\.\!\?]{25,140}[\.\!\?])", main):
        if len(points) < 5:
            points.append(m.strip())
    if not points and main:
        # crude: first 3 sentences-ish
        chunks = re.split(r"[\.\!\?]\s+", main)
        points = [c.strip() for c in chunks[:4] if len(c.strip()) > 20]

    data = {
        "url": url,
        "title": title[:120],
        "description": desc[:300],
        "main_text": main,
        "key_points": points[:5],
        "images": images,
        "meta": meta,
    }
    data = sanitize_web_content(data)
    _set_cache(url, data)
    return WebContent.from_dict(data)


# Back-compat alias if old code references it
scrape_listing = extract_web_content
