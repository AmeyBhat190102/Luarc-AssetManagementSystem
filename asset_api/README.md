# Asset Management API

A production-ready REST API for managing coupons/vouchers with JWT authentication and concurrency-safe claiming, built with **FastAPI**, **PostgreSQL**, and **psycopg2**.

---

## Tech Stack

| Layer            | Technology                          |
| ---------------- | ----------------------------------- |
| Framework        | FastAPI                             |
| Database         | PostgreSQL                          |
| DB Driver        | psycopg2 (threaded connection pool) |
| Auth             | JWT                                 |
| Password Hashing | `pwdlib` + bcrypt                   |
| Validation       | Pydantic v2 + pydantic-settings     |
| Logging          | structlog                           |
| Runtime          | Python 3.12+                        |

---

## Architecture Overview

```
┌─────────────┐     JWT Bearer      ┌──────────────────┐
│   Client    │ ─────────────────►  │   FastAPI App    │
└─────────────┘                     └────────┬─────────┘
                                             │
                          ┌──────────────────┼──────────────────┐
                          │                  │                  │
                   ┌──────▼──────┐   ┌───────▼──────┐  ┌───────▼──────┐
                   │ auth/router │   │assets/router │  │  /health     │
                   └──────┬──────┘   └───────┬──────┘  └─────────────-┘
                          │                  │
                   ┌──────▼──────┐   ┌───────▼──────┐
                   │auth/service │   │assets/service│
                   └──────┬──────┘   └───────┬──────┘
                          │                  │
                   ┌──────▼──────────────────▼──────┐
                   │     ThreadedConnectionPool     │
                   │          (psycopg2)            │
                   └─────────────────┬──────────────┘
                                     │
                              ┌──────▼──────┐
                              │  PostgreSQL │
                              └─────────────┘
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL running locally (or via Docker)
- [`uv`](https://github.com/astral-sh/uv) (recommended) or pip

### 1. Clone & set up the environment

```bash
git clone <repo-url>
cd asset_api

# Using uv (recommended)
uv venv && uv sync

# Or pip
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual values
```

### 3. Initialise the database

```bash
psql -d your_db_name -f schema.sql
```

This creates the `users`, `assets`, and `claims` tables, all indexes, and seeds 3 sample assets.

### 4. Run the server

```bash
# Development (auto-reload)
uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

Interactive docs available at: **http://localhost:8000/docs**

---

## Environment Variables

| Variable                      | Required | Default | Description                                   |
| ----------------------------- | -------- | ------- | --------------------------------------------- |
| `DATABASE_URL`                | ✅       | —       | PostgreSQL DSN                                |
| `SECRET_KEY`                  | ✅       | —       | JWT signing secret (use a long random string) |
| `ALGORITHM`                   | ❌       | `HS256` | JWT signing algorithm                         |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ❌       | `60`    | Token lifetime in minutes                     |
| `DB_MIN_CONN`                 | ❌       | `2`     | Min connections in pool                       |
| `DB_MAX_CONN`                 | ❌       | `10`    | Max connections in pool                       |

---

## Database Schema

```
users
─────────────────────────────────────
id              SERIAL PK
email           TEXT UNIQUE NOT NULL
hashed_password TEXT NOT NULL
created_at      TIMESTAMPTZ

assets
─────────────────────────────────────
id               SERIAL PK
code             TEXT UNIQUE NOT NULL
description      TEXT
status           TEXT  CHECK (available | exhausted)
total_quantity   INT   CHECK > 0
claimed_quantity INT   DEFAULT 0
created_at       TIMESTAMPTZ

claims
─────────────────────────────────────
id         SERIAL PK
user_id    INT FK → users(id)
asset_id   INT FK → assets(id)
claimed_at TIMESTAMPTZ
status     TEXT CHECK (active)

UNIQUE INDEX on (user_id, asset_id)   ← enforces one claim per user per asset at DB level
INDEX on claims(user_id)              ← speeds up history join
INDEX on claims(asset_id)             ← speeds up asset lookup
```

---

## Concurrency & Data Integrity

This is the core challenge of the system. The claim endpoint handles it with a **pessimistic row-level lock**.

### Claim Flow

```
Request arrives
      │
      ▼
SELECT ... FOR UPDATE  ──► blocks if another tx holds the lock
      │
      ▼
Check asset status == 'available'
      │
      ▼
Check claimed_quantity < total_quantity
      │
      ▼
Check no existing claim by this user
      │
      ▼
INSERT INTO claims
      │
      ▼
UPDATE assets SET claimed_quantity = claimed_quantity + 1
       optionally SET status = 'exhausted' if now full
      │
      ▼
COMMIT  ──► lock released, next waiting request unblocks
```

---

## Authentication Flow

```
Register ──► bcrypt hash password ──► store in DB

Login ──► fetch user by email
       ──► verify password against bcrypt hash
       ──► issue signed JWT { sub: user_id, email, exp }

Protected request ──► extract Bearer token
                   ──► verify JWT signature + expiry
                   ──► fetch user from DB
                   ──► inject into route handler
```

Passwords are hashed with `pwdlib` + `bcrypt` which internally pre-hashes with SHA-256 before bcrypt to handle the 72-byte bcrypt input limit transparently.

