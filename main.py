"""
main.py  -  Clinic Stock-Out Database (SDG 3)
Builds clinic_stock.db, loads the CSVs, then prints:
  1. clinics that are stocked out or will be within 14 days
  2. what to reorder
  3. where stock can be shared between nearby clinics before ordering more
  4. a demo of the trigger blocking an impossible dispense

Run:  python generate_sample_data.py  then  python main.py
"""

import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "clinic_stock.db"


def load(conn, table, columns):
    """Insert data/<table>.csv into the table (only the listed columns)."""
    with open(ROOT / "data" / f"{table}.csv", newline="", encoding="utf-8") as f:
        rows = [[r[c] for c in columns] for r in csv.DictReader(f)]     # keep columns in the given order
    marks = ", ".join("?" * len(columns))                               # "?, ?, ?" ("?" * 3 = "???", join adds commas)
    conn.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marks})", rows)
    return len(rows)


def show(conn, title, sql):
    """Run a query and print it as an aligned table."""
    cur = conn.execute(sql)
    headers = [d[0] for d in cur.description]                           # column names
    rows = [["" if v is None else str(v) for v in r] for r in cur.fetchall()]
    print(f"\n=== {title} ===")
    if not rows:
        print("(none)")
        return
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    for r in rows:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)))


def main():
    if not (ROOT / "data" / "stock_movements.csv").exists():
        sys.exit("No data yet. Run: python generate_sample_data.py")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        load(conn, "clinics", ["clinic_id", "name", "lga"])
        load(conn, "medicines", ["medicine_id", "name", "unit"])
        n = load(conn, "stock_movements", ["clinic_id", "medicine_id", "moved_on", "kind", "quantity"])
        print(f"Loaded {n} stock movements (the trigger checked every dispense)")

        show(conn, "1. Stocked out or running out within 14 days",
             """SELECT clinic, medicine, on_hand, avg_daily_use, days_left, status
                FROM stock_status
                WHERE status IN ('STOCKED OUT', 'CRITICAL')
                ORDER BY status DESC, days_left""")
        show(conn, "2. Reorder list (60 days of stock)",
             """SELECT clinic, medicine, unit, on_hand, reorder_qty
                FROM stock_status WHERE reorder_qty > 0
                ORDER BY clinic, reorder_qty DESC""")
        show(conn, "3. Share before you buy: transfers within the same LGA",
             "SELECT * FROM redistribution_options")
        show(conn, "4. Status count per clinic",
             """SELECT clinic,
                       SUM(status = 'STOCKED OUT') AS stocked_out,   -- a comparison is 1 or 0 in SQLite, so SUM counts matches
                       SUM(status = 'CRITICAL')    AS critical,
                       SUM(status = 'LOW')         AS low,
                       SUM(status = 'OK')          AS ok
                FROM stock_status GROUP BY clinic ORDER BY stocked_out DESC, critical DESC""")

        print("\n=== 5. Trigger demo: try to dispense 1,000,000 ORS sachets ===")
        try:
            conn.execute("""INSERT INTO stock_movements (clinic_id, medicine_id, moved_on, kind, quantity)
                            VALUES (1, 1, (SELECT MAX(moved_on) FROM stock_movements), 'dispense', 1000000)""")
            print("Inserted?! (this should not happen)")
        except sqlite3.IntegrityError as err:                           # RAISE(ABORT) arrives as IntegrityError
            print(f"Blocked by the database: {err}")
    print(f"\nDatabase saved to {DB_PATH.name}")


if __name__ == "__main__":
    main()
