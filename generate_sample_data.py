"""
generate_sample_data.py
Simulates 120 days of SYNTHETIC deliveries and dispensing for 6 made-up clinics.
The simulation keeps a running stock count so it never dispenses more than exists
(the database trigger would reject that). NOT real data.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "data"
random.seed(21)                                          # reproducible

CLINICS = [("Clinic A", "LGA North"), ("Clinic B", "LGA North"), ("Clinic C", "LGA North"),
           ("Clinic D", "LGA South"), ("Clinic E", "LGA South"), ("Clinic F", "LGA South")]
# (medicine, unit, typical daily use) - daily use numbers are invented
MEDICINES = [("ORS sachet", "sachet", 12), ("Zinc 20mg", "tablet", 20),
             ("Amoxicillin 250mg", "capsule", 30), ("Artemether-lumefantrine", "pack", 6),
             ("Paracetamol 500mg", "tablet", 40), ("Iron-folic acid", "tablet", 25)]
DAYS = 120
START = date(2026, 6, 1)


def main():
    DATA.mkdir(exist_ok=True)
    with open(DATA / "clinics.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clinic_id", "name", "lga"])
        w.writerows((i, n, l) for i, (n, l) in enumerate(CLINICS, start=1))    # generator expression, ids from 1
    with open(DATA / "medicines.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["medicine_id", "name", "unit"])
        w.writerows((i, n, u) for i, (n, u, _use) in enumerate(MEDICINES, start=1))

    moves = []                                                    # every movement, in date order
    for cid in range(1, len(CLINICS) + 1):
        for mid, (_n, _u, use) in enumerate(MEDICINES, start=1):
            demand = use * random.uniform(0.5, 1.6)              # each clinic is busier or quieter
            supply_every = random.choice([30, 45, 60])           # how often deliveries arrive (days)
            supply_size = int(demand * random.uniform(25, 75))   # some clinics are under-supplied, some over
            stock = 0                                            # running count for this clinic+medicine
            for d in range(DAYS):
                day = (START + timedelta(days=d)).isoformat()
                if d % supply_every == 0:                        # % = remainder -> true every supply_every days
                    moves.append((cid, mid, day, "receipt", supply_size))
                    stock += supply_size
                want = max(0, int(random.gauss(demand, demand * 0.3)))   # gauss = bell-curve random number
                give = min(want, stock)                          # can't dispense what isn't there
                if give > 0:
                    moves.append((cid, mid, day, "dispense", give))
                    stock -= give
                if d == 70 and stock > 50 and random.random() < 0.3:     # occasionally some stock expires
                    binned = stock // 5                          # // = whole-number division
                    moves.append((cid, mid, day, "expired", binned))
                    stock -= binned
    moves.sort(key=lambda m: m[2])                               # sort by date so the trigger sees history in order
    with open(DATA / "stock_movements.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clinic_id", "medicine_id", "moved_on", "kind", "quantity"])
        w.writerows(moves)
    print(f"wrote SYNTHETIC data: {len(CLINICS)} clinics, {len(MEDICINES)} medicines, {len(moves)} movements")


if __name__ == "__main__":
    main()
