"""
Peppers Invoice Namer

Uses Google Vision API OCR to read invoice PDFs in a Drive folder, extracts
date / supplier / invoice-number from the text, then renames the file in Drive.

Usage:
    python peppers_invoice_namer.py <folder_id>               # dry run
    python peppers_invoice_namer.py <folder_id> --execute     # rename files
    python peppers_invoice_namer.py <folder_id> --limit 10    # show N rows
"""
import argparse
import base64
import csv
import io
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests as http_requests
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ── Paths ─────────────────────────────────────────────────────────────────────
AGENT_DIR        = Path(__file__).parent.parent / "agents" / "invoice_agent"
CREDENTIALS_FILE = AGENT_DIR / "credentials.json"
TOKEN_FILE       = AGENT_DIR / "token.json"
DRY_RUN_CSV      = Path(__file__).parent / "invoice_namer_dry_run.csv"
EXECUTE_LOG_CSV  = Path(__file__).parent / "invoice_namer_log.csv"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/cloud-platform",
]

# Vision API: files:annotate handles inline PDF with page selection
VISION_URL   = "https://vision.googleapis.com/v1/files:annotate"
MAX_PDF_MB   = 8
MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024

ALREADY_NAMED_RE = re.compile(r'^\d{4}-\d{2}-\d{2}_')

# ── Auth ──────────────────────────────────────────────────────────────────────
def get_credentials() -> Credentials:
    creds = None
    if TOKEN_FILE.exists():
        # Check raw stored scopes (creds.scopes reflects passed SCOPES, not issued scopes)
        import json as _json
        stored = set(_json.loads(TOKEN_FILE.read_text()).get("scopes", []))
        missing = set(SCOPES) - stored
        if missing:
            print(f"Token missing scopes {missing} — re-authenticating …")
            TOKEN_FILE.unlink()
        else:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    # Ensure the bearer token is populated
    if not creds.token:
        creds.refresh(Request())

    return creds

# ── Drive helpers ─────────────────────────────────────────────────────────────
def get_folder_name(service, folder_id: str) -> str:
    try:
        return service.files().get(
            fileId=folder_id, fields="name", supportsAllDrives=True,
        ).execute().get("name", folder_id)
    except Exception:
        return folder_id


def list_pdf_files(service, folder_id: str) -> list[dict]:
    results, page_token = [], None
    while True:
        resp = service.files().list(
            q=(
                f"'{folder_id}' in parents"
                " and mimeType = 'application/pdf'"
                " and trashed = false"
            ),
            fields="nextPageToken, files(id, name, size)",
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def download_pdf(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def rename_file(service, file_id: str, new_name: str) -> None:
    service.files().update(
        fileId=file_id,
        body={"name": new_name},
        fields="id, name",
        supportsAllDrives=True,
    ).execute()

# ── Vision OCR ────────────────────────────────────────────────────────────────
def ocr_pdf(access_token: str, pdf_bytes: bytes, max_pages: int = 3) -> str:
    """Send PDF bytes to Vision API files:annotate and return combined OCR text."""
    payload = {
        "requests": [{
            "inputConfig": {
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
                "mimeType": "application/pdf",
            },
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "pages": list(range(1, max_pages + 1)),
        }]
    }
    resp = http_requests.post(
        VISION_URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    texts = []
    for top in data.get("responses", []):
        for page_resp in top.get("responses", []):
            text = page_resp.get("fullTextAnnotation", {}).get("text", "")
            if text:
                texts.append(text)
    return "\n".join(texts)

# ── Field extraction ──────────────────────────────────────────────────────────
_DATE_RE = [
    # DD/MM/YYYY  or  DD-MM-YYYY  or  DD.MM.YYYY
    (re.compile(r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b'), "dmy"),
    # YYYY-MM-DD  or  YYYY/MM/DD
    (re.compile(r'\b(\d{4})[/\-](\d{2})[/\-](\d{2})\b'),          "ymd"),
    # DD/MM/YY
    (re.compile(r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2})\b'), "dmy_short"),
]

_INV_RE = [
    re.compile(r'(?:חשבונית\s*(?:מס[\'״]?|מספר|מ\.?)\s*[:\-]?\s*)([A-Za-z0-9\-]{2,})', re.IGNORECASE),
    re.compile(r'(?:מס[\'״]\s*[:\-]?\s*)([A-Za-z0-9\-]{2,20})',                          re.IGNORECASE),
    re.compile(r'(?:מספר\s+חשבוני(?:ת|ות)\s*[:\-]?\s*)([A-Za-z0-9\-]{2,})',              re.IGNORECASE),
    re.compile(r'(?:invoice\s*(?:no\.?|#|number)?\s*[:\-]?\s*)([A-Za-z0-9\-]{2,})',      re.IGNORECASE),
    re.compile(r'(?:\bno\.\s*)([A-Za-z0-9\-]{3,})',                                        re.IGNORECASE),
    re.compile(r'\b(INV[-\s]?[A-Za-z0-9]{2,})\b',                                         re.IGNORECASE),
]

_NOISE_RE = re.compile(
    r'(?:חשבונית|invoice|total|סה"כ|מע"מ|תאריך|date|לקוח|customer|טלפון|phone|פקס|fax)',
    re.IGNORECASE,
)


def extract_date(text: str) -> str:
    for pattern, fmt in _DATE_RE:
        m = pattern.search(text)
        if not m:
            continue
        g = m.groups()
        try:
            if fmt == "ymd":
                y, mo, d = int(g[0]), int(g[1]), int(g[2])
            elif fmt == "dmy_short":
                d, mo = int(g[0]), int(g[1])
                y = 2000 + int(g[2])
            else:
                d, mo, y = int(g[0]), int(g[1]), int(g[2])
            if 1 <= mo <= 12 and 1 <= d <= 31 and 2000 <= y <= 2100:
                return f"{y:04d}-{mo:02d}-{d:02d}"
        except ValueError:
            continue
    return "UNKNOWN"


def extract_invoice_num(text: str) -> str:
    for pattern in _INV_RE:
        m = pattern.search(text)
        if m:
            val = m.group(1).strip().rstrip('.,;')
            if len(val) >= 2:
                return val
    return "UNKNOWN"


def extract_supplier(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:10]:
        # Must contain at least 2 real letters (Hebrew or Latin)
        if not re.search(r'[א-תa-zA-Z]{2,}', line):
            continue
        # Skip pure-date or pure-number lines
        if re.match(r'^[\d/\-\.\s:,]+$', line):
            continue
        # Skip obvious label/header lines
        if _NOISE_RE.search(line):
            continue
        return line
    return lines[0] if lines else "UNKNOWN"


def clean_supplier(s: str) -> str:
    if not s or s == "UNKNOWN":
        return "UNKNOWN"
    s = s.strip()[:25]
    s = re.sub(r'\s+', '_', s)
    # Keep Unicode letters (Hebrew included), digits, underscore, hyphen
    s = ''.join(c for c in s if c.isalpha() or c.isdigit() or c in ('_', '-'))
    return s[:20] or "UNKNOWN"


def build_filename(date: str, supplier: str, inv_num: str) -> str:
    sup  = clean_supplier(supplier)
    inv  = re.sub(r'[^\w\-]', '', inv_num)[:20] if inv_num != "UNKNOWN" else "UNKNOWN"
    return f"{date}_{sup}_{inv}.pdf"

# ── Console output ────────────────────────────────────────────────────────────
def _safe(s: str) -> str:
    enc = sys.stdout.encoding or "utf-8"
    return s.encode(enc, "replace").decode(enc)


def print_table(rows: list[dict], limit: int | None = None) -> None:
    display = rows[:limit] if limit else rows
    if not display:
        return

    cols = ["ORIGINAL FILENAME", "DATE", "SUPPLIER", "INV#", "NEW FILENAME", "ACTION"]
    widths = [
        max(len(cols[0]), max(len(_safe(r["original"])[:45])  for r in display)),
        max(len(cols[1]), max(len(r["date"])                   for r in display)),
        max(len(cols[2]), max(len(_safe(r["supplier"])[:20])   for r in display)),
        max(len(cols[3]), max(len(_safe(r["inv_num"])[:15])    for r in display)),
        max(len(cols[4]), max(len(_safe(r["new_name"])[:45])   for r in display)),
        max(len(cols[5]), max(len(r["action"])                 for r in display)),
    ]

    def fmt(*cells):
        return "  ".join(f"{str(c):<{w}}" for c, w in zip(cells, widths))

    print("\n  " + fmt(*cols))
    print("  " + "  ".join("-" * w for w in widths))
    for r in display:
        print("  " + fmt(
            _safe(r["original"])[:45],
            r["date"],
            _safe(r["supplier"])[:20],
            _safe(r["inv_num"])[:15],
            _safe(r["new_name"])[:45],
            r["action"],
        ))
    if limit and len(rows) > limit:
        print(f"\n  … {len(rows) - limit} more rows (full output in CSV)")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder_id")
    parser.add_argument("--execute", action="store_true", help="Rename files in Drive")
    parser.add_argument("--limit",   type=int, default=None, help="Show only N rows in table")
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"Authenticating … [{mode}]")
    creds   = get_credentials()
    service = build("drive", "v3", credentials=creds)

    folder_name = get_folder_name(service, args.folder_id)
    print(f"Scanning: {folder_name} ({args.folder_id})\n")

    pdf_files = list_pdf_files(service, args.folder_id)
    print(f"Found {len(pdf_files)} PDF(s).\n")
    if not pdf_files:
        sys.exit(0)

    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []

    for i, f in enumerate(pdf_files, 1):
        fid   = f["id"]
        fname = f["name"]
        fsize = int(f.get("size", 0))

        prefix = f"  [{i:>3}/{len(pdf_files)}] {_safe(fname)[:55]}"
        print(f"{prefix} …", end=" ", flush=True)

        # ── Already named ──────────────────────────────────────────────────
        if ALREADY_NAMED_RE.match(fname):
            print("SKIP")
            rows.append({
                "timestamp": ts, "file_id": fid, "original": fname,
                "date": "", "supplier": "", "inv_num": "",
                "new_name": fname, "action": "SKIP", "result": "already named",
            })
            continue

        # ── Too large ──────────────────────────────────────────────────────
        if fsize > MAX_PDF_BYTES:
            print(f"SKIP (>{MAX_PDF_MB}MB)")
            rows.append({
                "timestamp": ts, "file_id": fid, "original": fname,
                "date": "UNKNOWN", "supplier": "UNKNOWN", "inv_num": "UNKNOWN",
                "new_name": "UNKNOWN", "action": "ERROR",
                "result": f"file too large ({fsize // 1024 // 1024}MB)",
            })
            continue

        # ── Download → OCR → extract ───────────────────────────────────────
        try:
            pdf_bytes = download_pdf(service, fid)

            # Refresh token if near-expired before Vision call
            if not creds.valid:
                creds.refresh(Request())

            ocr_text = ocr_pdf(creds.token, pdf_bytes)
            if not ocr_text.strip():
                raise ValueError("Vision API returned empty text")

            date     = extract_date(ocr_text)
            supplier = extract_supplier(ocr_text)
            inv_num  = extract_invoice_num(ocr_text)
            new_name = build_filename(date, supplier, inv_num)

            action = "RENAME"
            result = "pending"

            if args.execute:
                rename_file(service, fid, new_name)
                result = "renamed"

            print(f"-> {_safe(new_name)[:55]}")

        except Exception as exc:
            date = supplier = inv_num = new_name = "UNKNOWN"
            action = "ERROR"
            result = str(exc)[:120]
            sys.stderr.write(f"\n  ERR {_safe(fname)}: {exc}\n")
            print("ERROR")

        rows.append({
            "timestamp": ts, "file_id": fid, "original": fname,
            "date": date, "supplier": supplier, "inv_num": inv_num,
            "new_name": new_name, "action": action, "result": result,
        })

    # ── Table + CSV ────────────────────────────────────────────────────────
    print_table(rows, limit=args.limit)

    csv_path   = EXECUTE_LOG_CSV if args.execute else DRY_RUN_CSV
    fieldnames = ["timestamp", "file_id", "original", "date", "supplier",
                  "inv_num", "new_name", "action", "result"]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    renamed   = sum(1 for r in rows if r["result"] == "renamed")
    skipped   = sum(1 for r in rows if r["action"] == "SKIP")
    to_rename = sum(1 for r in rows if r["action"] == "RENAME")
    errors    = sum(1 for r in rows if r["action"] == "ERROR")

    print()
    if args.execute:
        print(f"Renamed: {renamed}  |  Skipped: {skipped}  |  Errors: {errors}  |  Total: {len(rows)}")
    else:
        print(f"Would rename: {to_rename}  |  Skip: {skipped}  |  Errors: {errors}  |  Total: {len(rows)}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
