"""Script Generator for WebVid.

Turns WebContent into a short, speakable, hook-driven video script.
V0.1: template + heuristics (no LLM yet to avoid prompt injection surface + cost).
Fully deterministic + editable downstream.
"""

import re
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


def generate_script(content: WebContent, tone: str = "professional", target_seconds: int = 30) -> Script:
    tone = (tone or "professional").lower()
    title = content.title or "Website"
    hook = _make_hook(title, tone)
    points = _make_points(content)
    cta = _make_cta(tone, title)

    # Build speakable full script
    full = f"{hook}.\n\n"
    for i, p in enumerate(points, 1):
        full += f"{p}. "
    full += f"\n\n{cta}"
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
    )
