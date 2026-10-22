"""Erzeugt Cartoon-Bilder aus Fotos über die OpenAI Images API (mit Cache auf der Festplatte)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path

from openai import OpenAI
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()  # HEIC/HEIF (iPhone-Fotos) öffnen können

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"

DEFAULT_PROMPT = (
    "Turn this photo into a cartoon portrait for a card of the board game 'Guess Who?'. "
    "Style: friendly, colorful cartoon illustration with clean bold outlines and flat cel shading, "
    "like the classic Guess Who character portraits. "
    "Keep the person clearly recognizable: preserve face shape, hairstyle, hair color, facial hair, "
    "glasses, skin tone, eye color and distinctive accessories. "
    "Show head and shoulders, facing the viewer, centered horizontally, with a little space above the head. "
    "Transparent background: only the person, no scenery, no shadow on the background. "
    "No text, no letters, no frame, no border."
)

# Modelle, die nur feste Größen kennen; alle anderen (gpt-image-2 ff.) können beliebige Größen
FIXED_SIZE_MODELS = {"gpt-image-1", "gpt-image-1.5", "gpt-image-1-mini", "chatgpt-image-latest"}
FIXED_SIZES = [(1024, 1024), (1024, 1536), (1536, 1024)]


def load_photo(data: bytes) -> Image.Image:
    """Öffnet ein Foto in beliebigem Format und dreht es gemäß EXIF richtig herum."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def has_transparency(png: bytes) -> bool:
    img = Image.open(io.BytesIO(png))
    return img.mode in ("RGBA", "LA") and img.getchannel("A").getextrema()[0] < 255


def with_background(png: bytes, color: str) -> Image.Image:
    """Legt das freigestellte Cartoon auf eine einfarbige Fläche. Die Figur selbst bleibt unverändert."""
    fg = Image.open(io.BytesIO(png)).convert("RGBA")
    bg = Image.new("RGBA", fg.size, color)
    return Image.alpha_composite(bg, fg).convert("RGB")


def api_size(model: str, width_mm: float, height_mm: float) -> str:
    """Wählt die Ausgabegröße für die API passend zum Seitenverhältnis der Karte."""
    ratio = width_mm / height_mm
    if model in FIXED_SIZE_MODELS:
        w, h = min(FIXED_SIZES, key=lambda s: abs(s[0] / s[1] - ratio))
        return f"{w}x{h}"
    # Freie Größe: lange Kante 1536 px, beide Kanten durch 16 teilbar, Verhältnis max. 1:3
    ratio = max(1 / 3, min(3, ratio))
    if ratio >= 1:
        w, h = 1536, 1536 / ratio
    else:
        w, h = 1536 * ratio, 1536
    return f"{round(w / 16) * 16}x{round(h / 16) * 16}"


def generate_cartoon(
    client: OpenAI,
    photo: bytes,
    *,
    prompt: str,
    model: str,
    size: str,
    quality: str = "high",
    variant: int = 0,
) -> bytes:
    """Gibt das Cartoon als PNG-Bytes zurück. Gleiche Eingaben werden aus dem Cache bedient."""
    key = hashlib.sha256(
        photo + json.dumps([prompt, model, size, quality, variant, "transparent"]).encode()
    ).hexdigest()[:32]
    cached = CACHE_DIR / f"{key}.png"
    if cached.exists():
        return cached.read_bytes()

    img = load_photo(photo)
    img.thumbnail((2048, 2048))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    kwargs = {}
    if model in ("gpt-image-1", "gpt-image-1.5"):
        kwargs["input_fidelity"] = "high"  # Gesichtszüge möglichst genau übernehmen

    result = client.images.edit(
        model=model,
        image=("photo.png", buf.getvalue(), "image/png"),
        prompt=prompt,
        size=size,
        quality=quality,
        background="transparent",  # Hintergrundfarben werden danach lokal eingesetzt
        output_format="png",
        **kwargs,
    )
    png = base64.b64decode(result.data[0].b64_json)

    CACHE_DIR.mkdir(exist_ok=True)
    cached.write_bytes(png)
    return png
