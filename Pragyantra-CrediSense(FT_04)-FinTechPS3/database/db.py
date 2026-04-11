import sqlite3
import hashlib
import os
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = "app.db"  # Change this to your desired path


# ── Connection helper ─────────────────────────────────────────────────────────

@contextmanager
def get_connection():
    """Yield a connection with row_factory so columns are accessible by name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")   # better concurrency
    conn.execute("PRAGMA foreign_keys=ON;")    # enforce FK constraints
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
            CREATE TABLE IF NOT EXISTS users (
                id           TEXT PRIMARY KEY,
                username     TEXT NOT NULL UNIQUE,
                email        TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt         TEXT NOT NULL,
                is_active    INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS credit_scores (
                id             TEXT PRIMARY KEY,
                user_id        TEXT NOT NULL,
                score          INTEGER NOT NULL,
                grade          TEXT NOT NULL,
                bureau_source  TEXT NOT NULL DEFAULT 'internal',
                evaluated_at   TEXT NOT NULL,
                created_at     TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ollama_results (
                id                 TEXT PRIMARY KEY,
                user_id            TEXT NOT NULL,
                model_name         TEXT NOT NULL,
                prompt             TEXT NOT NULL,
                output             TEXT NOT NULL,
                inference_time_ms  REAL,
                created_at         TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_credit_user   ON credit_scores(user_id);
            CREATE INDEX IF NOT EXISTS idx_ollama_user   ON ollama_results(user_id);
            CREATE INDEX IF NOT EXISTS idx_ollama_model  ON ollama_results(model_name);
        """)
    print(f"[db] Database initialised at '{DB_PATH}'")


# ── Password helpers ──────────────────────────────────────────────────────────

def _generate_salt() -> str:
    return os.urandom(32).hex()


def _hash_password(password: str, salt: str) -> str:
    """SHA-256 hash with salt. Replace with bcrypt in production."""
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


# ── User operations ───────────────────────────────────────────────────────────

def create_user(username: str, email: str, password: str) -> dict:
    """
    Register a new user.
    Returns the created user record (without sensitive fields).
    Raises ValueError if username or email already exists.
    """
    user_id   = str(uuid.uuid4())
    salt      = _generate_salt()
    pw_hash   = _hash_password(password, salt)
    now       = _now()

    with get_connection() as conn:
        try:
            conn.execute(
                """INSERT INTO users (id, username, email, password_hash, salt, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (user_id, username, email, pw_hash, salt, now, now)
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Username or email already exists: {e}")

    return get_user_by_id(user_id)


def authenticate_user(username: str, password: str) -> dict | None:
    """
    Verify credentials.
    Returns the user dict on success, None on failure.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
        ).fetchone()

    if row and _verify_password(password, row["salt"], row["password_hash"]):
        return _safe_user(row)
    return None


def get_user_by_id(user_id: str) -> dict | None:
    """Fetch a user by their UUID (no sensitive fields returned)."""
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
            (new_email, _now(), user_id)
        )
    return cursor.rowcount > 0


def update_user_password(user_id: str, new_password: str) -> bool:
    """Re-hash and store a new password. Returns True on success."""
    salt    = _generate_salt()
    pw_hash = _hash_password(new_password, salt)
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
            (pw_hash, salt, _now(), user_id)
        )
    return cursor.rowcount > 0


def deactivate_user(user_id: str) -> bool:
    """Soft-delete a user by setting is_active = 0."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
            (_now(), user_id)
        )
    return cursor.rowcount > 0


def delete_user(user_id: str) -> bool:
    """Hard-delete a user and all their related records (cascade)."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return cursor.rowcount > 0


def _safe_user(row: sqlite3.Row) -> dict:
    """Strip password_hash and salt before returning user data."""
    d = dict(row)
    d.pop("password_hash", None)
    d.pop("salt", None)
    return d


# ── Credit score operations ───────────────────────────────────────────────────

def add_credit_score(user_id: str, score: int, bureau_source: str = "internal") -> dict:
    """
    Insert a new credit score snapshot for a user.
    Grade is computed automatically from the score.
    """
    if not (300 <= score <= 900):
        raise ValueError("Credit score must be between 300 and 900.")

    record_id = str(uuid.uuid4())
    grade     = _score_to_grade(score)
    now       = _now()

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO credit_scores (id, user_id, score, grade, bureau_source, evaluated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (record_id, user_id, score, grade, bureau_source, now, now)
        )

    return get_credit_score_by_id(record_id)


def get_latest_credit_score(user_id: str) -> dict | None:
    """Return the most recent credit score record for a user."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT * FROM credit_scores
               WHERE user_id = ?
               ORDER BY evaluated_at DESC
               LIMIT 1""",
            (user_id,)
        ).fetchone()
    return dict(row) if row else None


def get_credit_score_history(user_id: str, limit: int = 10) -> list[dict]:
    """Return up to `limit` credit score snapshots for a user, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM credit_scores
               WHERE user_id = ?
               ORDER BY evaluated_at DESC
               LIMIT ?""",
            (user_id, limit)
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
    inference_time_ms: float = None
) -> dict:
    """
    Persist a prompt/output pair from an Ollama model call.
    `inference_time_ms` is optional — pass it if you're timing your calls.
    """
    record_id = str(uuid.uuid4())
    now       = _now()

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO ollama_results
               (id, user_id, model_name, prompt, output, inference_time_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (record_id, user_id, model_name, prompt, output, inference_time_ms, now)
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
            (user_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_ollama_results_by_model(user_id: str, model_name: str, limit: int = 20) -> list[dict]:
    """Filter a user's Ollama results by which model was used."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM ollama_results
               WHERE user_id = ? AND model_name = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (user_id, model_name, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_ollama_result(record_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM ollama_results WHERE id = ?", (record_id,)
        )
    return cursor.rowcount > 0


def delete_all_ollama_results_for_user(user_id: str) -> int:
    """Delete every Ollama result for a user. Returns number of rows deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM ollama_results WHERE user_id = ?", (user_id,)
        )
    return cursor.rowcount


# ── Quick smoke-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()

    # --- Users ---
    print("\n── Users ──────────────────────────────")
    user = create_user("alice", "alice@example.com", "securepass123")
    print("Created :", user)

    auth = authenticate_user("alice", "securepass123")
    print("Auth OK :", auth is not None)

    bad_auth = authenticate_user("alice", "wrongpassword")
    print("Bad auth:", bad_auth is None)

    # --- Credit scores ---
    print("\n── Credit Scores ───────────────────────")
    score1 = add_credit_score(user["id"], 720, bureau_source="CIBIL")
    print("Score 1 :", score1)

    score2 = add_credit_score(user["id"], 810, bureau_source="Equifax")
    print("Score 2 :", score2)

    latest = get_latest_credit_score(user["id"])
    print("Latest  :", latest)

    history = get_credit_score_history(user["id"])
    print("History :", [f"{r['score']} ({r['grade']})" for r in history])

    # --- Ollama results ---
    print("\n── Ollama Results ──────────────────────")
    result = save_ollama_result(
        user_id=user["id"],
        model_name="llama3",
        prompt="Explain credit scores in simple terms.",
        output="A credit score is a number that represents your creditworthiness...",
        inference_time_ms=342.5
    )
    print("Saved   :", result)

    all_results = get_ollama_results_for_user(user["id"])
    print("Results :", len(all_results), "record(s) found")

    print("\n[db] All checks passed.")