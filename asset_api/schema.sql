-- Run once against your PostgreSQL database:
-- psql -d your_db -f schema.sql

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS assets (
    id               SERIAL PRIMARY KEY,
    code             TEXT UNIQUE NOT NULL,
    description      TEXT,
    status           TEXT NOT NULL DEFAULT 'available'
                         CHECK (status IN ('available', 'exhausted')),
    total_quantity   INT NOT NULL CHECK (total_quantity > 0),
    claimed_quantity INT NOT NULL DEFAULT 0
                         CHECK (claimed_quantity >= 0),
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS claims (
    id         SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id   INT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    claimed_at TIMESTAMPTZ DEFAULT NOW(),
    status     TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active'))
);

-- Prevent the same user from claiming the same asset twice
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_asset_claim
    ON claims (user_id, asset_id);

-- Speed up the user history join query
CREATE INDEX IF NOT EXISTS idx_claims_user_id ON claims (user_id);
CREATE INDEX IF NOT EXISTS idx_claims_asset_id ON claims (asset_id);

-- Seed some sample assets for testing
INSERT INTO assets (code, description, total_quantity) VALUES
    ('COUPON-ZEPTO-10', 'Zepto Rs.10 off on first order', 100),
    ('VOUCHER-ZERODHA-FREE', 'Zerodha free brokerage for 1 month', 50),
    ('PROMO-ZOHO-TRIAL', 'Zoho One 30-day trial', 200)
ON CONFLICT (code) DO NOTHING;
