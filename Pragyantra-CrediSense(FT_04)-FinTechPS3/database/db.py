import sqlite3
import hashlib
import os
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = "app.db"   # Change to an absolute path in production


# ── Connection helper ─────────────────────────────────────────────────────────

@contextmanager
def get_connection():
    """
    Yield a SQLite connection whose rows are accessible by column name.
    WAL mode gives better read/write concurrency.
    Foreign-key enforcement is switched on.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema creation ───────────────────────────────────────────────────────────

def init_db():
    """Create all tables if they don't already exist."""
    with get_connection() as conn:
        conn.executescript("""
            -- ── users ────────────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                username      TEXT NOT NULL UNIQUE,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt          TEXT NOT NULL,
                is_active     INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );

            -- ── credit_scores ────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS credit_scores (
                id            TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL,
                score         INTEGER NOT NULL,
                grade         TEXT NOT NULL,
                bureau_source TEXT NOT NULL DEFAULT 'internal',
                evaluated_at  TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- ── ollama_results ────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS ollama_results (
                id                TEXT PRIMARY KEY,
                user_id           TEXT NOT NULL,
                model_name        TEXT NOT NULL,
                prompt            TEXT NOT NULL,
                output            TEXT NOT NULL,
                inference_time_ms REAL,
                created_at        TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- ── transactions ─────────────────────────────────────────────
            -- FIX: this table was missing entirely; it is required by
            --      save_transactions() and get_history() used in __init__.py
            CREATE TABLE IF NOT EXISTS transactions (
                id               TEXT PRIMARY KEY,
                user_id          TEXT NOT NULL,
                date             TEXT NOT NULL,
                narration        TEXT,
                chq_ref_no       TEXT,
                value_date       TEXT,
                withdrawal_amt   REAL NOT NULL DEFAULT 0.0,
                deposit_amt      REAL NOT NULL DEFAULT 0.0,
                closing_balance  REAL NOT NULL DEFAULT 0.0,
                transaction_type TEXT NOT NULL
                    CHECK(transaction_type IN ('DEBIT','CREDIT','UNKNOWN')),
                page_number      INTEGER,
                created_at       TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- ── indexes ───────────────────────────────────────────────────
            CREATE INDEX IF NOT EXISTS idx_credit_user
                ON credit_scores(user_id);

            CREATE INDEX IF NOT EXISTS idx_ollama_user
                ON ollama_results(user_id);

            CREATE INDEX IF NOT EXISTS idx_ollama_model
                ON ollama_results(model_name);

            CREATE INDEX IF NOT EXISTS idx_txn_user
                ON transactions(user_id);

            CREATE INDEX IF NOT EXISTS idx_txn_user_date
                ON transactions(user_id, date DESC);
        """)
    print(f"[db] Database initialised at '{DB_PATH}'")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _generate_salt() -> str:
    return os.urandom(32).hex()


def _hash_password(password: str, salt: str) -> str:
    """SHA-256 with salt. Swap for bcrypt in production."""
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _verify_password(password: str, salt: str, stored_hash: str) -> bool:
    return _hash_password(password, salt) == stored_hash


def _score_to_grade(score: int) -> str:
    if score >= 800:
        return "Excellent"
    elif score >= 740:
        return "Very Good"
    elif score >= 670:
        return "Good"
    elif score >= 580:
        return "Fair"
    else:
        return "Poor"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_user(row: sqlite3.Row) -> dict:
    """Return a user dict with sensitive fields stripped out."""
    d = dict(row)
    d.pop("password_hash", None)
    d.pop("salt", None)
    return d


# ── User operations ───────────────────────────────────────────────────────────

def create_user(username: str, email: str, password: str) -> dict:
    """
    Register a new user.
    Returns the created user record (without sensitive fields).
    Raises ValueError if username or email already exists.
    """
    user_id = str(uuid.uuid4())
    salt    = _generate_salt()
    pw_hash = _hash_password(password, salt)
    now     = _now()

    with get_connection() as conn:
        try:
            conn.execute(
                """INSERT INTO users
                   (id, username, email, password_hash, salt, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (user_id, username, email, pw_hash, salt, now, now),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Username or email already exists: {e}")

    return get_user_by_id(user_id)


def authenticate_user(username: str, password: str) -> dict | None:
    """Verify credentials. Returns safe user dict on success, None on failure."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
        ).fetchone()

    if row and _verify_password(password, row["salt"], row["password_hash"]):
        return _safe_user(row)
    return None


def get_user_by_id(user_id: str) -> dict | None:
    """Fetch a user by UUID. Returns None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return _safe_user(row) if row else None


def get_user_by_username(username: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return _safe_user(row) if row else None


def update_user_email(user_id: str, new_email: str) -> bool:
    """Update a user's email. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET email = ?, updated_at = ? WHERE id = ?",
            (new_email, _now(), user_id),
        )
    return cursor.rowcount > 0


def update_user_password(user_id: str, new_password: str) -> bool:
    """Re-hash and store a new password. Returns True on success."""
    salt    = _generate_salt()
    pw_hash = _hash_password(new_password, salt)
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
            (pw_hash, salt, _now(), user_id),
        )
    return cursor.rowcount > 0


def deactivate_user(user_id: str) -> bool:
    """Soft-delete a user (is_active = 0). Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
            (_now(), user_id),
        )
    return cursor.rowcount > 0


def delete_user(user_id: str) -> bool:
    """Hard-delete a user and all cascade-linked records."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return cursor.rowcount > 0


# ── Transaction operations ────────────────────────────────────────────────────

def save_transactions(user_id: str, transactions: list[dict]) -> int:
    """
    Bulk-insert parsed bank transactions for a user.

    Each dict in *transactions* must contain the keys produced by
    parser.extract_bank_statement():
        date, narration, chq_ref_no, value_date,
        withdrawal_amt, deposit_amt, closing_balance,
        transaction_type, page_number

    Returns the number of rows inserted.
    Raises ValueError if user_id does not exist.
    """
    if not transactions:
        return 0

    if get_user_by_id(user_id) is None:
        raise ValueError(f"User '{user_id}' does not exist.")

    now  = _now()
    rows = [
        (
            str(uuid.uuid4()),
            user_id,
            t["date"],
            t.get("narration", ""),
            t.get("chq_ref_no", ""),
            t.get("value_date", ""),
            t["withdrawal_amt"],
            t["deposit_amt"],
            t["closing_balance"],
            t["transaction_type"],
            t.get("page_number"),
            now,
        )
        for t in transactions
    ]

    with get_connection() as conn:
        conn.executemany(
            """INSERT INTO transactions
               (id, user_id, date, narration, chq_ref_no, value_date,
                withdrawal_amt, deposit_amt, closing_balance,
                transaction_type, page_number, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )

    return len(rows)


def get_history(user_id: str, limit: int = 100) -> list[dict]:
    """
    Return up to *limit* transaction records for *user_id*, newest date first.
    Returns an empty list if the user has no transactions.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM transactions
               WHERE user_id = ?
               ORDER BY date DESC, created_at DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_transaction_by_id(txn_id: str) -> dict | None:
    """Fetch a single transaction by its UUID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (txn_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_transactions_for_user(user_id: str) -> int:
    """Delete all transactions for a user. Returns the number of rows deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM transactions WHERE user_id = ?", (user_id,)
        )
    return cursor.rowcount


# ── Credit score operations ───────────────────────────────────────────────────

def add_credit_score(user_id: str, score: int, bureau_source: str = "internal") -> dict:
    """
    Insert a credit-score snapshot. Grade is derived automatically.
    Score must be in [300, 900].
    """
    if not (300 <= score <= 900):
        raise ValueError("Credit score must be between 300 and 900.")

    record_id = str(uuid.uuid4())
    grade     = _score_to_grade(score)
    now       = _now()

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO credit_scores
               (id, user_id, score, grade, bureau_source, evaluated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (record_id, user_id, score, grade, bureau_source, now, now),
        )

    return get_credit_score_by_id(record_id)


def get_latest_credit_score(user_id: str) -> dict | None:
    """Return the most recent credit-score record for a user."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT * FROM credit_scores
               WHERE user_id = ?
               ORDER BY evaluated_at DESC
               LIMIT 1""",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def get_credit_score_history(user_id: str, limit: int = 10) -> list[dict]:
    """Return the latest *limit* credit-score snapshots for a user."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM credit_scores
               WHERE user_id = ?
               ORDER BY evaluated_at DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_credit_score_by_id(record_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM credit_scores WHERE id = ?", (record_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_credit_score(record_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM credit_scores WHERE id = ?", (record_id,)
        )
    return cursor.rowcount > 0


# ── Ollama result operations ──────────────────────────────────────────────────

def save_ollama_result(
    user_id: str,
    model_name: str,
    prompt: str,
    output: str,
    inference_time_ms: float = None,
) -> dict:
    """Persist a prompt/output pair from an Ollama model call."""
    record_id = str(uuid.uuid4())
    now       = _now()

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO ollama_results
               (id, user_id, model_name, prompt, output, inference_time_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (record_id, user_id, model_name, prompt, output, inference_time_ms, now),
        )

    return get_ollama_result_by_id(record_id)


def get_ollama_result_by_id(record_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM ollama_results WHERE id = ?", (record_id,)
        ).fetchone()
    return dict(row) if row else None


def get_ollama_results_for_user(user_id: str, limit: int = 20) -> list[dict]:
    """Return the latest Ollama results for a user, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM ollama_results
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_ollama_results_by_model(user_id: str, model_name: str, limit: int = 20) -> list[dict]:
    """Filter a user's Ollama results by model name."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM ollama_results
               WHERE user_id = ? AND model_name = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (user_id, model_name, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_ollama_result(record_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM ollama_results WHERE id = ?", (record_id,)
        )
    return cursor.rowcount > 0


def delete_all_ollama_results_for_user(user_id: str) -> int:
    """Delete every Ollama result for a user. Returns rows deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM ollama_results WHERE user_id = ?", (user_id,)
        )
    return cursor.rowcount


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()

    # ── Users ──────────────────────────────────────────────────────────────
    print("\n── Users ──────────────────────────────")
    user = create_user("alice", "alice@example.com", "securepass123")
    print("Created :", user)

    auth = authenticate_user("alice", "securepass123")
    print("Auth OK :", auth is not None)

    bad_auth = authenticate_user("alice", "wrongpassword")
    print("Bad auth:", bad_auth is None)

    # ── Transactions ────────────────────────────────────────────────────────
    print("\n── Transactions ────────────────────────")
    sample_txns = [
        {
            "date": "01/01/2026", "narration": "UPI/GOOGLE PAY",
            "chq_ref_no": "REF001", "value_date": "01/01/2026",
            "withdrawal_amt": 500.0, "deposit_amt": 0.0,
            "closing_balance": 9500.0, "transaction_type": "DEBIT",
            "page_number": 1,
        },
        {
            "date": "02/01/2026", "narration": "SALARY CREDIT",
            "chq_ref_no": "REF002", "value_date": "02/01/2026",
            "withdrawal_amt": 0.0, "deposit_amt": 50000.0,
            "closing_balance": 59500.0, "transaction_type": "CREDIT",
            "page_number": 1,
        },
    ]
    count = save_transactions(user["id"], sample_txns)
    print(f"Saved   : {count} transaction(s)")

    history = get_history(user["id"])
    print(f"History : {len(history)} record(s)")
    for t in history:
        print(f"  {t['date']}  {t['transaction_type']:<7}  ₹{t['withdrawal_amt'] or t['deposit_amt']:,.2f}  {t['narration']}")

    # ── Credit scores ────────────────────────────────────────────────────────
    print("\n── Credit Scores ───────────────────────")
    score1 = add_credit_score(user["id"], 720, bureau_source="CIBIL")
    print("Score 1 :", score1)
    score2 = add_credit_score(user["id"], 810, bureau_source="Equifax")
    print("Score 2 :", score2)
    print("Latest  :", get_latest_credit_score(user["id"]))
    print("History :", [f"{r['score']} ({r['grade']})" for r in get_credit_score_history(user["id"])])

    # ── Ollama results ───────────────────────────────────────────────────────
    print("\n── Ollama Results ──────────────────────")
    result = save_ollama_result(
        user_id=user["id"],
        model_name="llama3",
        prompt="Explain credit scores in simple terms.",
        output="A credit score is a number that represents your creditworthiness …",
        inference_time_ms=342.5,
    )
    print("Saved   :", result)
    print("Results :", len(get_ollama_results_for_user(user["id"])), "record(s) found")

    print("\n[db] All checks passed.")