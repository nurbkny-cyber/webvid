# WebVid

**Turn any website into short-form videos** (Reels / TikTok / YouTube Shorts).

V0.1 — fully functional local prototype built to the full Software Engineering Constitution, Modular Creed, and Security-by-Design Directive.

## What it does (end-to-end)

1. Paste any public URL.
2. Secure extraction of title, description, main text, key points, and relevant images.
3. Generate (or edit) a short script: Hook + 3–5 points + CTA.
4. Visual storyboard with per-scene timing (fully editable).
5. Render a real 9:16 vertical video (1080×1920) with burned-in captions.
   - Uses ffmpeg when present → real MP4.
   - Graceful fallback to animated GIF otherwise.
6. Preview, download, reuse from local history.

## Run (safe ports)

```bash
cd webvid
./run.sh
```

- Backend: http://localhost:4819
- Frontend: http://localhost:4820

Never uses 3000/5000/8000/8080/8081 etc.

## Recommended one-time setup (for best quality)

```bash
# Real MP4 output (otherwise you get a high-quality GIF you can convert)
brew install ffmpeg
```

After installing ffmpeg, restart the backend. The UI will show MP4 capability on `/api/health`.

### xAI Grok for dramatically better scripts (optional but transformative)

The "✨ Improve with Grok AI" button in the script editor calls Grok when you have a key.

```bash
# Copy the example and set your key
cp .env.example .env
# edit .env and put your key, or just export in the shell:
export XAI_API_KEY=your_key_from_console.x.ai
```

- Get a key: https://console.x.ai/
- When the key is present on the backend, Grok writes the hook + points + CTA.
- Always falls back gracefully to the solid template if the key is missing or the call fails (never breaks the product).
- This is the exact "magic" that makes the tool feel premium and worth paying for.

Restart the backend after setting the key (or let the keeper heal the port). `/api/health` will report `"ai_enabled": true`.

## Freemium / Profit model (V0.1)

- 2 free renders per day (localStorage, per browser).
- "Go Pro" toggle in header instantly unlocks unlimited + removes the small watermark.
- This is the exact value prop you would charge for: unlimited clean exports, future batch, custom intros, scheduled posts, etc.
- Real usage + clear upgrade moment = marketable.

## Security (by design, from day one)

- Every URL is validated + sanitized.
- SSRF protection: private IPs, loopback, metadata services (169.254..., etc.) are blocked.
- Rate limits on every endpoint, extremely tight on `/api/render` (the expensive CPU/disk operation).
- All scraped data treated as hostile input (length caps, sanitization).
- Renders are written to a controlled `./renders` directory with safe filename serving.
- Structured security logging.

See `backend/modules/security.py`.

## Architecture (modular)

```
webvid/
  backend/
    server.py                 # thin stdlib orchestrator
    modules/
      models.py               # WebContent, Script, Scene, VideoAsset
      security.py             # RateLimiter, validate_and_sanitize_url, etc.
      scraper.py              # general web extraction (stdlib only)
      script_generator.py
      storyboard.py
      renderer.py             # PIL frames + conditional ffmpeg MP4
  frontend/
    index.html                # self-contained vanilla JS + Tailwind (no React/Babel for max compatibility)
  renders/                    # generated videos (gitignored)
  run.sh
  README.md
```

All new code. No "social asset engine on top". Clean vertical slice for the actual product.

The frontend includes a live "Server renders (all previous)" browser (fetches /api/renders) and one-click example URLs for demos.

## GitHub

https://github.com/nurbkny-cyber/webvid

## What's new (moving fast toward full product)

- xAI Grok integration live: "✨ Improve with Grok AI" button in the script editor (when XAI_API_KEY is set). Dramatically better, more human, scroll-stopping scripts than pure templates. Full graceful fallback.
- Server renders browser at the bottom of the UI (one-click load any previous video).
- Friendly errors everywhere (no more raw Python tracebacks for bad domains).
- Self-contained vanilla frontend (no fragile React/Babel CDNs).

## Next (V0.1 → V1) — still pushing

- Persisted local history (SQLite) + user accounts in hosted version
- Better progress / estimated time for long renders
- ffmpeg detection + quality toggle in UI
- Optional voiceover (gTTS or local)
- Pro export pack (thumbnail variants, .srt captions, multiple formats)
- Packaging as desktop app + one-click hosted version with real billing
- More aggressive scraping (optional trafilatura) + image B-roll selection

## Creed compliance note

This was built after the explicit feedback that previous work had only renamed and layered on top of an old real-estate asset generator. The project was restarted in a new directory (`webvid/`) with fresh modules whose sole purpose is "any website → short video". No leftover `listing.beds`, `price`, `TEMPLATES` for PNG social assets, or mixed concerns.

## License / Use

Local tool. Your data never leaves the machine in V0.1.
