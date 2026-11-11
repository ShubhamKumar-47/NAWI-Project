"""
scripts/backup_database.py — Automated Database Backup Utility.
Supports automated PostgreSQL (pg_dump) and SQLite snapshot backups with gzip compression.
"""
import os
import sys
import subprocess
import datetime
import shutil
import gzip
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")


def backup_database():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_url = env("DATABASE_URL", default=f"sqlite:///{BASE_DIR}/db.sqlite3")

    if db_url.startswith("postgres://") or db_url.startswith("postgresql://"):
        print(f"[{timestamp}] Initiating PostgreSQL backup from DATABASE_URL...")
        backup_file = backup_dir / f"nawi_db_backup_{timestamp}.sql.gz"

        try:
            # Use pg_dump with DATABASE_URL
            dump_cmd = ["pg_dump", db_url, "--no-owner", "--no-acl", "--clean"]
            with gzip.open(backup_file, "wb") as f_out:
                proc = subprocess.run(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                f_out.write(proc.stdout)
            print(f"[{timestamp}] Successfully created compressed backup: {backup_file}")
            print(f"File size: {backup_file.stat().st_size / 1024:.2f} KB")
        except FileNotFoundError:
            print("[Warning] 'pg_dump' utility not found on PATH. Ensure postgresql-client is installed.")
        except subprocess.CalledProcessError as exc:
            print(f"[Error] pg_dump failed: {exc.stderr.decode('utf-8', errors='replace')}")
    else:
        # SQLite backup
        sqlite_path = BASE_DIR / "db.sqlite3"
        if sqlite_path.exists():
            backup_file = backup_dir / f"nawi_sqlite_backup_{timestamp}.sqlite3.gz"
            with open(sqlite_path, "rb") as f_in, gzip.open(backup_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            print(f"[{timestamp}] Successfully created compressed SQLite backup: {backup_file}")
            print(f"File size: {backup_file.stat().st_size / 1024:.2f} KB")
        else:
            print(f"[Warning] SQLite database file not found at {sqlite_path}")


if __name__ == "__main__":
    backup_database()

