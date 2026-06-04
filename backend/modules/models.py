"""Data models for WebVid.

Domain: WebContent extracted from any public website, turned into short video scripts + rendered MP4 assets.
Per Modular Creed + Security-by-Design: explicit, validated, minimal.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class WebContent:
    """General website content suitable for short video generation."""
    url: str = ""
    title: str = ""
    description: str = ""
    main_text: str = ""
    key_points: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "main_text": self.main_text,
            "key_points": self.key_points,
            "images": self.images,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            main_text=data.get("main_text", ""),
            key_points=data.get("key_points", []) or [],
            images=data.get("images", []) or [],
            meta=data.get("meta", {}) or {},
        )


@dataclass
class Script:
    """Short video script (15-60s target). Editable by user."""
    hook: str
    points: List[str]
    cta: str
    full_text: str
    target_seconds: int = 30
    platform_hints: List[str] = field(default_factory=lambda: ["reels", "tiktok", "shorts"])
    source: str = "template"  # "template" | "grok" — lets UI show "AI improved" badge

    def to_dict(self) -> dict:
        return {
            "hook": self.hook,
            "points": self.points,
            "cta": self.cta,
            "full_text": self.full_text,
            "target_seconds": self.target_seconds,
            "platform_hints": self.platform_hints,
            "source": getattr(self, "source", "template"),
        }


@dataclass
class Scene:
    """One timed scene in the storyboard."""
    index: int
    text: str
    duration: float  # seconds
    visual: str  # hint: "image:0", "title", "bullet", "cta", "broll"


@dataclass
class VideoAsset:
    """Result of a render."""
    id: str
    path: str  # relative to renders/
    duration: float
    width: int = 1080
    height: int = 1920
    format: str = "mp4"
    has_watermark: bool = True
    created_at: str = ""
