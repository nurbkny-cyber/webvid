"""Script Generator for WebVid.

Turns WebContent into a short, speakable, hook-driven video script.
- Template path (always available, deterministic, zero cost).
- Optional Grok (xAI) path when XAI_API_KEY / GROK_API_KEY is set in env.
  Uses the official OpenAI-compatible endpoint. Strong prompt for vertical shorts.
  Graceful fallback on any error (never breaks the flow).

Security-by-Design: prompt is constrained, output is validated JSON, key never logged,
calls are best-effort and rate-limited at the server layer.

User asked for xAI Grok support — this delivers it as a first-class (optional) upgrade.
"""

import os
import re
import json
import requests
from .models import WebContent, Script


def _make_hook(title: str, tone: str) -> str:
    t = title.strip() or "this page"
    hooks = {
        "professional": f"Key insights from {t}",
        "friendly": f"You need to see what {t} just revealed",
        "urgent": f"Stop scrolling — {t} changes everything",
        "storytelling": f"Here's the story behind {t}",
        "luxury": f"Elevate your thinking with {t}",
    }
    return hooks.get(tone, f"What {t} teaches in 60 seconds")


def _make_points(content: WebContent, max_n: int = 4) -> list[str]:
    pts = list(content.key_points or [])
    if len(pts) < 2 and content.main_text:
        # crude split
        sents = re.split(r"[\.\!\?]\s+", content.main_text)
        pts = [s.strip() for s in sents if 25 < len(s.strip()) < 160][:max_n]
    if not pts:
        pts = [content.description or content.main_text[:120] or "Important details on the page"]
    return pts[:max_n]


def _make_cta(tone: str, title: str) -> str:
    ctas = {
        "professional": "Read the full breakdown on the site. Link in bio.",
        "friendly": "Save this and share it with someone who needs it!",
        "urgent": "Don't miss out — full details on the site now.",
        "storytelling": "The rest of the story is on the page. Go see it.",
        "luxury": "Experience it yourself. Details on the site.",
    }
    return ctas.get(tone, "Full story and links on the site. Save for later.")


def _generate_with_grok(content: WebContent, tone: str, target_seconds: int) -> Script | None:
    """Call xAI Grok (OpenAI-compatible) for a high-quality vertical video script.
    Returns Script or None (caller falls back to template).
    """
    key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")
    if not key:
        return None

    # Demo mode so you can instantly see what Grok-quality scripts look like
    # without a real key yet. Set XAI_API_KEY=demo  (then restart backend or let keeper heal)
    if key.lower() == "demo":
        title = content.title or "this page"
        return Script(
            hook=f"You need to see what {title} just revealed",
            points=[
                "It turns any website into scroll-stopping short videos in seconds",
                "Hook, points, and CTA are written for Reels, TikTok, and Shorts",
                "You stay in full control — edit the script and storyboard before rendering"
            ],
            cta="Try it on your own site now. Link in bio.",
            full_text=f"You need to see what {title} just revealed. It turns any website into scroll-stopping short videos in seconds. Hook, points, and CTA are written for Reels, TikTok, and Shorts. You stay in full control — edit the script and storyboard before rendering. Try it on your own site now. Link in bio.",
            target_seconds=target_seconds,
            platform_hints=["reels", "tiktok", "youtube_shorts"],
            source="grok",
        )

    try:
        # Constrained, high-signal prompt for Reels/TikTok/Shorts style
        sys_prompt = (
            "You are a world-class short-form video scriptwriter specializing in addictive "
            "Reels, TikTok, and YouTube Shorts (15-60 seconds). You write in natural spoken language, "
            "never robotic. Every script has a scroll-stopping hook in the first 3-6 seconds, "
            "3-5 punchy spoken points, and a clear benefit-driven CTA. "
            "Always return STRICT minified JSON only, exactly this shape: "
            "{\"hook\":\"...\",\"points\":[\"...\",\"...\"],\"cta\":\"...\",\"full_text\":\"...\"} "
            "No markdown, no explanations, no extra keys."
        )

        user_prompt = f"""Website content to turn into a short vertical video:

Title: {content.title or 'this page'}
Key points from page: {content.key_points or []}
Main text (first 1800 chars): {(content.main_text or content.description or '')[:1800]}

Requirements:
- Tone: {tone}
- Target spoken length: ~{target_seconds} seconds
- Hook must be extremely clickable in the first 4 seconds.
- Points must be short, speakable sentences (not bullet lists).
- full_text should be the complete script ready to be read aloud, with natural flow and pauses marked by periods.

Return ONLY the JSON object."""

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "grok-3-mini",  # fast/cheap; users with access can change to grok-3 via env if desired
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.75,
            "max_tokens": 700
        }

        resp = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=28
        )
        resp.raise_for_status()
        data = resp.json()

        raw = data["choices"][0]["message"]["content"].strip()

        # Be robust to ```json wrappers some models add
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1].replace("json", "").strip()

        script_json = json.loads(raw)

        hook = (script_json.get("hook") or "").strip()
        points = [str(p).strip() for p in (script_json.get("points") or []) if str(p).strip()][:5]
        cta = (script_json.get("cta") or "").strip()
        full = (script_json.get("full_text") or "").strip()

        if not hook or len(points) < 1:
            return None

        if not full:
            full = f"{hook}. " + " ".join(points) + f" {cta}"

        return Script(
            hook=hook,
            points=points,
            cta=cta,
            full_text=full,
            target_seconds=target_seconds,
            platform_hints=["reels", "tiktok", "youtube_shorts"],
            source="grok",
        )
    except Exception as e:
        # Never break the user experience. Log for the operator (cost / key issues).
        try:
            from modules.security import security_logger
            security_logger.warning(f"grok generation failed (falling back to template): {type(e).__name__}")
        except Exception:
            pass
        return None


def generate_script(content: WebContent, tone: str = "professional", target_seconds: int = 30, use_ai: bool = False) -> Script:
    tone = (tone or "professional").lower()
    target = max(15, min(60, int(target_seconds or 30)))

    # Optional high-quality path (user requested xAI Grok support)
    if use_ai:
        ai = _generate_with_grok(content, tone, target)
        if ai:
            return ai
        # if it failed we silently fall through to the reliable template

    title = content.title or "Website"
    hook = _make_hook(title, tone)
    points = _make_points(content)
    cta = _make_cta(tone, title)

    # Build speakable full script
    full = f"{hook}. "
    for p in points:
        full += f"{p}. "
    full += cta
    full = re.sub(r"\s+", " ", full).strip()

    # Rough timing: ~2.5 words per sec spoken
    words = len(full.split())
    est = max(15, min(60, int(words / 2.5)))
    target = target_seconds or est

    return Script(
        hook=hook,
        points=points,
        cta=cta,
        full_text=full,
        target_seconds=target,
        platform_hints=["reels", "tiktok", "youtube_shorts"],
        source="template",
    )
