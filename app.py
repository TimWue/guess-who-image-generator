"""Streamlit-App: Fotos hochladen → Cartoons erzeugen → druckfertiges A4-PDF herunterladen.

Start:  uv run streamlit run app.py
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from guess_who.cartoon import (DEFAULT_PROMPT, api_size, generate_cartoon, has_transparency, load_photo,
                               with_background)
from guess_who.layout import Card, LayoutSettings, build_pdf, fit_to_card, grid

load_dotenv()
st.set_page_config(page_title="Guess Who – Kartengenerator", layout="wide")
st.title("Guess Who – Kartengenerator")

# ---------- Einstellungen ----------
with st.sidebar:
    st.header("Kartenformat")
    col_w, col_h = st.columns(2)
    card_w = col_w.number_input("Breite (mm)", 10.0, 190.0, 24.5, 0.5)
    card_h = col_h.number_input("Höhe (mm)", 10.0, 280.0, 39.0, 0.5)

    st.header("Druckseite (A4)")
    margin = st.number_input("Seitenrand (mm)", 0.0, 40.0, 10.0, 0.5,
                             help="Die meisten Drucker können ca. 4–5 mm am Rand nicht bedrucken.")
    gap = st.number_input("Abstand zwischen Karten (mm)", 0.0, 20.0, 0.0, 0.5,
                          help="0 = Karten liegen direkt aneinander, ein Schnitt trennt zwei Karten.")
    copies = st.number_input("Exemplare pro Person und Farbe", 1, 10, 1)
    crop_marks = st.checkbox("Schnittmarken im Rand", True)
    outline = st.checkbox("Dünne Umrandung jeder Karte", True)
    show_names = st.checkbox("Namen auf die Karte drucken", True)

    st.header("Hintergrundfarben")
    st.caption("Jede Person wird einmal erzeugt und dann mit jeder Farbe hinterlegt. Die Figur bleibt identisch.")
    bg_cols = st.columns(3)
    colors = {
        "Blau": bg_cols[0].color_picker("Blau", "#2F80ED"),
        "Rot": bg_cols[1].color_picker("Rot", "#E53935"),
        "Gelb": bg_cols[2].color_picker("Gelb", "#FDD835"),
    }

    st.header("OpenAI")
    api_key = st.text_input("API-Key", value=os.getenv("OPENAI_API_KEY", ""), type="password")
    model = st.selectbox(
        "Modell",
        ["gpt-image-2.5-sunburst", "gpt-image-2.5-flare", "gpt-image-2", "gpt-image-1.5", "gpt-image-1"],
        accept_new_options=True,
        help="Eigene Modellnamen können direkt eingetippt werden.",
    )
    qualities = ["low", "medium", "high"]
    if model.startswith("gpt-image-2.5"):
        qualities += ["xhigh", "max"]
    quality = st.selectbox("Qualität", qualities, index=2)
    prompt = st.text_area("Stil-Prompt", DEFAULT_PROMPT, height=260)

settings = LayoutSettings(card_w, card_h, margin, gap, crop_marks=crop_marks,
                          outline=outline, show_names=show_names)
cols, rows = grid(settings)
if cols * rows == 0:
    st.error("Die Karte passt mit diesem Rand nicht auf eine A4-Seite.")
    st.stop()
st.caption(f"Karte {card_w:g} × {card_h:g} mm → {cols} × {rows} = **{cols * rows} Karten pro A4-Seite**")

# ---------- Fotos ----------
uploads = st.file_uploader(
    "Fotos hochladen (JPG, PNG, WEBP, HEIC, …)", accept_multiple_files=True,
    type=["jpg", "jpeg", "png", "webp", "heic", "heif", "bmp", "tif", "tiff", "gif"],
)
if not uploads:
    st.info("Lade ein oder mehrere Fotos hoch. Ein Foto pro Person, das Gesicht sollte gut zu erkennen sein.")
    st.stop()

state = st.session_state
state.setdefault("results", {})   # file_id -> PNG-Bytes
state.setdefault("variants", {})  # file_id -> Zähler für „Neu erzeugen“
size = api_size(model, card_w, card_h)


def run(file_ids: list[str]) -> None:
    if not api_key:
        st.error("Bitte einen OpenAI-API-Key eintragen (Seitenleiste oder .env).")
        return
    client = OpenAI(api_key=api_key)
    by_id = {u.file_id: u for u in uploads}
    # Worker-Threads haben keinen Zugriff auf st.session_state, daher alles vorher auslesen
    photos = {fid: by_id[fid].getvalue() for fid in file_ids}
    variants = {fid: state.variants.get(fid, 0) for fid in file_ids}
    bar = st.progress(0.0, text="Erzeuge Cartoons …")

    def job(fid: str) -> tuple[str, bytes | Exception]:
        try:
            return fid, generate_cartoon(client, photos[fid], prompt=prompt, model=model,
                                         size=size, quality=quality, variant=variants[fid])
        except Exception as e:  # Fehler pro Bild anzeigen, die anderen laufen weiter
            return fid, e

    with ThreadPoolExecutor(max_workers=4) as pool:
        for n, (fid, res) in enumerate(pool.map(job, file_ids), 1):
            if isinstance(res, Exception):
                st.error(f"{by_id[fid].name}: {res}")
            else:
                state.results[fid] = res
            bar.progress(n / len(file_ids), text=f"{n}/{len(file_ids)} fertig")
    bar.empty()


missing = [u.file_id for u in uploads if u.file_id not in state.results]
c1, c2 = st.columns([1, 3])
if c1.button(f"Cartoons erzeugen ({len(missing)} offen)", type="primary", disabled=not missing):
    run(missing)
c2.caption(f"Modell `{model}`, Bildgröße `{size}`. Bereits erzeugte Bilder werden im Ordner `cache/` "
           "gespeichert und nicht erneut berechnet.")

# ---------- Vorschau ----------
names: dict[str, str] = {}
for up in uploads:
    with st.container(border=True):
        cols_row = st.columns([2, 1.2] + [1.2] * len(colors))
        with cols_row[0]:
            names[up.file_id] = st.text_input("Name", Path(up.name).stem.replace("_", " ").title(),
                                              key=f"name_{up.file_id}")
            if up.file_id in state.results:
                if st.button("Neu erzeugen", key=f"redo_{up.file_id}"):
                    state.variants[up.file_id] = state.variants.get(up.file_id, 0) + 1
                    run([up.file_id])
                    st.rerun()
                if not has_transparency(state.results[up.file_id]):
                    st.warning("Das Modell hat keinen transparenten Hintergrund geliefert, "
                               "die Farbe ist daher nicht sichtbar. Bitte neu erzeugen oder ein anderes Modell wählen.")
        cols_row[1].image(load_photo(up.getvalue()), caption="Foto")
        if up.file_id in state.results:
            for col, (label, color) in zip(cols_row[2:], colors.items()):
                col.image(fit_to_card(with_background(state.results[up.file_id], color), settings), caption=label)
        else:
            cols_row[2].caption("noch kein Cartoon")

# ---------- PDF ----------
done = [u for u in uploads if u.file_id in state.results]
if done:
    st.divider()
    # nach Farbe sortiert, damit jede Farbe einen zusammenhängenden Satz ergibt
    cards = [Card(with_background(state.results[u.file_id], color), names[u.file_id])
             for color in colors.values() for u in done for _ in range(copies)]
    pages = -(-len(cards) // (cols * rows))
    st.subheader(f"PDF: {len(cards)} Karten auf {pages} A4-Seite(n)")
    st.download_button("PDF herunterladen", build_pdf(cards, settings), "guess-who-karten.pdf",
                       "application/pdf", type="primary")
    st.warning("Beim Drucken **„Tatsächliche Größe“ / 100 %** wählen, nicht „An Seite anpassen“. "
               "Mit dem 50-mm-Balken unten auf der Seite kannst du die Größe nachmessen.")
