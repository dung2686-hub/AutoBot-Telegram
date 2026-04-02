CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER UNIQUE NOT NULL,
    username        TEXT DEFAULT '',
    full_name       TEXT DEFAULT '',
    balance         INTEGER DEFAULT 0,           -- VND, stored as integer
    language        TEXT DEFAULT 'vi',
    referral_code   TEXT DEFAULT '',
    referred_by     INTEGER DEFAULT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_markups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      TEXT UNIQUE NOT NULL,         -- Canboso product ID
    product_name    TEXT DEFAULT '',
    markup_percent  INTEGER DEFAULT 20,           -- Per-product markup
    is_active       INTEGER DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS deposits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    amount          INTEGER NOT NULL,             -- VND
    code            TEXT UNIQUE NOT NULL,          -- Payment code (NAP_xxx)
    status          TEXT DEFAULT 'pending',        -- pending / completed / expired
    reference_code  TEXT DEFAULT '',               -- SePay reference (idempotency)
    expires_at      TIMESTAMP NOT NULL,
    completed_at    TIMESTAMP DEFAULT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    order_code      TEXT DEFAULT '',               -- Canboso order code
    product_id      TEXT NOT NULL,
    product_name    TEXT NOT NULL,
    quantity        INTEGER DEFAULT 1,
    original_price  INTEGER NOT NULL,              -- Canboso price
    sell_price      INTEGER NOT NULL,              -- Price after markup
    total_amount    INTEGER NOT NULL,              -- sell_price * quantity
    delivered_data  TEXT DEFAULT '[]',             -- JSON: [{user, password, verifyEmail}]
    status          TEXT DEFAULT 'completed',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    type            TEXT NOT NULL,                 -- deposit / purchase / refund / admin_credit
    amount          INTEGER NOT NULL,              -- Positive = credit, negative = debit
    balance_after   INTEGER NOT NULL,
    description     TEXT DEFAULT '',
    reference_id    TEXT DEFAULT '',               -- deposit.id or order.id
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_deposits_code ON deposits(code);
CREATE INDEX IF NOT EXISTS idx_deposits_status ON deposits(status);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
