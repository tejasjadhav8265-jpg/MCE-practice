import sqlite3
import hashlib
import os
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = "app.db"


# ── Connection ─────────────────────────────────────

@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"DB error: {e}")
    finally:
        conn.close()


# ── Schema ─────────────────────────────────────────

def init_db():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS credit_scores (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            score INTEGER,
            grade TEXT,
            bureau_source TEXT,
            evaluated_at TEXT,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ollama_results (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            model_name TEXT,
            prompt TEXT,
            output TEXT,
            inference_time_ms REAL,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- ✅ ADDED (you forgot this in Python)
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            date TEXT,
            narration TEXT,
            withdrawal_amt REAL,
            deposit_amt REAL,
            closing_balance REAL,
            transaction_type TEXT,
            page_number INTEGER,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

    print("✅ DB initialized")


# ── Helpers ────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat()


def _generate_salt():
    return os.urandom(16).hex()


def _hash_password(password, salt):
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _verify_password(password, salt, stored):
    return _hash_password(password, salt) == stored


def _score_to_grade(score):
    if score >= 800: return "Excellent"
    if score >= 740: return "Very Good"
    if score >= 670: return "Good"
    if score >= 580: return "Fair"
    return "Poor"


# ── USERS ──────────────────────────────────────────

def create_user(username, email, password):
    user_id = str(uuid.uuid4())
    salt = _generate_salt()
    pw_hash = _hash_password(password, salt)

    with get_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO users VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """, (user_id, username, email, pw_hash, salt, _now(), _now()))
        except sqlite3.IntegrityError:
            raise ValueError("User already exists")

    return {"id": user_id, "username": username, "email": email}


def authenticate_user(username, password):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1",
            (username,)
        ).fetchone()

    if row and _verify_password(password, row["salt"], row["password_hash"]):
        return dict(row)

    return None


# ── CREDIT SCORE ───────────────────────────────────

def add_credit_score(user_id, score):
    record_id = str(uuid.uuid4())
    grade = _score_to_grade(score)

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO credit_scores VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (record_id, user_id, score, grade, "internal", _now(), _now()))

    return {"score": score, "grade": grade}


# ── TRANSACTIONS ───────────────────────────────────

def save_transactions(user_id, transactions):
    with get_connection() as conn:
        for t in transactions:
            conn.execute("""
                INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                user_id,
                t["date"],
                t.get("narration", ""),
                t.get("withdrawal_amt", 0),
                t.get("deposit_amt", 0),
                t.get("closing_balance", 0),
                t.get("transaction_type", "UNKNOWN"),
                t.get("page_number", 1),
                _now()
            ))


# ── OLLAMA ─────────────────────────────────────────

def save_ollama_result(user_id, model, prompt, output):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO ollama_results VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            user_id,
            model,
            prompt,
            output,
            None,
            _now()
        ))
