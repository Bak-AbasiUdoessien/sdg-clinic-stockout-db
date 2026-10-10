# Clinic Stock-Out Database (SDG 3: Good Health)

When a clinic runs out of ORS, zinc or antimalarials, children die of diseases we already know how to treat. This SQLite database tracks essential medicines across clinics and answers four questions: **who is out, who will run out within 14 days, what to reorder, and which nearby clinic could share stock today.**

**SDG targets covered:** 3.8 (access to essential medicines), together with 3.2 (child deaths) and 3.3 (malaria).

## Design idea: never store "stock", calculate it
Every delivery, dispense and expiry is saved as a **movement**. Stock on hand is always calculated from the movements, like a bank balance from its transactions, so it can never drift out of sync.

| Object | Type | What it does |
|---|---|---|
| `clinics`, `medicines`, `stock_movements` | tables | Raw data, with `CHECK` rules and foreign keys |
| `prevent_negative_stock` | **trigger** | Blocks any dispense larger than the stock on hand at that date |
| `stock_on_hand` | view | Receipts minus outgoing movements. A `CROSS JOIN` makes sure items with no activity still show up |
| `stock_status` | view | Daily use, days of stock left, a status of OUT / CRITICAL / LOW / OK, and the reorder quantity |
| `redistribution_options` | view | A **self-join** that pairs a clinic in need with a clinic in the same LGA holding more than 90 days of stock |

**Something worth explaining in an interview:** a clinic that has run out *dispenses nothing*, so its recent usage looks like zero and it would never be reordered. `stock_status` avoids that trap by taking the **higher of the 30-day and 90-day** average use. A unit test covers this case.

## Run it
```bash
python generate_sample_data.py      # SYNTHETIC: 6 clinics, 6 medicines, 120 days
python main.py                      # builds clinic_stock.db and prints the 5 reports
python -m unittest discover tests   # 5 tests, including the trigger
```
Everything uses the Python standard library. Open `clinic_stock.db` in VS Code with SQLite Viewer to explore the views.

## Limitations
- Each donor's spare stock is shown against every clinic in need, so in practice you share it out, not give it to all of them at once.
- The reorder rule is "60 days of use minus stock on hand". Real supply chains also account for lead time and safety stock.

## Use real data
Nigeria reports facility stock levels through **DHIS2** (the NHMIS logistics data) and the NPSCMP (National Product Supply Chain Management Programme). Export the stock movements, map them to `data/stock_movements.csv`, and the views will work unchanged.

## ⚠️ Data note
The bundled data is **simulated**. The clinic names and quantities are invented.
