-- =============================================================================
-- schema.sql
-- Database schema for users, transactions, credit scores, and Ollama results
-- Engine  : MySQL 8.0+
-- Charset : utf8mb4 (full Unicode + emoji support)
-- =============================================================================

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS ollama_results;
DROP TABLE IF EXISTS credit_scores;
DROP TABLE IF EXISTS users;

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- Table: users
-- =============================================================================
CREATE TABLE users (
    id            CHAR(36)     NOT NULL,
    username      VARCHAR(64)  NOT NULL,
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    salt          VARCHAR(128) NOT NULL,
    is_active     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT pk_users           PRIMARY KEY (id),
    CONSTRAINT uq_users_username  UNIQUE (username),
    CONSTRAINT uq_users_email     UNIQUE (email),
    CONSTRAINT ck_users_is_active CHECK (is_active IN (0, 1))
)
ENGINE  = InnoDB
CHARSET = utf8mb4
COLLATE = utf8mb4_unicode_ci
COMMENT = 'Registered users and their hashed login credentials';


-- =============================================================================
-- Table: credit_scores
-- =============================================================================
CREATE TABLE credit_scores (
    id            CHAR(36)    NOT NULL,
    user_id       CHAR(36)    NOT NULL,
    score         SMALLINT    NOT NULL,
    grade         VARCHAR(16) NOT NULL,
    bureau_source VARCHAR(64) NOT NULL DEFAULT 'internal',
    evaluated_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_credit_scores      PRIMARY KEY (id),
    CONSTRAINT fk_credit_scores_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT ck_credit_score_range CHECK (score BETWEEN 300 AND 900),
    CONSTRAINT ck_credit_score_grade CHECK (grade IN (
        'Excellent', 'Very Good', 'Good', 'Fair', 'Poor'
    ))
)
ENGINE  = InnoDB
CHARSET = utf8mb4
COLLATE = utf8mb4_unicode_ci
COMMENT = 'Historical credit-score snapshots per user';


-- =============================================================================
-- Table: ollama_results
-- =============================================================================
CREATE TABLE ollama_results (
    id                CHAR(36)     NOT NULL,
    user_id           CHAR(36)     NOT NULL,
    model_name        VARCHAR(128) NOT NULL,
    prompt            LONGTEXT     NOT NULL,
    output            LONGTEXT     NOT NULL,
    inference_time_ms FLOAT                 DEFAULT NULL,
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_ollama_results      PRIMARY KEY (id),
    CONSTRAINT fk_ollama_results_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT ck_ollama_inference_ms CHECK (
        inference_time_ms IS NULL OR inference_time_ms >= 0
    )
)
ENGINE  = InnoDB
CHARSET = utf8mb4
COLLATE = utf8mb4_unicode_ci
COMMENT = 'Prompt/output pairs from Ollama model calls, keyed to a user';


-- =============================================================================
-- Table: transactions
-- FIX: this table was missing from the original schema
-- Stores individual bank transactions parsed from uploaded PDF statements.
-- =============================================================================
CREATE TABLE transactions (
    id               CHAR(36)       NOT NULL,
    user_id          CHAR(36)       NOT NULL,
    -- Raw date string from the PDF (e.g. "01/01/2026")
    date             VARCHAR(20)    NOT NULL,
    narration        TEXT,
    chq_ref_no       VARCHAR(128),
    value_date       VARCHAR(20),
    withdrawal_amt   DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    deposit_amt      DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    closing_balance  DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    transaction_type VARCHAR(10)    NOT NULL,
    page_number      SMALLINT,
    created_at       DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_transactions      PRIMARY KEY (id),
    CONSTRAINT fk_transactions_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT ck_txn_type CHECK (
        transaction_type IN ('DEBIT', 'CREDIT', 'UNKNOWN')
    ),
    CONSTRAINT ck_withdrawal_amt   CHECK (withdrawal_amt  >= 0),
    CONSTRAINT ck_deposit_amt      CHECK (deposit_amt     >= 0),
    CONSTRAINT ck_closing_balance  CHECK (closing_balance >= 0)
)
ENGINE  = InnoDB
CHARSET = utf8mb4
COLLATE = utf8mb4_unicode_ci
COMMENT = 'Parsed bank statement transactions linked to a user';


-- =============================================================================
-- Indexes
-- =============================================================================

-- users
CREATE INDEX idx_users_is_active
    ON users(is_active);

-- credit_scores
CREATE INDEX idx_credit_scores_user_id
    ON credit_scores(user_id);

CREATE INDEX idx_credit_scores_user_evaluated
    ON credit_scores(user_id, evaluated_at DESC);

-- ollama_results
CREATE INDEX idx_ollama_results_user_id
    ON ollama_results(user_id);

CREATE INDEX idx_ollama_results_model_name
    ON ollama_results(model_name);

CREATE INDEX idx_ollama_results_user_model
    ON ollama_results(user_id, model_name);

-- transactions
CREATE INDEX idx_transactions_user_id
    ON transactions(user_id);

CREATE INDEX idx_transactions_user_date
    ON transactions(user_id, date DESC);

CREATE INDEX idx_transactions_type
    ON transactions(user_id, transaction_type);


-- =============================================================================
-- Views
-- =============================================================================

-- Latest credit score per user
CREATE OR REPLACE VIEW vw_latest_credit_score AS
SELECT
    u.id          AS user_id,
    u.username,
    u.email,
    cs.id         AS score_id,
    cs.score,
    cs.grade,
    cs.bureau_source,
    cs.evaluated_at
FROM users AS u
INNER JOIN credit_scores AS cs
    ON cs.id = (
        SELECT id
        FROM   credit_scores
        WHERE  user_id = u.id
        ORDER  BY evaluated_at DESC
        LIMIT  1
    );


-- Ollama usage summary per user
CREATE OR REPLACE VIEW vw_ollama_user_summary AS
SELECT
    r.user_id,
    COUNT(*)               AS total_results,
    AVG(inference_time_ms) AS avg_inference_ms,
    MAX(created_at)        AS last_result_at,
    (
        SELECT model_name
        FROM   ollama_results AS r2
        WHERE  r2.user_id = r.user_id
        ORDER  BY created_at DESC
        LIMIT  1
    )                      AS last_model_used
FROM ollama_results AS r
GROUP BY r.user_id;


-- Transaction summary per user (useful for ML feature extraction)
CREATE OR REPLACE VIEW vw_transaction_summary AS
SELECT
    user_id,
    COUNT(*)                                                    AS total_transactions,
    SUM(CASE WHEN transaction_type = 'DEBIT'  THEN 1 ELSE 0 END) AS total_debits,
    SUM(CASE WHEN transaction_type = 'CREDIT' THEN 1 ELSE 0 END) AS total_credits,
    ROUND(SUM(withdrawal_amt), 2)                               AS total_withdrawal,
    ROUND(SUM(deposit_amt),    2)                               AS total_deposit,
    ROUND(SUM(deposit_amt) - SUM(withdrawal_amt), 2)            AS net_flow,
    ROUND(AVG(withdrawal_amt), 2)                               AS avg_debit_amt,
    ROUND(AVG(deposit_amt),    2)                               AS avg_credit_amt,
    MIN(date)                                                   AS earliest_date,
    MAX(date)                                                   AS latest_date
FROM transactions
GROUP BY user_id;


-- =============================================================================
-- Seed data  (development / testing only — remove for production)
-- =============================================================================

INSERT INTO users (id, username, email, password_hash, salt, is_active, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'testuser',
    'test@example.com',
    'a6e0c6e2f4b3e8d1c2a9b7f5e3d1c0a8b6f4e2d0c8a6b4e2d0c8a6b4f2e0d8c6',
    'deadbeefdeadbeefdeadbeefdeadbeef',
    1,
    NOW(),
    NOW()
);

INSERT INTO credit_scores (id, user_id, score, grade, bureau_source, evaluated_at, created_at)
VALUES
(
    '00000000-0000-0000-0000-000000000010',
    '00000000-0000-0000-0000-000000000001',
    680, 'Good', 'CIBIL', NOW() - INTERVAL 30 DAY, NOW() - INTERVAL 30 DAY
),
(
    '00000000-0000-0000-0000-000000000011',
    '00000000-0000-0000-0000-000000000001',
    740, 'Very Good', 'CIBIL', NOW(), NOW()
);

INSERT INTO ollama_results (id, user_id, model_name, prompt, output, inference_time_ms, created_at)
VALUES (
    '00000000-0000-0000-0000-000000000020',
    '00000000-0000-0000-0000-000000000001',
    'llama3',
    'What does a credit score of 740 mean?',
    'A credit score of 740 is considered Very Good. You are likely to be approved for most loans at competitive interest rates.',
    287.4,
    NOW()
);

INSERT INTO transactions (
    id, user_id, date, narration, chq_ref_no, value_date,
    withdrawal_amt, deposit_amt, closing_balance, transaction_type, page_number, created_at
)
VALUES
(
    '00000000-0000-0000-0000-000000000030',
    '00000000-0000-0000-0000-000000000001',
    '01/01/2026', 'SALARY CREDIT', 'REF001', '01/01/2026',
    0.00, 50000.00, 50000.00, 'CREDIT', 1, NOW()
),
(
    '00000000-0000-0000-0000-000000000031',
    '00000000-0000-0000-0000-000000000001',
    '05/01/2026', 'UPI/GOOGLE PAY', 'REF002', '05/01/2026',
    1500.00, 0.00, 48500.00, 'DEBIT', 1, NOW()
);

-- =============================================================================
-- End of schema.sql
-- =============================================================================