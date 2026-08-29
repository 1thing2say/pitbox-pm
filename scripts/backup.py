"""Make a consistent backup of the database and the uploaded files.

    python scripts/backup.py                 # -> backups/pitbox-YYYY-MM-DD_HHMM/
    python scripts/backup.py --out D:/baja   # somewhere else (a USB stick, OneDrive)
    python scripts/backup.py --keep 20       # prune to the newest 20 backups

WHY NOT JUST COPY pitbox.db
---------------------------
The database runs in WAL mode, so recent writes live in the pitbox.db-wal
sidecar until SQLite checkpoints them. Copying pitbox.db on its own can capture
a file that is technically valid, opens without error, and is missing most of
your parts -- a backup that looks fine and is not.

sqlite3's own backup API walks the live database page by page, coordinating with
any writer, and produces one self-contained file with the WAL already folded in.
That is what this uses. It is safe to run while the app is serving.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import BASE_DIR, settings  # noqa: E402


def db_path_from_url(url: str) -> Path | None:
    """Only SQLite is backed up here; Postgres has its own pg_dump story."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url[len(prefix) :]
    path = Path(raw)
    return path if path.is_absolute() else (BASE_DIR / raw).resolve()


def human(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(BASE_DIR / "backups"), help="destination folder")
    parser.add_argument("--keep", type=int, default=0, help="keep only the newest N backups")
    args = parser.parse_args()

    source = db_path_from_url(settings.database_url)
    if source is None:
        print(f"Database is not SQLite ({settings.database_url}).")
        print("Use pg_dump instead -- see docs/HOSTING.md.")
        return 2
    if not source.exists():
        print(f"No database at {source}. Nothing to back up.")
        return 1

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    dest = Path(args.out) / f"pitbox-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)

    # --- database, via the online backup API (WAL-safe, no downtime) ---------
    target = dest / "pitbox.db"
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()

    # Prove the copy is readable and actually has the rows, rather than
    # assuming. A backup nobody has opened is a rumour.
    check = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            print("!! integrity_check FAILED on the backup -- do not trust it.")
            return 1
        counts = {
            table: check.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("projects", "nodes", "tags", "node_tags", "attachments", "members")
        }
    finally:
        check.close()

    print(f"database  {human(target.stat().st_size)}  ->  {target}")
    print("          " + "  ".join(f"{k}={v}" for k, v in counts.items()))

    # --- uploaded files ------------------------------------------------------
    blobs = settings.storage_dir
    if blobs.exists():
        files_dest = dest / "storage"
        shutil.copytree(blobs, files_dest, dirs_exist_ok=True)
        total = sum(f.stat().st_size for f in files_dest.rglob("*") if f.is_file())
        count = sum(1 for f in files_dest.rglob("*") if f.is_file())
        print(f"files     {count} files, {human(total)}  ->  {files_dest}")
    else:
        print("files     (no storage/ directory yet)")

    # --- retention -----------------------------------------------------------
    if args.keep > 0:
        existing = sorted(
            (p for p in Path(args.out).glob("pitbox-*") if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for old in existing[args.keep :]:
            shutil.rmtree(old, ignore_errors=True)
            print(f"pruned    {old.name}")

    print(f"\nOK. Restore by stopping the app and copying these back over the originals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
