"""Storyboard builder for WebVid.

Script -> list of timed Scenes for the renderer.
V0.1 keeps it simple and predictable so users can edit script and re-render reliably.
"""

from .models import Script, Scene


def build_storyboard(script: Script, style: str = "clean") -> list[Scene]:
    """Return ordered scenes with durations that sum ~ target_seconds."""
    target = script.target_seconds or 30
    scenes: list[Scene] = []

    # Scene 0: hook (strong visual, 4-7s)
    hook_dur = max(4.0, min(7.0, target * 0.2))
    scenes.append(Scene(index=0, text=script.hook, duration=hook_dur, visual="title"))

    # Points
    n_points = len(script.points)
    if n_points == 0:
        n_points = 1
    remaining = target - hook_dur - 5.0  # reserve for cta
    per_point = max(3.5, remaining / max(1, n_points))

    for i, pt in enumerate(script.points[:5]):
        d = min(9.0, max(3.0, per_point))
        scenes.append(Scene(index=i + 1, text=pt, duration=d, visual=f"bullet:{i}"))

    # CTA / close
    cta_dur = max(4.0, min(6.0, target * 0.18))
    scenes.append(Scene(index=99, text=script.cta, duration=cta_dur, visual="cta"))

    # Normalize total to target
    total = sum(s.duration for s in scenes)
    if total > 0:
        scale = target / total
        for s in scenes:
            s.duration = max(2.5, round(s.duration * scale, 1))

    return scenes
