# WebVid Architecture (V0.1)

**Product**: Any public website URL → short vertical video (15-60s) with script, captions, B-roll, ready for Reels/TikTok/Shorts.

This is the correct scope. Not real-estate social assets. Not image-only generators.

## Versioning (Modular Creed)

- **V0.1** (this): Local, stdlib-heavy, working end-to-end vertical slice. Real (or GIF-fallback) video render. Freemium local demo. Security from line 1.
- **V1.0**: SQLite history, better renderer (transitions, motion), optional TTS, Pro export bundles, desktop packaging.
- **V2+**: LLM script variants (with injection defenses + quotas), team features, API, billing.

## Core Modules (backend/modules)

- **models.py** — WebContent, Script, Scene, VideoAsset (dataclasses, clean to_dict/from_dict).
- **security.py** — SSRF blocks, RateLimiter (different buckets for scrape/script/render), sanitize, observability. `render_rate_limiter` is deliberately tight.
- **scraper.py** — `extract_web_content(url)` → WebContent. Stdlib fetch + regex/og-tag heuristics + image extraction. Cache + full security wrap.
- **script_generator.py** — `generate_script(content, tone, target_seconds)` → Script. Template + light heuristics. User-editable.
- **storyboard.py** — `build_storyboard(script)` → list[Scene]. Predictable timing, easy to tweak per scene.
- **renderer.py** — The money module. PIL frame generation (text overlays, cycling B-roll, gradient panels, brand bar). ffmpeg subprocess when present → real MP4 1080x1920. Otherwise high-quality GIF. Safe image downloads.

## API (thin server)

- `POST /api/extract` → {url} → WebContent
- `POST /api/script` → {web_content, tone, target_seconds} → Script
- `POST /api/render` → {script, scenes?, images?, options?} → {asset: {url: "/renders/xxx.mp4", duration, format}}
- `GET /renders/<file>` — direct video serve (with CORS)
- `GET /api/health` — also reports ffmpeg presence

All POSTs go through rate limiting + validation.

## Frontend (V0.1)

Single clean `index.html` (React via CDN + Tailwind + Babel). No legacy real-estate templates, no Canvas asset code from previous projects.

Flow:
1. URL paste + import (calls extract)
2. Review content + live script editor (tone + length controls, point editing)
3. Storyboard grid (per-scene text + duration editable)
4. Render (calls backend) → <video> player + download + local history

Usage tracking + "Pro" toggle live in localStorage for the freemium value prop.

## Security & Cost Controls (non-negotiable)

- URL validation on every path (no private nets, no metadata endpoints).
- Render is the DoW (denial of wallet) / CPU abuse vector → smallest quota in V0.1.
- Image downloads capped (size + count).
- Renders directory is the only place that grows; simple file serving with name sanitization.
- All errors and rate events logged via the security logger.

## Why a new directory?

Previous iteration was accused (correctly) of "writing social asset engine on top". The entire previous tree was real-estate listing → social post/asset code with string replacements and added sections. Per the creed (no entropy, vertical slices, honest scope), we started fresh in `webvid/` with only the actual required domain objects and pipeline.

## Ports

Backend 4819, frontend 4820 — deliberately uncommon to coexist with other dev work on the machine.

## Dependencies (V0.1)

- Python 3 stdlib only for core (urllib, PIL for frames is present in this env, imageio was tested but not required).
- ffmpeg binary recommended (one `brew install`) for MP4. Renderer degrades gracefully.

## Profit potential

Clear daily limit + instant "Pro" unlock that removes friction (watermark + count). This is the exact hook for a real paid tier later (unlimited, cloud renders, analytics, team templates, scheduling).

Built to be marketable from day one while staying 100% creed-compliant.
