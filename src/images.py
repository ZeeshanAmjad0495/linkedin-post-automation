"""Image generation: branded title cards (free, Pillow) and AI illustrations.

IMAGE_MODE controls behavior:
  - "card": always render a branded title card (zero cost, no extra API).
  - "ai":   always generate an AI illustration (needs OPENAI_API_KEY, small cost).
  - "mix":  alternate per run between card and AI (default).

If AI generation is requested but unavailable/fails, we fall back to a branded
card so a run never aborts for lack of an image.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .config import Config
from .content import PostContent

log = logging.getLogger("bot.images")

CARD_W, CARD_H = 1200, 630

# Brand palette (deep navy -> teal accent). Tweak freely.
BG_TOP = (10, 22, 40)        # #0A1628
BG_BOTTOM = (12, 38, 64)     # #0C2640
ACCENT = (34, 211, 238)      # cyan-400
ACCENT_2 = (59, 130, 246)    # blue-500
TEXT = (238, 244, 250)
MUTED = (148, 170, 194)

FONT_BOLD_CANDIDATES = [
    os.getenv("FONT_BOLD_PATH"),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]
FONT_REG_CANDIDATES = [
    os.getenv("FONT_REGULAR_PATH"),
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
]


@dataclass
class GeneratedImage:
    path: str
    mode: str  # "card" or "ai"


def _load_font(size: int, bold: bool) -> ImageFont.FreeTypeFont:
    for path in FONT_BOLD_CANDIDATES if bold else FONT_REG_CANDIDATES:
        if not path:
            continue
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ValueError):
            continue
    log.warning("No TrueType font found; falling back to PIL default (low quality).")
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _gradient(w: int, h: int, top, bottom) -> Image.Image:
    base = Image.new("RGB", (w, h), top)
    draw = ImageDraw.Draw(base)
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)
    return base


def make_branded_card(content: PostContent, cfg: Config, out_path: str) -> str:
    img = _gradient(CARD_W, CARD_H, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    # Subtle dotted grid motif (top-right region) for a technical feel.
    for gx in range(CARD_W - 360, CARD_W - 40, 26):
        for gy in range(40, 240, 26):
            draw.ellipse([gx, gy, gx + 3, gy + 3], fill=(40, 64, 92))

    margin = 80
    # Left accent bar.
    draw.rounded_rectangle([margin - 28, 150, margin - 16, 470], radius=6, fill=ACCENT)

    # Theme pill (top-left).
    pill_font = _load_font(26, bold=True)
    label = content.theme.upper()
    pad_x, pad_y = 22, 12
    tw = draw.textlength(label, font=pill_font)
    draw.rounded_rectangle(
        [margin, 70, margin + tw + pad_x * 2, 70 + 32 + pad_y],
        radius=20,
        fill=(22, 48, 78),
        outline=ACCENT,
        width=2,
    )
    draw.text((margin + pad_x, 70 + pad_y - 2), label, font=pill_font, fill=ACCENT)

    # Title (large, bold, wrapped).
    title_font = _load_font(72, bold=True)
    max_w = CARD_W - margin * 2
    title_lines = _wrap(draw, content.card_title, title_font, max_w)[:4]
    y = 190
    for line in title_lines:
        draw.text((margin, y), line, font=title_font, fill=TEXT)
        y += 84

    # Subtitle (muted).
    if content.card_subtitle:
        sub_font = _load_font(34, bold=False)
        for line in _wrap(draw, content.card_subtitle, sub_font, max_w)[:2]:
            draw.text((margin, y + 8), line, font=sub_font, fill=MUTED)
            y += 44

    # Footer: brand name / handle.
    foot_font = _load_font(28, bold=True)
    footer = " · ".join([p for p in (cfg.brand_name, cfg.brand_handle) if p]) or "Technical Notes"
    draw.line([(margin, CARD_H - 92), (CARD_W - margin, CARD_H - 92)], fill=(40, 64, 92), width=2)
    draw.ellipse([margin, CARD_H - 70, margin + 18, CARD_H - 52], fill=ACCENT_2)
    draw.text((margin + 30, CARD_H - 74), footer, font=foot_font, fill=TEXT)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "PNG")
    log.info("Rendered branded card -> %s", out_path)
    return out_path


def make_ai_image(content: PostContent, cfg: Config, out_path: str) -> str:
    """Generate an AI illustration via OpenAI Images. Raises on failure."""
    if cfg.image_provider != "openai":
        raise RuntimeError(f"Unsupported IMAGE_PROVIDER '{cfg.image_provider}' (only 'openai' is built in).")
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not set for AI image generation.")

    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai_api_key)
    prompt = (
        content.image_prompt
        or f"A clean, modern, professional editorial tech illustration about {content.theme}. "
        "Flat vector style, cool blue/teal palette, no text, no logos."
    )
    size = "1792x1024" if "dall-e-3" in cfg.openai_image_model else "1536x1024"

    resp = client.images.generate(model=cfg.openai_image_model, prompt=prompt, size=size, n=1)
    item = resp.data[0]

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if getattr(item, "b64_json", None):
        with open(out_path, "wb") as fh:
            fh.write(base64.b64decode(item.b64_json))
    elif getattr(item, "url", None):
        import requests

        r = requests.get(item.url, timeout=60)
        r.raise_for_status()
        with open(out_path, "wb") as fh:
            fh.write(r.content)
    else:
        raise RuntimeError("OpenAI image response contained neither b64_json nor url.")

    log.info("Generated AI image -> %s", out_path)
    return out_path


def generate_image(cfg: Config, content: PostContent, image_counter: int, out_dir: str) -> GeneratedImage:
    """Pick and produce an image according to IMAGE_MODE, with safe fallback."""
    mode = cfg.image_mode
    if mode == "mix":
        want_ai = (image_counter % 2 == 1)  # alternate; cards on even, AI on odd
    elif mode == "ai":
        want_ai = True
    else:
        want_ai = False  # "card" or anything unknown

    if want_ai and cfg.wants_ai_images and cfg.openai_api_key:
        ai_path = os.path.join(out_dir, "post_ai.png")
        try:
            make_ai_image(content, cfg, ai_path)
            return GeneratedImage(path=ai_path, mode="ai")
        except Exception as exc:  # noqa: BLE001 - never let an image failure abort the post
            log.warning("AI image failed (%s); falling back to branded card.", exc)

    card_path = os.path.join(out_dir, "post_card.png")
    make_branded_card(content, cfg, card_path)
    return GeneratedImage(path=card_path, mode="card")
