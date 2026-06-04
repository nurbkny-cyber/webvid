#!/usr/bin/env python3
"""
WebVid Backend Server (V0.1)

Thin orchestrator per Modular Creed.
- Pure stdlib http.server
- Security wrappers on all inputs
- Routes: health, extract, script, render (the expensive one)
- Serves rendered videos statically from /renders/<file>

Run: python backend/server.py
Ports chosen to avoid conflicts (see run.sh).
"""

import http.server
import json
import urllib.parse
import time
import os
import sys
import mimetypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.models import WebContent
from modules.security import (
    security_logger,
    check_rate_limit,
    scrape_rate_limiter,
    script_rate_limiter,
    render_rate_limiter,
    validate_and_sanitize_url,
)
from modules.scraper import extract_web_content
from modules.script_generator import generate_script
from modules.storyboard import build_storyboard
from modules.renderer import render_video, RENDERS_DIR

PORT = 4819


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")


def _json(h, data, status=200):
    body = json.dumps(data, indent=2, default=str).encode("utf-8")
    h.send_response(status)
    _cors(h)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _send_file(h, path: str, content_type: str = None):
    if not os.path.exists(path):
        h.send_response(404)
        h.end_headers()
        return
    size = os.path.getsize(path)
    ct = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
    h.send_response(200)
    _cors(h)
    h.send_header("Content-Type", ct)
    h.send_header("Content-Length", str(size))
    h.send_header("Cache-Control", "public, max-age=3600")
    h.end_headers()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.wfile.write(chunk)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.end_headers()

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == "/api/health":
            ai_key = bool(os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY"))
            _json(self, {
                "status": "ok",
                "name": "WebVid",
                "version": "0.1",
                "creed": "active",
                "ffmpeg": __import__("modules.renderer", fromlist=["is_ffmpeg_available"]).is_ffmpeg_available(),
                "ai_enabled": ai_key,
                "ai_note": "Set XAI_API_KEY or GROK_API_KEY env var for Grok-powered script generation",
            })
            return

        if p.path.startswith("/renders/"):
            fname = p.path.split("/renders/", 1)[1]
            # basic safety: no path traversal
            if ".." in fname or "/" in fname or "\\" in fname:
                _json(self, {"error": "bad filename"}, 400)
                return
            full = os.path.join(RENDERS_DIR, fname)
            _send_file(self, full)
            return

        if p.path == "/api/renders":
            files = []
            for f in sorted(os.listdir(RENDERS_DIR)):
                if f.endswith((".mp4", ".gif")):
                    files.append({"file": f, "url": f"/renders/{f}"})
            _json(self, {"renders": files})
            return

        _json(self, {
            "name": "WebVid API",
            "version": "0.1",
            "endpoints": [
                "GET /api/health",
                "POST /api/extract {url}",
                "POST /api/script {web_content, tone?, target_seconds?}",
                "POST /api/render {script, scenes?, images?, options?}",
                "GET /renders/<file>",
            ],
            "note": "All POSTs enforce security + rate limits. Render is the costly operation."
        })

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            data = json.loads(body) if body.strip() else {}
        except Exception as e:
            _json(self, {"error": f"bad json: {e}", "success": False}, 400)
            return

        ip = self.client_address[0]

        if p == "/api/extract":
            url = data.get("url", "")
            if not url:
                _json(self, {"error": "url required", "success": False}, 400)
                return
            try:
                check_rate_limit(scrape_rate_limiter, ip)
                content = extract_web_content(url)
                _json(self, {"success": True, "data": content.to_dict()})
            except Exception as e:
                msg = str(e)
                security_logger.error(f"extract error: {msg}")
                # Always provide clean user-friendly messages; never leak raw Python/traceback
                if any(x in msg for x in ["nodename nor servname", "Name or service not known", "getaddrinfo", "Temporary failure in name resolution", "Could not resolve the website (DNS error)"]):
                    friendly = "Could not resolve the website (DNS error). Check the URL for typos or try a working public site like https://httpbin.org/html ."
                elif "timed out" in msg.lower() or "timeout" in msg.lower() or "Connection to the website timed out" in msg:
                    friendly = "Connection to the website timed out. The site may be slow, down, or blocking scrapers. Try a different URL."
                else:
                    friendly = "Could not fetch content from the site. Some sites block automated requests, are down, or require login/JS. Try a simple public page like https://httpbin.org/html ."
                _json(self, {"error": friendly, "success": False}, 400)

        elif p == "/api/script":
            try:
                check_rate_limit(script_rate_limiter, ip)
                raw = data.get("web_content") or data
                content = WebContent.from_dict(raw)
                tone = data.get("tone", "professional")
                secs = int(data.get("target_seconds", 30))
                use_ai = bool(data.get("use_ai", False))
                script = generate_script(content, tone=tone, target_seconds=secs, use_ai=use_ai)
                _json(self, {"success": True, "script": script.to_dict()})
            except Exception as e:
                security_logger.error(f"script error: {e}")
                _json(self, {"error": str(e), "success": False}, 400)

        elif p == "/api/render":
            # This is the money shot + the abuse target. Strict limits.
            try:
                check_rate_limit(render_rate_limiter, ip)
                # Accept either full script+images or minimal
                script_dict = data.get("script") or {}
                if not script_dict.get("hook"):
                    # allow minimal {hook, points, cta}
                    script_dict = {
                        "hook": data.get("hook", "Key insight"),
                        "points": data.get("points", []),
                        "cta": data.get("cta", "Full story on site"),
                        "full_text": data.get("full_text", ""),
                        "target_seconds": data.get("target_seconds", 30),
                    }
                from modules.models import Script
                script = Script(
                    hook=script_dict.get("hook", ""),
                    points=script_dict.get("points", []) or [],
                    cta=script_dict.get("cta", ""),
                    full_text=script_dict.get("full_text") or "",
                    target_seconds=int(script_dict.get("target_seconds", 30)),
                )
                scenes_raw = data.get("scenes") or []
                scenes = []
                if scenes_raw:
                    from modules.models import Scene
                    for s in scenes_raw:
                        scenes.append(Scene(
                            index=s.get("index", 0),
                            text=s.get("text", ""),
                            duration=float(s.get("duration", 4)),
                            visual=s.get("visual", "bullet"),
                        ))
                else:
                    scenes = build_storyboard(script)

                images = data.get("images", []) or []
                asset = render_video(script, scenes, images)
                _json(self, {
                    "success": True,
                    "asset": {
                        "id": asset.id,
                        "url": f"/renders/{asset.path}",
                        "duration": asset.duration,
                        "format": asset.format,
                        "width": asset.width,
                        "height": asset.height,
                    },
                    "note": "Free tier includes watermark. Upgrade for clean exports."
                })
            except Exception as e:
                security_logger.error(f"render error: {e}")
                _json(self, {"error": str(e), "success": False}, 400)

        else:
            _json(self, {"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        security_logger.info(f"[{time.strftime('%H:%M:%S')}] {args[0]}")


if __name__ == "__main__":
    print(f"\n  WebVid Backend (V0.1 - Creed Compliant) on http://localhost:{PORT}")
    print("  Endpoints: /api/extract, /api/script, /api/render, /renders/<file>")
    print("  Security: SSRF blocks, rate limits (strict on render), sanitized inputs.")
    print("  Tip: brew install ffmpeg  for real MP4 output (otherwise GIF fallback)\n")
    try:
        http.server.HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
