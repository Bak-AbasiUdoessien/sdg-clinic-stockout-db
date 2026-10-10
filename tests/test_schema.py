"""Tests for the SQL in sql/schema.sql. Run:  python -m unittest discover tests"""

import sqlite3
from datetime import date, timedelta
import unittest
from pathlib import Path

SCHEMA = Path(__file__).parent.parent / "sql" / "schema.sql"


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")                     # fresh database for each test
        self.conn.executescript(SCHEMA.read_text())
        self.conn.executescript("""
            INSERT INTO clinics VALUES (1, 'A', 'L1'), (2, 'B', 'L1');
            INSERT INTO medicines VALUES (1, 'ORS', 'sachet');
        """)

    def move(self, clinic, day, kind, qty):
        """Helper: insert one stock movement for medicine 1."""
        self.conn.execute(
            "INSERT INTO stock_movements (clinic_id, medicine_id, moved_on, kind, quantity) VALUES (?, 1, ?, ?, ?)",
            (clinic, day, kind, qty))

    def test_trigger_blocks_overdispensing(self):
        self.move(1, "2026-01-01", "receipt", 10)
        with self.assertRaises(sqlite3.IntegrityError):              # the trigger's RAISE(ABORT)
            self.move(1, "2026-01-02", "dispense", 11)

    def test_on_hand_is_receipts_minus_outgoing(self):
        self.move(1, "2026-01-01", "receipt", 100)
        self.move(1, "2026-01-02", "dispense", 30)
        self.move(1, "2026-01-03", "expired", 5)
        on_hand = self.conn.execute("SELECT on_hand FROM stock_on_hand WHERE clinic = 'A'").fetchone()[0]
        self.assertEqual(on_hand, 65)

    def test_clinic_with_no_movements_shows_zero(self):
        row = self.conn.execute("SELECT on_hand FROM stock_on_hand WHERE clinic = 'B'").fetchone()
        self.assertEqual(row[0], 0)                                  # CROSS JOIN + COALESCE keeps it visible

    def test_status_and_redistribution(self):
        self.move(1, "2026-01-01", "receipt", 50)                    # clinic A: little stock
        self.move(2, "2026-01-01", "receipt", 5000)                  # clinic B: lots
        for d in range(2, 25):                                       # 23 days of dispensing
            self.move(1, f"2026-01-{d:02d}", "dispense", 2)          # A: 46 used, 4 left -> about 2 days left
            self.move(2, f"2026-01-{d:02d}", "dispense", 10)         # B: 230 used, 4770 left -> years of stock
        status = dict(self.conn.execute("SELECT clinic, status FROM stock_status").fetchall())
        self.assertEqual(status["B"], "OK")
        self.assertIn(status["A"], ("STOCKED OUT", "CRITICAL"))
        pairs = self.conn.execute("SELECT needs_stock, can_give FROM redistribution_options").fetchall()
        self.assertEqual(pairs, [("A", "B")])                         # B can help A

    def test_stockout_still_has_demand(self):
        self.move(1, "2025-11-10", "receipt", 90)                   # 90 used over 30 days in Nov/Dec...
        for d in range(30):
            day = (date(2025, 11, 10) + timedelta(days=d)).isoformat()
            self.move(1, day, "dispense", 3)
        self.move(2, "2026-01-31", "receipt", 1)                     # ...then nothing for ~50 days (the shelf was empty)
        row = self.conn.execute("SELECT avg_daily_use, reorder_qty FROM stock_status WHERE clinic = 'A'").fetchone()
        self.assertEqual(row[0], 1.0)                                # 90 over 90 days, not 0 from the empty last month
        self.assertEqual(row[1], 60)                                 # so it still gets reordered

    def tearDown(self):
        self.conn.close()


if __name__ == "__main__":
    unittest.main()
