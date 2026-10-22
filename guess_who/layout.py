"""Setzt Karten in exakter Größe (mm) auf A4-Seiten und erzeugt ein druckfertiges PDF."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageOps
from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PAGE_W_MM, PAGE_H_MM = 210, 297
CROP_MARK_MM = 4  # Länge der Schnittmarken im Seitenrand


@dataclass
class Card:
    image: Image.Image
    name: str = ""


@dataclass
class LayoutSettings:
    card_w_mm: float
    card_h_mm: float
    margin_mm: float = 8
    gap_mm: float = 0
    dpi: int = 300
    crop_marks: bool = True
    outline: bool = True
    show_names: bool = False
    name_band_mm: float = 6


def grid(s: LayoutSettings) -> tuple[int, int]:
    """Anzahl Spalten und Zeilen, die auf eine A4-Seite passen."""
    usable_w = PAGE_W_MM - 2 * s.margin_mm
    usable_h = PAGE_H_MM - 2 * s.margin_mm
    cols = math.floor((usable_w + s.gap_mm) / (s.card_w_mm + s.gap_mm))
    rows = math.floor((usable_h + s.gap_mm) / (s.card_h_mm + s.gap_mm))
    return max(cols, 0), max(rows, 0)


def fit_to_card(img: Image.Image, s: LayoutSettings) -> Image.Image:
    """Schneidet das Bild auf das Seitenverhältnis der Karte zu und skaliert auf die Druckauflösung."""
    px_w = round(s.card_w_mm / 25.4 * s.dpi)
    px_h = round(s.card_h_mm / 25.4 * s.dpi)
    # leicht nach oben versetzt zuschneiden, damit der Kopf nicht abgeschnitten wird
    return ImageOps.fit(img.convert("RGB"), (px_w, px_h), Image.LANCZOS, centering=(0.5, 0.4))


def build_pdf(cards: list[Card], s: LayoutSettings) -> bytes:
    cols, rows = grid(s)
    if cols == 0 or rows == 0:
        raise ValueError("Die Karte ist mit diesem Rand zu groß für eine A4-Seite.")
    per_page = cols * rows

    # Raster auf der Seite zentrieren
    grid_w = cols * s.card_w_mm + (cols - 1) * s.gap_mm
    grid_h = rows * s.card_h_mm + (rows - 1) * s.gap_mm
    x0 = (PAGE_W_MM - grid_w) / 2
    y_top = PAGE_H_MM - (PAGE_H_MM - grid_h) / 2

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Guess Who Karten")

    for page_start in range(0, len(cards), per_page):
        page_cards = cards[page_start : page_start + per_page]
        used_rows = math.ceil(len(page_cards) / cols)

        for i, card in enumerate(page_cards):
            col, row = i % cols, i // cols
            x = x0 + col * (s.card_w_mm + s.gap_mm)
            y = y_top - (row + 1) * s.card_h_mm - row * s.gap_mm
            _draw_card(c, card, x, y, s)

        if s.crop_marks:
            _draw_crop_marks(c, s, cols, used_rows, x0, y_top)
        bottom = y_top - used_rows * s.card_h_mm - (used_rows - 1) * s.gap_mm
        _draw_footer(c, s, bottom)
        c.showPage()

    c.save()
    return buf.getvalue()


def _draw_card(c: canvas.Canvas, card: Card, x: float, y: float, s: LayoutSettings) -> None:
    img = fit_to_card(card.image, s)
    c.drawImage(ImageReader(img), x * mm, y * mm, s.card_w_mm * mm, s.card_h_mm * mm)

    if s.show_names and card.name:
        band = min(s.name_band_mm, s.card_h_mm / 3)
        c.saveState()
        c.setFillColor(Color(1, 1, 1, alpha=0.85))
        c.rect(x * mm, y * mm, s.card_w_mm * mm, band * mm, stroke=0, fill=1)
        c.setFillColor(black)
        font_size = band * mm * 0.6
        while c.stringWidth(card.name, "Helvetica-Bold", font_size) > (s.card_w_mm - 2) * mm and font_size > 4:
            font_size -= 0.5
        c.setFont("Helvetica-Bold", font_size)
        c.drawCentredString((x + s.card_w_mm / 2) * mm, y * mm + (band * mm - font_size * 0.7) / 2, card.name)
        c.restoreState()

    if s.outline:
        c.saveState()
        c.setStrokeColor(Color(0.6, 0.6, 0.6))
        c.setLineWidth(0.25)
        c.rect(x * mm, y * mm, s.card_w_mm * mm, s.card_h_mm * mm, stroke=1, fill=0)
        c.restoreState()


def _draw_crop_marks(c: canvas.Canvas, s: LayoutSettings, cols: int, rows: int, x0: float, y_top: float) -> None:
    """Schnittmarken im Seitenrand an jeder Kartenkante – dort, wo nicht gedruckt wird."""
    xs = sorted({x0 + i * (s.card_w_mm + s.gap_mm) for i in range(cols)}
                | {x0 + i * (s.card_w_mm + s.gap_mm) + s.card_w_mm for i in range(cols)})
    ys = sorted({y_top - i * (s.card_h_mm + s.gap_mm) for i in range(rows)}
                | {y_top - i * (s.card_h_mm + s.gap_mm) - s.card_h_mm for i in range(rows)})
    left, right = x0, x0 + cols * s.card_w_mm + (cols - 1) * s.gap_mm
    top, bottom = y_top, y_top - rows * s.card_h_mm - (rows - 1) * s.gap_mm
    gap = 1  # Abstand der Marke zur Karte

    c.saveState()
    c.setLineWidth(0.3)
    c.setStrokeColor(black)
    for x in xs:
        c.line(x * mm, (top + gap) * mm, x * mm, (top + gap + CROP_MARK_MM) * mm)
        c.line(x * mm, (bottom - gap) * mm, x * mm, (bottom - gap - CROP_MARK_MM) * mm)
    for y in ys:
        c.line((left - gap) * mm, y * mm, (left - gap - CROP_MARK_MM) * mm, y * mm)
        c.line((right + gap) * mm, y * mm, (right + gap + CROP_MARK_MM) * mm, y * mm)
    c.restoreState()


def _draw_footer(c: canvas.Canvas, s: LayoutSettings, bottom: float) -> None:
    """Hinweis und 50-mm-Messbalken zum Prüfen der Druckgröße (nur wenn unter den Karten Platz ist)."""
    free = bottom - (1 + CROP_MARK_MM if s.crop_marks else 0)
    if free < 6:
        return
    y = max(4.0, free / 2)
    c.saveState()
    c.setLineWidth(0.4)
    c.line(10 * mm, y * mm, 60 * mm, y * mm)
    for tick in (10, 60):
        c.line(tick * mm, (y - 1) * mm, tick * mm, (y + 1) * mm)
    c.setFont("Helvetica", 6)
    c.drawString(62 * mm, (y - 0.7) * mm,
                 f"= 50 mm  |  Karte {s.card_w_mm:g} × {s.card_h_mm:g} mm  |  "
                 "Drucken mit 100 % / „Tatsächliche Größe“, NICHT „An Seite anpassen“")
    c.restoreState()
