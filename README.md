# Product Label Data Extractor

Upload a photo with many product labels → get a table of **Article Name, Size, MRP** (CSV / Excel).

## Setup
```bash
python -m venv venv
venv\Scripts\activate        # Windows  (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env       # Mac/Linux: cp .env.example .env
```
Get a free API key from https://aistudio.google.com/apikey and put it in `.env`.

## Run
```bash
streamlit run app.py
```

## Tips for better accuracy
- Take the photo straight-on, in good light, labels in focus.
- Very crowded images (40+ labels): split into 2–4 photos and process each.
- Always review rows marked "Not Detected" in the editable table.

## Structure
- `app.py` – Streamlit UI
- `extractor.py` – Gemini vision call + structured JSON output
- `utils.py` – image checks, cleaning, CSV/Excel export

## Notes
- Free tier has rate limits; if you hit one, wait a minute.
- If the model name stops working, change `GEMINI_MODEL` in `.env`.
