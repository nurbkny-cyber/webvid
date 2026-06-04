"""Video Renderer for WebVid.

Core value delivery: turn script + extracted images into a real short vertical video.
- 1080x1920 (9:16)
- Burned-in captions per scene
- Uses page images as B-roll where possible (safely fetched)
- PIL for frame compositing (text, bg, simple effects)
- ffmpeg (subprocess) if present on PATH -> true MP4
- Fallback: animated GIF (still useful + easy to convert)

Security: images downloaded with timeout/size caps, no exec of remote content.
Cost control: frame count limited, quality reasonable for V0.1.
"""

import os
import time
import uuid
import tempfile
import subprocess
import shutil
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import urllib.request
import urllib.error

from .models import Script, Scene, VideoAsset
from .security import is_ffmpeg_available, security_logger

RENDERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "renders")
os.makedirs(RENDERS_DIR, exist_ok=True)

WIDTH, HEIGHT = 1080, 1920
FPS = 30
MAX_IMAGES = 4
MAX_DOWNLOAD_BYTES = 2_000_000  # 2MB per image safety


def _download_image(url: str, dest: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WebVid/0.1"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            cl = resp.headers.get("Content-Length")
            if cl and int(cl) > MAX_DOWNLOAD_BYTES:
                return False
            data = resp.read(MAX_DOWNLOAD_BYTES)
            with open(dest, "wb") as f:
                f.write(data)
        return True
    except Exception as e:
        security_logger.warning(f"image download fail {url[:60]}: {e}")
        return False


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    # Try system fonts that look good on macOS
    candidates = [
        "/System/Library/Fonts/SF-Pro-Display-Bold.otf" if bold else "/System/Library/Fonts/SF-Pro-Display-Regular.otf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    words = text.split()
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines or [text]


def _make_frame(bg_img: Optional[Image.Image], text: str, sub: str, is_last: bool) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), (15, 15, 30))
    draw = ImageDraw.Draw(img)

    # Background
    if bg_img:
        try:
            bg = bg_img.resize((WIDTH, int(HEIGHT * 0.58)), Image.LANCZOS)
            img.paste(bg, (0, 0))
            # dark gradient overlay bottom
            overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            for y in range(int(HEIGHT * 0.42), HEIGHT):
                alpha = int(220 * ((y - HEIGHT * 0.42) / (HEIGHT * 0.58)))
                ov_draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, min(255, alpha)))
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(img)
        except Exception:
            pass

    # Bottom panel
    draw.rectangle([(0, int(HEIGHT * 0.42)), (WIDTH, HEIGHT)], fill=(12, 12, 22))

    # Title / main text
    title_font = _get_font(68, bold=True)
    body_font = _get_font(42)
    sub_font = _get_font(32)

    y = int(HEIGHT * 0.48)
    lines = _wrap_text(text, title_font, WIDTH - 120, draw)
    for line in lines[:4]:  # cap
        draw.text((60, y), line, font=title_font, fill=(255, 255, 255))
        y += 78

    if sub:
        y += 20
        for line in _wrap_text(sub, body_font, WIDTH - 120, draw)[:3]:
            draw.text((60, y), line, font=body_font, fill=(200, 205, 220))
            y += 52

    # CTA hint on last
    if is_last:
        draw.text((60, HEIGHT - 160), "Link in bio  •  Save this", font=sub_font, fill=(160, 170, 200))

    # Subtle brand bar
    draw.rectangle([(0, HEIGHT - 8), (WIDTH, HEIGHT)], fill=(59, 108, 245))

    return img


def _frames_to_gif(frames: List[Image.Image], out_path: str, duration_ms: int = 120):
    if not frames:
        return
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )


def _frames_to_mp4(frames_dir: str, out_path: str, fps: int = FPS) -> bool:
    """Use ffmpeg if available to turn frame_%04d.png sequence into MP4."""
    if not is_ffmpeg_available():
        return False
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2",
        "-movflags", "+faststart",
        "-preset", "medium",
        "-crf", "23",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 1000
    except Exception as e:
        security_logger.warning(f"ffmpeg render failed: {e}")
        return False


def render_video(script: Script, scenes: List[Scene], images: List[str], options: Optional[dict] = None) -> VideoAsset:
    """
    Main render entrypoint.
    Returns VideoAsset with path (relative filename) that server can serve from /renders/.
    """
    options = options or {}
    vid_id = uuid.uuid4().hex[:12]
    base = f"webvid_{vid_id}"
    mp4_path = os.path.join(RENDERS_DIR, f"{base}.mp4")
    gif_path = os.path.join(RENDERS_DIR, f"{base}.gif")

    # Prepare B-roll images (download up to MAX_IMAGES safely)
    bg_images: List[Optional[Image.Image]] = [None] * len(scenes)
    tmp_dir = tempfile.mkdtemp(prefix="webvid_img_")
    try:
        dl_imgs = []
        for i, u in enumerate(images[:MAX_IMAGES]):
            p = os.path.join(tmp_dir, f"bg_{i}.jpg")
            if _download_image(u, p):
                try:
                    dl_imgs.append(Image.open(p).convert("RGB"))
                except Exception:
                    pass
        # Assign cycling
        for i in range(len(scenes)):
            if dl_imgs:
                bg_images[i] = dl_imgs[i % len(dl_imgs)]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Generate frames
    frames: List[Image.Image] = []
    total_dur = sum(s.duration for s in scenes)
    for si, scene in enumerate(scenes):
        # number of frames for this scene
        n_frames = max(1, int(round(scene.duration * FPS)))
        bg = bg_images[si]
        sub = ""
        if "bullet" in scene.visual:
            sub = "Key takeaway"
        elif scene.visual == "cta":
            sub = "Full details on site"

        for fi in range(n_frames):
            # slight zoom on bg for motion
            frame = _make_frame(bg, scene.text, sub, scene.visual == "cta")
            frames.append(frame)

    if not frames:
        # emergency single frame
        frames = [_make_frame(None, script.hook, "", False)]

    # Try real MP4 first
    used_mp4 = False
    if is_ffmpeg_available():
        # write frames to temp seq
        seq_dir = tempfile.mkdtemp(prefix="webvid_seq_")
        try:
            for idx, fr in enumerate(frames):
                fr.save(os.path.join(seq_dir, f"frame_{idx:04d}.png"))
            if _frames_to_mp4(seq_dir, mp4_path, FPS):
                used_mp4 = True
                final_path = mp4_path
                fmt = "mp4"
        finally:
            shutil.rmtree(seq_dir, ignore_errors=True)

    if not used_mp4:
        # GIF fallback (always works with PIL)
        try:
            _frames_to_gif(frames, gif_path, duration_ms=int(1000 / FPS))
            final_path = gif_path
            fmt = "gif"
            security_logger.info("Rendered as GIF fallback (ffmpeg not present or failed)")
        except Exception as eg:
            security_logger.error(f"GIF fallback also failed: {eg}")
            # last resort: create a single frame GIF
            f0 = frames[0] if frames else _make_frame(None, script.hook or "WebVid", "", False)
            f0.save(gif_path, duration=800, loop=0)
            final_path = gif_path
            fmt = "gif"

    asset = VideoAsset(
        id=vid_id,
        path=os.path.basename(final_path),
        duration=round(total_dur, 1),
        width=WIDTH,
        height=HEIGHT,
        format=fmt,
        has_watermark=True,  # V0.1 free tier
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    security_logger.info(f"Render complete: {asset.path} ({asset.duration}s, {fmt})")
    return asset
