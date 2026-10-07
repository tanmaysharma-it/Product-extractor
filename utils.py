"""Image preparation, data cleaning and export helpers."""
import io
import re

import pandas as pd
from PIL import Image, UnidentifiedImageError

NOT_DETECTED = "Not Detected"
COLUMNS = ["Article Name", "Size", "MRP"]
MAX_SIDE = 3000  # keep enough resolution so small label text stays readable


def prepare_image(file_bytes: bytes) -> tuple[bytes, str, Image.Image]:
    """Validate the upload, fix rotation, downscale if huge. Returns (jpeg_bytes, mime, PIL image)."""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
        img = Image.open(io.BytesIO(file_bytes))  # reopen after verify()
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("Invalid or corrupted image file.") from e

    from PIL import ImageOps
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), "image/jpeg", img


def clean_mrp(value) -> str:
    """'Rs. 1,299.50/-' -> '1299.50'. Returns 'Not Detected' if no number found."""
    if value is None:
        return NOT_DETECTED
    text = str(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return NOT_DETECTED
    return f"{float(match.group()):.2f}"


def clean_text(value) -> str:
    if value is None:
        return NOT_DETECTED
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "unknown", "not detected"}:
        return NOT_DETECTED
    return text


def records_to_dataframe(records: list[dict]) -> pd.DataFrame:
    """Validate/clean raw extractor output. Skips malformed items, keeps duplicates."""
    rows = []
    for item in records or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "Article Name": clean_text(item.get("article_name")),
            "Size": clean_text(item.get("size")),
            "MRP": clean_mrp(item.get("mrp")),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def _size_key(size: str):
    try:
        return (0, float(size), "")
    except (TypeError, ValueError):
        return (1, 0.0, str(size))


def group_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Rows with the same Article Name + MRP become one row: sizes combined, Pairs = count.
    Rows where Article or MRP is 'Not Detected' are never merged. First-appearance order is kept."""
    out_cols = ["Article Name", "Sizes", "MRP", "Pairs"]
    groups: dict = {}   # (article, mrp) -> list of sizes
    order: list = []    # keeps first-appearance order; unmergeable rows get a unique key
    for i, row in enumerate(df.itertuples(index=False)):
        article, size, mrp = row[0], row[1], row[2]
        if NOT_DETECTED in (article, mrp):
            key = ("__single__", i)
        else:
            key = (article, mrp)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(size)

    rows = []
    for key in order:
        sizes = groups[key]
        counts: dict = {}
        for s in sizes:
            counts[s] = counts.get(s, 0) + 1
        sizes_text = ", ".join(
            f"{s} (x{c})" if c > 1 else str(s)
            for s, c in sorted(counts.items(), key=lambda kv: _size_key(kv[0]))
        )
        if key[0] == "__single__":
            article, mrp = df.iloc[key[1]]["Article Name"], df.iloc[key[1]]["MRP"]
        else:
            article, mrp = key
        rows.append({"Article Name": article, "Sizes": sizes_text, "MRP": mrp, "Pairs": len(sizes)})
    return pd.DataFrame(rows, columns=out_cols)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")  # utf-8-sig so Excel opens it correctly


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    out = df.copy()
    # Store MRP as a real number in Excel where possible
    out["MRP"] = out["MRP"].apply(
        lambda v: float(v) if re.fullmatch(r"\d+(?:\.\d+)?", str(v).strip()) else v
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        out.to_excel(writer, index=False, sheet_name="Products")
        ws = writer.sheets["Products"]
        for col, width in zip("ABCD", (30, 25, 12, 10)):
            ws.column_dimensions[col].width = width
    return buf.getvalue()