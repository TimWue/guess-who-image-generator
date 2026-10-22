# Guess Who – Kartengenerator

Macht aus Fotos über die OpenAI Images API Cartoon-Porträts und setzt sie in exakter Größe (mm) auf A4-Seiten (PDF).

## Start

```bash
cp .env.example .env      # OPENAI_API_KEY eintragen (oder Key in der App eingeben)
uv sync
uv run streamlit run app.py
```

## Ablauf

1. In der Seitenleiste Kartenbreite und -höhe in mm, Seitenrand, Abstand und Exemplare pro Person festlegen.
2. Fotos hochladen (JPG, PNG, WEBP, HEIC, …), Namen bei Bedarf anpassen.
3. „Cartoons erzeugen“ klicken. Ergebnisse landen in `cache/`, damit sie nicht doppelt bezahlt werden.
   Gefällt ein Bild nicht, „Neu erzeugen“ klicken.
4. PDF herunterladen und mit **100 % / „Tatsächliche Größe“** drucken. Zum Nachmessen ist unten auf der Seite ein 50-mm-Balken.

## Dateien

- `guess_who/cartoon.py`: OpenAI-Aufruf, Prompt, Cache
- `guess_who/layout.py`: Zuschnitt aufs Kartenformat (300 dpi) und PDF-Layout mit Schnittmarken
- `app.py`: Streamlit-Oberfläche
