"""
Peppers File Classifier

Scans all files (not subfolders) in a Drive folder, classifies each by Hebrew
keyword matching on the filename, then either prints a dry-run table or moves
files to the correct category folder (with auto-created YYYY/YYYY-MM structure).

Usage:
    python peppers_file_classifier.py <folder_id>            # dry run
    python peppers_file_classifier.py <folder_id> --execute  # move files
"""
import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ── Paths ─────────────────────────────────────────────────────────────────────
AGENT_DIR        = Path(__file__).parent.parent / "agents" / "invoice_agent"
CREDENTIALS_FILE = AGENT_DIR / "credentials.json"
TOKEN_FILE       = AGENT_DIR / "token.json"
DRY_RUN_CSV      = Path(__file__).parent / "classifier_dry_run.csv"
EXECUTE_LOG_CSV  = Path(__file__).parent / "classifier_execute_log.csv"

SCOPES         = ["https://www.googleapis.com/auth/drive"]
REQUIRED_SCOPE = "https://www.googleapis.com/auth/drive"

# ── Category → real Drive folder IDs ──────────────────────────────────────────
FOLDER_MAP = {
    "CATEGORY_01": "1BSywGji_x1PxkGi7pSphp_cZNQFlOx5h",  # 01_חשבוניות_ורכש
    "CATEGORY_02": "1sgZ_IPSgL6vSepr40YmEynQzSswPrvql",   # 02_מכירות_וקופה
    "CATEGORY_03": "1d37diufTkSTYkgZgL65G94E98UIUK0Ge",   # 03_בנקים
    "CATEGORY_04": "1DkwGnWuQ0_SJ4HhQHwR5fw_8NXENSrcL",   # 04_רואה_חשבון
    "CATEGORY_05": "1fqXxKM5BhO3W7-c9y0czVgzebwjg-0cN",   # 05_מבצעים_ושילוט
    "CATEGORY_06": "1aKpMTGSFwEtTJ1gVDN0F2sxbymVfugP3",   # 06_מועדון_לקוחות
    "CATEGORY_07": "1BvgX1DaNmJg1Ci7JInUmWeG6FigbAz0S",   # 07_עובדים
    "CATEGORY_08": "1hwHn_Hy6u7In9XIhFo3bXUriwFR6HJpT",   # 08_קטלוג_ומוצרים
    "CATEGORY_09": "162cBENaK9eCYmT_ODFLs_nVK71ptM4zm",   # 09_סוכנים_וקוד
    "CATEGORY_10": "1taSfTIjvyoScR5B3pAOjXgOVpB7304ba",   # 10_דשבורדים
}

# ── Classification rules (first match wins) ────────────────────────────────────
RULES = [
    ("CATEGORY_02", "02_מכירות_וקופה",    ['דוח Z', 'מכירות', 'הכנסות']),
    ("CATEGORY_01", "01_חשבוניות_ורכש",   ['רכש', 'חשבונית', 'ספק']),
    ("CATEGORY_03", "03_בנקים",           ['בנק', 'עו"ש', 'הלוואה']),
    ("CATEGORY_04", "04_רואה_חשבון",      ['רו"ח', 'רווח והפסד', 'מאזן']),
    ("CATEGORY_05", "05_מבצעים_ושילוט",   ['מבצע', 'שלט']),
    ("CATEGORY_06", "06_מועדון_לקוחות",   ['מועדון', 'לקוח', 'נקודות']),
    ("CATEGORY_07", "07_עובדים",          ['משכורת', 'עובד', 'שכר']),
    ("CATEGORY_08", "08_קטלוג_ומוצרים",   ['מלאי', 'ברקוד', 'מוצר', 'קטלוג', 'שווי']),
    ("CATEGORY_09", "09_סוכנים_וקוד",     ['.py', '.gs', '.js', 'סוכן', 'agent']),
    ("CATEGORY_10", "10_דשבורדים",        ['דשבורד', 'dashboard']),
]

DATE_RE = re.compile(r'(\d{4})[_\-](\d{2})')

# ── Auth ──────────────────────────────────────────────────────────────────────
def get_credentials() -> Credentials:
    creds = None

    if TOKEN_FILE.exists():
        import json as _json
        stored = set(_json.loads(TOKEN_FILE.read_text()).get("scopes", []))
        if REQUIRED_SCOPE not in stored:
            print("Token has insufficient scope — re-authenticating …")
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

    return creds

# ── Drive helpers ─────────────────────────────────────────────────────────────
def get_folder_name(service, folder_id: str) -> str:
    try:
        meta = service.files().get(
            fileId=folder_id, fields="name", supportsAllDrives=True,
        ).execute()
        return meta.get("name", folder_id)
    except Exception:
        return folder_id


def list_files(service, folder_id: str) -> list[dict]:
    results, page_token = [], None
    while True:
        resp = service.files().list(
            q=(
                f"'{folder_id}' in parents"
                " and mimeType != 'application/vnd.google-apps.folder'"
                " and trashed = false"
            ),
            fields="nextPageToken, files(id, name, parents)",
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


def get_ancestor_ids(service, folder_id: str) -> set[str]:
    """Walk up the parent chain and return all ancestor IDs including folder_id."""
    ids = {folder_id}
    current = folder_id
    for _ in range(12):
        try:
            meta = service.files().get(
                fileId=current, fields="parents", supportsAllDrives=True,
            ).execute()
            parents = meta.get("parents", [])
            if not parents:
                break
            current = parents[0]
            ids.add(current)
        except Exception:
            break
    return ids


def find_or_create_folder(service, parent_id: str, name: str) -> str:
    """Return ID of a named subfolder under parent_id, creating it if absent."""
    resp = service.files().list(
        q=(
            f"'{parent_id}' in parents"
            f" and name = '{name}'"
            " and mimeType = 'application/vnd.google-apps.folder'"
            " and trashed = false"
        ),
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    existing = resp.get("files", [])
    if existing:
        return existing[0]["id"]
    folder = service.files().create(
        body={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return folder["id"]


def resolve_target_folder(service, category: str, year_month: str) -> str:
    """Return the Drive folder ID to move a file into, creating subfolders as needed."""
    root_id = FOLDER_MAP[category]
    if not year_month:
        return root_id
    year = year_month[:4]
    year_id = find_or_create_folder(service, root_id, year)
    return find_or_create_folder(service, year_id, year_month)


def move_file(service, file_id: str, old_parents: list[str], new_parent_id: str) -> None:
    service.files().update(
        fileId=file_id,
        addParents=new_parent_id,
        removeParents=",".join(old_parents),
        fields="id, parents",
        supportsAllDrives=True,
    ).execute()

# ── Classification ────────────────────────────────────────────────────────────
def classify(filename: str) -> tuple[str, str]:
    lower = filename.lower()
    for category, dest_root, keywords in RULES:
        for kw in keywords:
            if kw.lower() in lower:
                return category, dest_root
    return "UNCLASSIFIED", ""


def extract_date(filename: str) -> str:
    m = DATE_RE.search(filename)
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def build_dest_path(dest_root: str, year_month: str) -> str:
    if not dest_root:
        return "— unclassified —"
    if year_month:
        return f"{dest_root}/{year_month[:4]}/{year_month}/"
    return f"{dest_root}/"

# ── Console output ────────────────────────────────────────────────────────────
def _safe(s: str) -> str:
    return s.encode(sys.stdout.encoding or "utf-8", "replace").decode(sys.stdout.encoding or "utf-8")


def print_table(rows: list[dict]) -> None:
    cols = ["FILENAME", "CURRENT FOLDER", "CATEGORY", "ACTION", "SUGGESTED DESTINATION"]
    widths = [
        max(len(cols[0]), max(len(_safe(r["filename"])[:55]) for r in rows)),
        max(len(cols[1]), max(len(_safe(r["current_folder"])) for r in rows)),
        max(len(cols[2]), max(len(r["category"]) for r in rows)),
        max(len(cols[3]), max(len(r["action"]) for r in rows)),
        max(len(cols[4]), max(len(r["destination"]) for r in rows)),
    ]

    def fmt(*cells):
        return "  ".join(f"{c:<{w}}" for c, w in zip(cells, widths))

    print("  " + fmt(*cols))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + fmt(
            _safe(r["filename"])[:55],
            _safe(r["current_folder"]),
            r["category"],
            r["action"],
            r["destination"],
        ))

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder_id", help="Drive folder ID to scan")
    parser.add_argument("--execute", action="store_true", help="Move files (default: dry run)")
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"Authenticating … [{mode}]")
    creds   = get_credentials()
    service = build("drive", "v3", credentials=creds)

    folder_name     = get_folder_name(service, args.folder_id)
    source_ancestors = get_ancestor_ids(service, args.folder_id)
    print(f"Scanning: {folder_name} ({args.folder_id})\n")

    files = list_files(service, args.folder_id)
    if not files:
        print("No files found.")
        sys.exit(0)
    print(f"Found {len(files)} file(s).\n")

    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []

    for f in files:
        fname      = f["name"]
        parents    = f.get("parents", [args.folder_id])
        category, dest_root = classify(fname)
        year_month = extract_date(fname)

        if category == "UNCLASSIFIED":
            action      = "UNCLASSIFIED"
            destination = "— unclassified —"
            result      = "skipped"

        elif FOLDER_MAP[category] in source_ancestors:
            action      = "SKIP"
            destination = build_dest_path(dest_root, year_month) + " (already here)"
            result      = "skipped"

        else:
            action      = "MOVE"
            destination = build_dest_path(dest_root, year_month)
            result      = "pending"

            if args.execute:
                try:
                    target_id = resolve_target_folder(service, category, year_month)
                    move_file(service, f["id"], parents, target_id)
                    result = "moved"
                except Exception as exc:
                    result = f"ERROR: {exc}"
                    sys.stderr.write(f"  ERR {_safe(fname)}: {exc}\n")

        rows.append({
            "timestamp":      ts,
            "file_id":        f["id"],
            "filename":       fname,
            "current_folder": folder_name,
            "category":       category,
            "year_month":     year_month,
            "action":         action,
            "destination":    destination,
            "result":         result,
        })

    print_table(rows)

    # Save CSV
    csv_path   = EXECUTE_LOG_CSV if args.execute else DRY_RUN_CSV
    fieldnames = ["timestamp", "file_id", "filename", "current_folder",
                  "category", "year_month", "action", "destination", "result"]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    moved        = sum(1 for r in rows if r["result"] == "moved")
    skipped      = sum(1 for r in rows if r["action"] in ("SKIP", "UNCLASSIFIED"))
    to_move      = sum(1 for r in rows if r["action"] == "MOVE")
    errors       = sum(1 for r in rows if r["result"].startswith("ERROR"))

    print()
    if args.execute:
        print(f"Moved: {moved}  |  Skipped: {skipped}  |  Errors: {errors}  |  Total: {len(rows)}")
    else:
        print(f"Would move: {to_move}  |  Skip: {skipped}  |  Total: {len(rows)}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
