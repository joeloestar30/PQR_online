import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modules.db import get_db, init_db
from modules.imports import import_data_sheet_csv


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_sheet_csv.py path\\to\\data.csv [REGION]")
        raise SystemExit(2)
    init_db()
    csv_path = sys.argv[1]
    region = sys.argv[2] if len(sys.argv) > 2 else "NL"
    conn = get_db()
    imported, skipped = import_data_sheet_csv(conn, csv_path, region)
    conn.commit()
    conn.close()
    print(f"Imported: {imported}")
    print(f"Skipped: {skipped}")


if __name__ == "__main__":
    main()
