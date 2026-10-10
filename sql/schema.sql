-- =====================================================================
-- schema.sql  -  Clinic Stock-Out Database (SDG 3: Good Health)
-- Stock is never stored as a number that can drift out of date. Instead every
-- delivery and every dispensed pack is recorded as a movement, and stock on
-- hand is CALCULATED from the movements (the same idea as a bank statement).
-- =====================================================================

DROP VIEW IF EXISTS redistribution_options;
DROP VIEW IF EXISTS stock_status;
DROP VIEW IF EXISTS stock_on_hand;
DROP TABLE IF EXISTS stock_movements;
DROP TABLE IF EXISTS medicines;
DROP TABLE IF EXISTS clinics;

CREATE TABLE clinics (
    clinic_id  INTEGER PRIMARY KEY,                 -- unique id
    name       TEXT NOT NULL UNIQUE,                -- clinic name
    lga        TEXT NOT NULL                        -- local government area
);

CREATE TABLE medicines (
    medicine_id  INTEGER PRIMARY KEY,               -- unique id
    name         TEXT NOT NULL UNIQUE,              -- e.g. 'ORS sachet'
    unit         TEXT NOT NULL                      -- how it is counted, e.g. 'sachet', 'pack'
);

CREATE TABLE stock_movements (
    movement_id  INTEGER PRIMARY KEY AUTOINCREMENT,                     -- unique, in insertion order
    clinic_id    INTEGER NOT NULL REFERENCES clinics(clinic_id),        -- which clinic
    medicine_id  INTEGER NOT NULL REFERENCES medicines(medicine_id),    -- which medicine
    moved_on     TEXT    NOT NULL CHECK (date(moved_on) = moved_on),    -- 'YYYY-MM-DD'
    kind         TEXT    NOT NULL CHECK (kind IN ('receipt', 'dispense', 'expired')),  -- in, out, or thrown away
    quantity     INTEGER NOT NULL CHECK (quantity > 0)                  -- always positive; 'kind' gives the direction
);
CREATE INDEX idx_moves ON stock_movements(clinic_id, medicine_id, moved_on);  -- speeds up the per-item sums

-- TRIGGER = code the database runs automatically. This one fires BEFORE every insert
-- and refuses to let a clinic dispense (or bin) more than it actually has.
CREATE TRIGGER prevent_negative_stock
BEFORE INSERT ON stock_movements
WHEN NEW.kind IN ('dispense', 'expired')                                -- only outgoing movements can go negative
 AND NEW.quantity > (
        SELECT COALESCE(SUM(CASE WHEN kind = 'receipt'                  -- receipts add...
                                 THEN quantity ELSE -quantity END), 0)  -- ...everything else subtracts; COALESCE turns "no rows" into 0
        FROM stock_movements
        WHERE clinic_id = NEW.clinic_id                                 -- NEW = the row being inserted
          AND medicine_id = NEW.medicine_id
          AND moved_on <= NEW.moved_on)                                 -- stock as of that day
BEGIN
    SELECT RAISE(ABORT, 'not enough stock for this dispense');          -- cancel the insert with an error
END;

-- Current stock per clinic and medicine.
CREATE VIEW stock_on_hand AS
SELECT
    c.clinic_id, c.name AS clinic, c.lga,
    m.medicine_id, m.name AS medicine, m.unit,
    COALESCE(SUM(CASE WHEN s.kind = 'receipt' THEN s.quantity ELSE -s.quantity END), 0) AS on_hand
FROM clinics c
CROSS JOIN medicines m                                                  -- every clinic x every medicine, even with no movements
LEFT JOIN stock_movements s
       ON s.clinic_id = c.clinic_id AND s.medicine_id = m.medicine_id
GROUP BY c.clinic_id, m.medicine_id;

-- Stock + how fast it is being used + how many days it will last.
CREATE VIEW stock_status AS
WITH report AS (SELECT MAX(moved_on) AS report_date FROM stock_movements),  -- "today" = latest date in the data
usage AS (
    -- An empty shelf can't dispense, so a clinic that ran out shows LOW recent use even
    -- though patients still need the medicine. To avoid hiding that demand we take the
    -- HIGHER of the 30-day and 90-day daily averages.
    SELECT clinic_id, medicine_id,
           MAX(SUM(CASE WHEN moved_on > date(report.report_date, '-30 days')  -- date(x, '-30 days') = 30 days before x
                        THEN quantity ELSE 0 END) / 30.0,                     -- 30-day average per day
               SUM(CASE WHEN moved_on > date(report.report_date, '-90 days')
                        THEN quantity ELSE 0 END) / 90.0                      -- 90-day average per day
           ) AS avg_daily_use                                                 -- MAX(a, b) with 2 values = the larger one
    FROM stock_movements, report
    WHERE kind = 'dispense'
    GROUP BY clinic_id, medicine_id
)
SELECT
    h.clinic, h.lga, h.medicine, h.unit, h.on_hand,
    ROUND(COALESCE(u.avg_daily_use, 0), 2)                    AS avg_daily_use,
    CASE WHEN COALESCE(u.avg_daily_use, 0) = 0 THEN NULL     -- not used recently -> can't estimate (avoid / 0)
         ELSE ROUND(h.on_hand / u.avg_daily_use, 1) END      AS days_left,
    CASE WHEN h.on_hand = 0                                  THEN 'STOCKED OUT'
         WHEN u.avg_daily_use > 0 AND h.on_hand / u.avg_daily_use < 14 THEN 'CRITICAL'
         WHEN u.avg_daily_use > 0 AND h.on_hand / u.avg_daily_use < 30 THEN 'LOW'
         ELSE 'OK' END                                       AS status,
    -- Order enough for 60 days of use, minus what is already on the shelf (never negative).
    MAX(0, CAST(ROUND(COALESCE(u.avg_daily_use, 0) * 60 - h.on_hand) AS INTEGER)) AS reorder_qty
FROM stock_on_hand h
LEFT JOIN usage u ON u.clinic_id = h.clinic_id AND u.medicine_id = h.medicine_id;

-- Before ordering more, can a nearby clinic with too much stock share some?
-- A SELF-JOIN: stock_status is joined to itself to pair a "needy" clinic with a "donor".
CREATE VIEW redistribution_options AS
SELECT
    need.medicine,
    need.clinic                                   AS needs_stock,
    need.status                                   AS need_status,
    give.clinic                                   AS can_give,
    give.days_left                                AS donor_days_left,
    -- the donor keeps 60 days for itself and can share the rest
    CAST(give.on_hand - give.avg_daily_use * 60 AS INTEGER) AS spare_qty
FROM stock_status need
JOIN stock_status give
  ON give.medicine = need.medicine                -- same medicine...
 AND give.clinic <> need.clinic                   -- ...different clinic...
 AND give.lga = need.lga                          -- ...in the same LGA (close enough to move stock)
WHERE need.status IN ('STOCKED OUT', 'CRITICAL')
  AND give.days_left > 90                         -- the donor has more than 3 months' supply
ORDER BY need.medicine, spare_qty DESC;
