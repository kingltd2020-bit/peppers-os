"""
Text extraction + Hebrew invoice field hints.

PDFs: pdfplumber first; if 150+ Hebrew letters (U+05D0–U+05EA), use text and skip Tesseract.
Otherwise: pdf2image @ 300 DPI, PIL binarize + optional x2 resize, Tesseract heb+eng --psm 6.

Images: same preprocessing + Tesseract (no pdfplumber).

Backward compatible: extract_text(file_data, filename) -> (raw_text, ocr_status).
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any

import config

log = logging.getLogger(__name__)

# Hebrew letters (final forms included through U+05EA per spec)
_HEBREW_LETTER_RE = re.compile(r"[\u05d0-\u05ea]")
_MIN_HEBREW_LETTERS = 150

_DATE_DDMMYYYY = re.compile(
    r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b",
)
# document number after חשבונית / מספר
_DOC_NUM_RE = re.compile(
    r"(?:חשבונית|מספר)\s*[:\s#\-]*(\d{3,})",
    re.IGNORECASE,
)
# total: ₪ or סה"כ or סכום then number (supports 1.234,56 / 1234.56); allow short Hebrew between label and digits
_TOTAL_RE = re.compile(
    r"(?:₪|סה\"כ|סהכ|סכום)(?:\s|[^\d₪])*?([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)",
)


# Reversed-Hebrew detection: pdfplumber sometimes extracts Hebrew PDFs in visual
# (LTR) order, leaving each word's characters reversed.  We detect this by looking
# for a handful of very common Hebrew words that are unmistakable when reversed,
# then fix every predominantly-Hebrew token in the text.
_REVERSED_HEBREW_MARKERS = [
    "תינובשח",  # חשבונית
    "ךיראת",    # תאריך
    "ןופלט",    # טלפון
    "לארשי",    # ישראל
    "ךסומ",     # מוסך
    "קית",      # תיק
]


def _is_reversed_hebrew(text: str) -> bool:
    """Return True when pdfplumber produced character-reversed Hebrew words."""
    for marker in _REVERSED_HEBREW_MARKERS:
        if marker in (text or ""):
            return True
    return False


def _normalize_hebrew_ocr(text: str) -> str:
    """
    Reverse each character-reversed Hebrew word back to logical (RTL) order.

    pdfplumber sometimes stores PDF glyph positions in visual/LTR order, so
    every Hebrew word ends up with its characters mirrored.  We flip only tokens
    that are ≥50 % Hebrew letters; non-Hebrew tokens (numbers, Latin, punctuation)
    are left untouched.
    """
    if not text:
        return text
    lines = text.splitlines()
    result: list[str] = []
    for line in lines:
        tokens = line.split()
        fixed: list[str] = []
        for tok in tokens:
            heb = len(_HEBREW_LETTER_RE.findall(tok))
            if heb >= 2 and heb >= len(tok) * 0.5:
                fixed.append(tok[::-1])
            else:
                fixed.append(tok)
        result.append(" ".join(fixed))
    return "\n".join(result)


def count_hebrew_letters(text: str) -> int:
    return len(_HEBREW_LETTER_RE.findall(text or ""))


def _parse_amount_to_float(token: str) -> float | None:
    s = (token or "").strip().replace("\u00a0", " ").replace(" ", "")
    s = s.replace("₪", "").replace("$", "").replace("€", "")
    if not s or not re.search(r"\d", s):
        return None
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")
    if last_comma > last_dot:
        # Israeli / EU: dot thousands, comma decimal
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _hebrew_word_count(line: str) -> int:
    words = line.split()
    return sum(1 for w in words if _HEBREW_LETTER_RE.search(w))


def extract_invoice_fields(text: str) -> dict[str, Any]:
    """Regex field hints for Hebrew invoices."""
    supplier_name: str | None = None
    total_amount: float | None = None
    document_date: str | None = None
    document_number: str | None = None

    if not text:
        return {
            "supplier_name": None,
            "total_amount": None,
            "document_date": None,
            "document_number": None,
        }

    # supplier_name: first line with 2–6 Hebrew words
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        hw = _hebrew_word_count(line)
        if 2 <= hw <= 6:
            supplier_name = line
            break

    m = _DATE_DDMMYYYY.search(text)
    if m:
        document_date = m.group(1)

    m = _DOC_NUM_RE.search(text)
    if m:
        document_number = m.group(1)

    best_amt: float | None = None
    for m in _TOTAL_RE.finditer(text):
        val = _parse_amount_to_float(m.group(1))
        if val is None:
            continue
        if best_amt is None or val > best_amt:
            best_amt = val
    total_amount = best_amt

    return {
        "supplier_name": supplier_name,
        "total_amount": total_amount,
        "document_date": document_date,
        "document_number": document_number,
    }


def _confidence(fields: dict[str, Any]) -> str:
    n = sum(
        1
        for k in ("supplier_name", "total_amount", "document_date", "document_number")
        if fields.get(k) is not None and fields.get(k) != ""
    )
    return "high" if n >= 3 else "low"


def _preprocess_image(img):
    from PIL import Image

    img = img.convert("L")
    img = img.point(lambda p: 255 if p > 180 else 0)
    if img.width < 1000:
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    return img


def _tesseract_ocr(img) -> str:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH
    return (
        pytesseract.image_to_string(
            img,
            lang="heb+eng",
            config="--psm 6",
        ).strip()
    )


def _pdf_text_pdfplumber(file_data: bytes) -> str:
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_data)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts).strip()


def _pdf_ocr_tesseract(file_data: bytes) -> str:
    from pdf2image import convert_from_bytes

    images = convert_from_bytes(
        file_data,
        dpi=300,
        poppler_path=config.POPPLER_PATH,
    )
    parts: list[str] = []
    for img in images:
        proc = _preprocess_image(img)
        parts.append(_tesseract_ocr(proc))
    return "\n".join(parts).strip()


def _image_ocr(file_data: bytes) -> str:
    from PIL import Image

    img = Image.open(io.BytesIO(file_data))
    proc = _preprocess_image(img)
    return _tesseract_ocr(proc)


def extract_document(file_data: bytes, filename: str) -> dict[str, Any]:
    """
    Returns:
      ocr_method: "pdfplumber" | "tesseract"
      supplier_name, total_amount, document_date, document_number
      raw_text, confidence
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        raw_text = ""
        method: str = "pdfplumber"
        try:
            raw_text = _pdf_text_pdfplumber(file_data)
            if count_hebrew_letters(raw_text) >= _MIN_HEBREW_LETTERS:
                method = "pdfplumber"
                # Fix reversed Hebrew from visual-order PDFs before classification
                if _is_reversed_hebrew(raw_text):
                    log.debug("Normalizing reversed Hebrew OCR output for %s", filename)
                    raw_text = _normalize_hebrew_ocr(raw_text)
                fields = extract_invoice_fields(raw_text)
                fields["confidence"] = _confidence(fields)
                return {
                    "ocr_method": method,
                    "supplier_name": fields["supplier_name"],
                    "total_amount": fields["total_amount"],
                    "document_date": fields["document_date"],
                    "document_number": fields["document_number"],
                    "raw_text": raw_text,
                    "confidence": fields["confidence"],
                }
        except Exception as exc:
            log.warning("PDF pdfplumber extraction failed: %s", exc)

        try:
            raw_text = _pdf_ocr_tesseract(file_data)
            method = "tesseract"
        except ImportError as exc:
            log.warning("PDF OCR unavailable: %s", exc)
            raw_text = ""
            method = "tesseract"
        except Exception as exc:
            log.error("PDF OCR failed: %s", exc)
            raw_text = ""
            method = "tesseract"

        fields = extract_invoice_fields(raw_text)
        return {
            "ocr_method": method,
            "supplier_name": fields["supplier_name"],
            "total_amount": fields["total_amount"],
            "document_date": fields["document_date"],
            "document_number": fields["document_number"],
            "raw_text": raw_text,
            "confidence": _confidence(fields),
        }

    if ext in {".jpg", ".jpeg", ".png", ".tiff", ".tif"}:
        try:
            raw_text = _image_ocr(file_data)
        except Exception as exc:
            log.error("Image OCR failed: %s", exc)
            raw_text = ""
        fields = extract_invoice_fields(raw_text)
        return {
            "ocr_method": "tesseract",
            "supplier_name": fields["supplier_name"],
            "total_amount": fields["total_amount"],
            "document_date": fields["document_date"],
            "document_number": fields["document_number"],
            "raw_text": raw_text,
            "confidence": _confidence(fields),
        }

    return {
        "ocr_method": "pdfplumber",
        "supplier_name": None,
        "total_amount": None,
        "document_date": None,
        "document_number": None,
        "raw_text": "",
        "confidence": "low",
    }


def result_from_sheet_row(row: dict[str, Any]) -> dict[str, Any]:
    """Build extract_document-shaped dict from a Documents_Master sheet/CSV row (skip OCR)."""
    raw = (row.get("raw_text_preview") or "").strip()
    sn = (row.get("supplier_name") or "").strip() or None
    dd = (row.get("document_date") or "").strip() or None
    dn = (row.get("document_number") or "").strip() or None
    at_raw = (row.get("amount_total") or "").strip()
    ta: float | None = None
    if at_raw:
        ta = _parse_amount_to_float(at_raw)
        if ta is None:
            try:
                ta = float(at_raw.replace(",", ""))
            except ValueError:
                ta = None

    fields = {
        "supplier_name": sn,
        "total_amount": ta,
        "document_date": dd,
        "document_number": dn,
    }
    return {
        "ocr_method": "pdfplumber",
        "supplier_name": sn,
        "total_amount": ta,
        "document_date": dd,
        "document_number": dn,
        "raw_text": raw,
        "confidence": _confidence(fields),
    }


def extract_text(file_data: bytes, filename: str) -> tuple[str, str]:
    """
    Backward-compatible (raw_text, ocr_status).
    ocr_status: digital | ocr | failed | skipped
    """
    ext = Path(filename).suffix.lower()
    if ext not in {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}:
        return "", "skipped"

    doc = extract_document(file_data, filename)
    raw = doc.get("raw_text") or ""
    method = doc.get("ocr_method")

    if method == "tesseract":
        status = "ocr" if raw else "failed"
    elif raw:
        status = "digital"
    else:
        status = "failed"

    return raw, status
