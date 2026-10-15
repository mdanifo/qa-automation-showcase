-- Applied at every app start. Every statement is idempotent.

CREATE TABLE IF NOT EXISTS users (
  username     TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  role         TEXT NOT NULL CHECK (role IN ('employee', 'manager', 'finance'))
);

CREATE TABLE IF NOT EXISTS claims (
  id            SERIAL PRIMARY KEY,
  owner         TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  title         TEXT NOT NULL,
  category      TEXT NOT NULL,
  amount_cents  INTEGER NOT NULL CHECK (amount_cents > 0),
  miles         NUMERIC(6,1),
  expense_date  DATE NOT NULL,
  status        TEXT NOT NULL DEFAULT 'submitted'
                CHECK (status IN ('submitted', 'approved', 'rejected', 'paid')),
  submitted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_by    TEXT REFERENCES users(username) ON DELETE SET NULL,
  decided_at    TIMESTAMPTZ,
  decision_note TEXT,
  paid_by       TEXT REFERENCES users(username) ON DELETE SET NULL,
  paid_at       TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS claim_events (
  id       SERIAL PRIMARY KEY,
  claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  actor    TEXT NOT NULL,
  action   TEXT NOT NULL CHECK (action IN ('submitted', 'approved', 'rejected', 'paid')),
  at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
