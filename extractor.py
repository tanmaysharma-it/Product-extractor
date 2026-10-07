"""Vision AI layer: sends the image to Gemini and returns a list of dicts."""
import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()

DEFAULT_MODEL = "gemini-3.5-flash"
RETRY_DELAYS = [3, 8]  # waits before retry 2 and 3 on the same model when the server is busy
# If the main model stays busy, these are tried in order (override with GEMINI_FALLBACK_MODELS in .env)
DEFAULT_FALLBACKS = "gemini-3.1-flash-lite,gemini-3.5-flash-lite"

PROMPT = """You are reading a photo that contains MANY product boxes / labels
(clothing, shoes, accessories).

Find EVERY individual product label visible in the image and return ONE entry per label.
Do not merge labels. Do not skip duplicates: if two labels have identical information,
return two separate entries. Go through the image systematically (e.g. top-left to bottom-right).

For each label extract ONLY:
- article_name: the article name exactly as printed
- size: the size exactly as printed
- mrp: the MRP (maximum retail price) as a number, e.g. "299.50" (no currency symbol)

Rules:
- Ignore all other text (barcodes, colour, MFG date, address, etc.).
- If a value is not clearly readable, return "Not Detected". Never guess.
- Return only JSON that matches the schema.
"""


class Product(BaseModel):
    article_name: str
    size: str
    mrp: str


class ExtractionError(Exception):
    """Raised for API/config problems with a user-friendly message."""


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ExtractionError("GEMINI_API_KEY not found. Add it to your .env file.")
    return genai.Client(api_key=api_key)


def _model_list() -> list[str]:
    main = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACKS).split(",")
    models = [main] + [m.strip() for m in fallbacks if m.strip()]
    return list(dict.fromkeys(models))  # remove duplicates, keep order


def extract_products(image_bytes: bytes, mime_type: str = "image/jpeg") -> list[dict]:
    """Return [{'article_name':..., 'size':..., 'mrp':...}, ...] for every label in the image."""
    client = _get_client()
    contents = [types.Part.from_bytes(data=image_bytes, mime_type=mime_type), PROMPT]
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        response_schema=list[Product],
    )

    response = None
    busy = False
    for model in _model_list():
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = client.models.generate_content(model=model, contents=contents, config=config)
                break
            except Exception as e:  # network, quota, bad key, busy server, etc.
                msg = str(e)
                if "503" in msg or "UNAVAILABLE" in msg:
                    busy = True
                    if attempt < len(RETRY_DELAYS):
                        time.sleep(RETRY_DELAYS[attempt])
                        continue
                    break  # this model stays busy -> try the next model
                if "404" in msg or "NOT_FOUND" in msg:
                    break  # model name not available -> try the next model
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    raise ExtractionError("Free-tier rate limit reached. Wait a minute and try again.") from e
                if "API key" in msg or "401" in msg or "403" in msg or "PERMISSION_DENIED" in msg:
                    raise ExtractionError("API key rejected. Check GEMINI_API_KEY in .env.") from e
                raise ExtractionError(f"Vision API error: {msg}") from e
        if response is not None:
            break

    if response is None:
        if busy:
            raise ExtractionError("Google's servers are busy right now. Please try again in a few minutes.")
        raise ExtractionError("None of the configured models are available. Check GEMINI_MODEL in .env.")

    return _parse(response)


def _parse(response) -> list[dict]:
    # Preferred: SDK already parsed into Product objects
    parsed = getattr(response, "parsed", None)
    if parsed:
        return [p.model_dump() if hasattr(p, "model_dump") else dict(p) for p in parsed]

    # Fallback: parse raw text, tolerate ```json fences
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.lower().startswith("json") else text
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ExtractionError("The model returned an unreadable response. Please try again.") from e

    if isinstance(data, dict):
        data = data.get("products") or data.get("items") or [data]
    return [d for d in data if isinstance(d, dict)]