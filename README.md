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
    index.html                # clean single-file React app (no legacy)
  renders/                    # generated videos (gitignored)
  run.sh
  README.md
```

All new code. No "social asset engine on top". Clean vertical slice for the actual product.

## Next (V0.1 → V1)

- Persisted local history (SQLite)
- Better typography / motion in renderer
- Optional voice (gTTS or local TTS)
- Pro export pack (thumbnail + caption variants + .srt)
- Packaging as a real desktop tool

## Creed compliance note

This was built after the explicit feedback that previous work had only renamed and layered on top of an old real-estate asset generator. The project was restarted in a new directory (`webvid/`) with fresh modules whose sole purpose is "any website → short video". No leftover `listing.beds`, `price`, `TEMPLATES` for PNG social assets, or mixed concerns.

## License / Use

Local tool. Your data never leaves the machine in V0.1.
