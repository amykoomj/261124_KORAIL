PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS branches;
DROP TABLE IF EXISTS snapshots;

CREATE TABLE branches (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT    NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 30),
  color_index INTEGER NOT NULL CHECK (color_index BETWEEN 0 AND 7),
  created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE sales (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  quarter    TEXT    NOT NULL CHECK (quarter GLOB '[0-9][0-9][0-9][0-9]-Q[1-4]'),
  branch_id  INTEGER NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
  amount     INTEGER NOT NULL CHECK (amount >= 0),
  customers  INTEGER NOT NULL CHECK (customers >= 1),
  is_sample  INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0,1)),
  created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
  updated_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (quarter, branch_id)
);

CREATE INDEX idx_sales_quarter ON sales(quarter);
CREATE INDEX idx_sales_branch  ON sales(branch_id);

CREATE TABLE snapshots (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  action     TEXT NOT NULL,
  payload    TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
