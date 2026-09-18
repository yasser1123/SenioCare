"""
Cloud PostgreSQL Database for SenioCare Tools.

Manages the Neon PostgreSQL connection and table schema.
Seed data is loaded from seniocare/data/seeds/*.json — edit those files
to change meals, exercises, interactions, etc. without touching this module.

Tables:
    meals                  — Food items with nutritional info and recipes
    condition_dietary_rules — Nutrient thresholds per health condition
    drug_food_interactions — Drug-food interaction records
    disease_symptoms       — Disease-to-symptom mappings with severity
    disease_precautions    — Precautionary measures per disease
    food_allergens         — Food-to-allergen category mappings
    exercises              — Exercise recommendations by mobility level
    medical_reports        — Analyzed medical report results (image analysis)
"""

import json
import os
import threading
import time
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")

DATABASE_URL = os.environ.get("APP_DATABASE_URL", "")

_SEEDS_DIR = Path(__file__).parent / "seeds"

# Track whether tables have been initialized this process
_initialized = False


def _require_database_url() -> str:
    """Return DATABASE_URL or raise a clear error (called lazily, not at import)."""
    if psycopg2 is None:
        raise RuntimeError(
            "psycopg2 is not installed. Install psycopg2-binary to use PostgreSQL database features."
        )
    db_url = os.environ.get("APP_DATABASE_URL", "") or DATABASE_URL
    if not db_url:
        raise RuntimeError(
            "APP_DATABASE_URL is not set. Add it to the root .env file.\n"
            "Example: APP_DATABASE_URL=postgresql://user:pass@host/db?sslmode=require"
        )
    return db_url


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


# Neon's pooler hostname resolves to three IPs, and from some networks one of
# them blackholes the TCP connect. libpq tries the addresses in order, so
# without connect_timeout roughly every other connect hung forever (observed:
# the test suite stalling at 0% CPU). With connect_timeout, a bad address
# costs CONNECT_TIMEOUT_S and libpq falls through to the next one.
#
# A fresh connection therefore costs 1-10 s, and every tool call used to open
# one. Connections are pooled and reused instead: get_connection() hands out
# a proxy whose close() returns the underlying connection to the pool, so the
# `conn = get_connection() ... conn.close()` pattern used everywhere keeps
# working unchanged.
#
# Separately, synchronous psycopg2 has no query timeout: if the server (or the
# path to it) stops answering after a query is sent, cursor.execute() blocks
# forever. Also observed with Neon, on connections that had just passed a
# SELECT 1. psycopg2's "green" wait callback lets us put a deadline on every
# socket wait during query execution. Connects deliberately stay in blocking
# mode (callback temporarily disabled) because only libpq's blocking connect
# implements per-address fallback with connect_timeout.
CONNECT_TIMEOUT_S = int(os.environ.get("APP_DATABASE_CONNECT_TIMEOUT_S", "10"))
QUERY_TIMEOUT_S = float(os.environ.get("APP_DATABASE_QUERY_TIMEOUT_S", "20"))
POOL_MAX_IDLE = int(os.environ.get("APP_DATABASE_POOL_SIZE", "4"))
_CONNECT_KWARGS = {
    "connect_timeout": CONNECT_TIMEOUT_S,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}

_connect_lock = threading.Lock()


def _wait_with_deadline(conn):
    """psycopg2 wait callback: like psycopg2.extras.wait_select, but bounded.

    Raises OperationalError once QUERY_TIMEOUT_S passes without the server
    completing the current operation. The connection is unusable afterwards
    and is discarded by the pool on its next health check.
    """
    import select as _select
    from psycopg2 import extensions as _ext

    deadline = time.monotonic() + QUERY_TIMEOUT_S
    while True:
        state = conn.poll()
        if state == _ext.POLL_OK:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise psycopg2.OperationalError(
                f"database query did not complete within {QUERY_TIMEOUT_S:g}s (client-side deadline)"
            )
        if state == _ext.POLL_READ:
            _select.select([conn.fileno()], [], [], remaining)
        elif state == _ext.POLL_WRITE:
            _select.select([], [conn.fileno()], [], remaining)
        else:
            raise psycopg2.OperationalError(f"unexpected poll state {state!r}")


if psycopg2 is not None:
    psycopg2.extensions.set_wait_callback(_wait_with_deadline)


def _connect(url: str, **kwargs):
    """Open a brand-new connection, in blocking mode so libpq can fall through
    to the next resolved address when one times out."""
    from psycopg2 import extensions as _ext

    with _connect_lock:
        _ext.set_wait_callback(None)
        try:
            return psycopg2.connect(url, **_CONNECT_KWARGS, **kwargs)
        finally:
            _ext.set_wait_callback(_wait_with_deadline)


def _quiet_close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def _healthy(conn) -> bool:
    """Cheap liveness probe; an idle pooled connection may have been dropped server-side."""
    try:
        if conn.closed:
            return False
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.rollback()
        return True
    except Exception:
        return False


class _ConnectionPool:
    """Minimal thread-safe pool: keeps up to `max_idle` idle connections.

    psycopg2.pool is not used because it only retains `minconn` idle
    connections and opens all of them eagerly at construction; here nothing
    is opened until needed and up to `max_idle` are kept once opened.
    """

    # A connection released this recently is handed out again without the
    # SELECT 1 probe: the probe costs two round trips (~0.4 s to us-east-1
    # from Egypt) and a connection idle for a few seconds is not what breaks.
    HEALTH_CHECK_AFTER_S = 30.0

    def __init__(self, url: str, max_idle: int):
        self.url = url
        self.max_idle = max_idle
        self._idle: list = []  # [(conn, released_at_monotonic), ...]
        self._lock = threading.Lock()
        self.stats = {"created": 0, "reused": 0, "discarded": 0}

    def acquire(self):
        while True:
            with self._lock:
                conn, released_at = self._idle.pop() if self._idle else (None, 0.0)
            if conn is None:
                conn = _connect(self.url, cursor_factory=RealDictCursor)
                self.stats["created"] += 1
                return conn
            fresh = (time.monotonic() - released_at) < self.HEALTH_CHECK_AFTER_S
            if fresh or _healthy(conn):
                self.stats["reused"] += 1
                return conn
            self.stats["discarded"] += 1
            _quiet_close(conn)

    def release(self, conn, discard: bool = False) -> None:
        if discard or conn.closed:
            self.stats["discarded"] += 1
            _quiet_close(conn)
            return
        with self._lock:
            if len(self._idle) < self.max_idle:
                self._idle.append((conn, time.monotonic()))
                return
        _quiet_close(conn)

    def close_all(self) -> None:
        with self._lock:
            idle, self._idle = self._idle, []
        for conn, _ in idle:
            _quiet_close(conn)


class _PooledConnection:
    """Proxy around a pooled psycopg2 connection.

    Everything is delegated to the real connection except close(), which rolls
    back any open transaction and returns the connection to the pool instead of
    closing it. A connection that failed is discarded rather than returned.
    """

    __slots__ = ("_conn", "_pool")

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def __getattr__(self, name):
        conn = object.__getattribute__(self, "_conn")
        if conn is None:
            raise psycopg2.InterfaceError("connection already returned to the pool")
        return getattr(conn, name)

    def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            # Only pay the round trip when a transaction is actually open.
            if conn.info.transaction_status != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                conn.rollback()
        except Exception:
            self._pool.release(conn, discard=True)
            return
        self._pool.release(conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __del__(self):
        # Safety net for callers that forget close(): return the connection
        # rather than leaking it.
        try:
            self.close()
        except Exception:
            pass


_pool = None
_pool_lock = threading.Lock()


def _get_pool(url: str) -> _ConnectionPool:
    """Return the process-wide pool for `url`, creating it on first use."""
    global _pool
    with _pool_lock:
        if _pool is None or _pool.url != url:
            if _pool is not None:
                _pool.close_all()
            _pool = _ConnectionPool(url, POOL_MAX_IDLE)
        return _pool


def get_connection() -> psycopg2.extensions.connection:
    """Return a pooled connection using RealDictCursor.

    Call close() when done; that returns it to the pool. Retries once if a
    fresh connect fails (transient network drop or a connect that exhausted
    every resolved address within CONNECT_TIMEOUT_S).
    """
    url = _require_database_url()
    pool = _get_pool(url)
    try:
        conn = pool.acquire()
    except psycopg2.OperationalError:
        conn = pool.acquire()
    return _PooledConnection(conn, pool)


def pool_stats() -> dict:
    """Connection reuse counters (exposed for /health and the metrics report)."""
    return dict(_pool.stats) if _pool is not None else {}


def close_pool() -> None:
    """Close every pooled connection (app shutdown, tests)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close_all()
            _pool = None


# ---------------------------------------------------------------------------
# Initialization (idempotent)
# ---------------------------------------------------------------------------


def _initialize_database() -> None:
    """Create all tables and populate with seed data (idempotent)."""
    global _initialized
    if _initialized:
        return

    conn = _connect(_require_database_url())
    cursor = conn.cursor()

    try:
        _create_tables(cursor)
        _seed_meals(cursor)
        _seed_condition_rules(cursor)
        _seed_drug_food_interactions(cursor)
        _seed_disease_symptoms(cursor)
        _seed_disease_precautions(cursor)
        _seed_food_allergens(cursor)
        _seed_exercises(cursor)
        conn.commit()
        _initialized = True
        print("[SenioCare DB] Cloud database tables initialized successfully")
    except Exception as e:
        conn.rollback()
        print(f"[SenioCare DB] Database initialization error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def _create_tables(cursor) -> None:
    """Create all database tables (idempotent — uses IF NOT EXISTS)."""

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            meal_id        TEXT PRIMARY KEY,
            name_ar        TEXT NOT NULL,
            name_en        TEXT NOT NULL,
            meal_type      TEXT NOT NULL,
            category       TEXT,
            ingredients    TEXT NOT NULL,
            energy_kcal    REAL,
            protein_g      REAL,
            fat_g          REAL,
            carbohydrate_g REAL,
            fiber_g        REAL,
            sodium_mg      REAL,
            sugar_g        REAL,
            prep_time      TEXT,
            notes_ar       TEXT,
            notes_en       TEXT,
            recipe_steps   TEXT,
            recipe_tips    TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS condition_dietary_rules (
            rule_id     TEXT PRIMARY KEY,
            condition   TEXT NOT NULL UNIQUE,
            avoid_high  TEXT,
            prefer_high TEXT,
            avoid_foods TEXT,
            max_values  TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drug_food_interactions (
            interaction_id TEXT PRIMARY KEY,
            drug_name      TEXT NOT NULL,
            food_name      TEXT NOT NULL,
            effect         TEXT NOT NULL,
            severity       TEXT,
            conclusion     TEXT,
            advice         TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disease_symptoms (
            disease_id   TEXT PRIMARY KEY,
            disease_name TEXT NOT NULL,
            symptoms     TEXT NOT NULL,
            severity     TEXT NOT NULL,
            description  TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disease_precautions (
            id         SERIAL PRIMARY KEY,
            disease_id TEXT NOT NULL,
            precaution TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS food_allergens (
            id        SERIAL PRIMARY KEY,
            food_name TEXT NOT NULL,
            allergen  TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            exercise_id      TEXT PRIMARY KEY,
            name_ar          TEXT NOT NULL,
            name_en          TEXT NOT NULL,
            mobility_level   TEXT NOT NULL,
            exercise_type    TEXT NOT NULL,
            duration         TEXT,
            steps            TEXT NOT NULL,
            benefits_ar      TEXT,
            benefits_en      TEXT,
            safety_ar        TEXT,
            safety_en        TEXT,
            avoid_conditions TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medical_reports (
            report_id       TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            report_type     TEXT NOT NULL,
            report_date     TEXT,
            key_findings    TEXT NOT NULL,
            lab_values      TEXT NOT NULL,
            health_summary  TEXT,
            severity_level  TEXT,
            recommendations TEXT NOT NULL,
            scanned_at      TEXT NOT NULL,
            raw_response    TEXT
        )
    """)

    # Indexes for common query patterns
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_meals_type             ON meals(meal_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drug_interactions_drug ON drug_food_interactions(drug_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drug_interactions_food ON drug_food_interactions(food_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_allergens_allergen     ON food_allergens(allergen)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exercises_mobility     ON exercises(mobility_level)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_precautions_disease    ON disease_precautions(disease_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medical_reports_user   ON medical_reports(user_id)")


# ---------------------------------------------------------------------------
# Seed helpers (each reads its own JSON file)
# ---------------------------------------------------------------------------


def _load_seed(filename: str):
    with open(_SEEDS_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _seed_meals(cursor) -> None:
    for m in _load_seed("meals.json"):
        cursor.execute("""
            INSERT INTO meals
                (meal_id, name_ar, name_en, meal_type, category, ingredients,
                 energy_kcal, protein_g, fat_g, carbohydrate_g, fiber_g,
                 sodium_mg, sugar_g, prep_time, notes_ar, notes_en,
                 recipe_steps, recipe_tips)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (meal_id) DO NOTHING
        """, (
            m["meal_id"], m["name_ar"], m["name_en"], m["meal_type"], m["category"],
            json.dumps(m["ingredients"]),
            m["energy_kcal"], m["protein_g"], m["fat_g"], m["carbohydrate_g"],
            m["fiber_g"], m["sodium_mg"], m["sugar_g"], m["prep_time"],
            m["notes_ar"], m["notes_en"],
            json.dumps(m["recipe_steps"]), m["recipe_tips"],
        ))


def _seed_condition_rules(cursor) -> None:
    for r in _load_seed("condition_rules.json"):
        cursor.execute("""
            INSERT INTO condition_dietary_rules
                (rule_id, condition, avoid_high, prefer_high, avoid_foods, max_values)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (rule_id) DO NOTHING
        """, (
            r["rule_id"], r["condition"],
            json.dumps(r["avoid_high"]), json.dumps(r["prefer_high"]),
            json.dumps(r["avoid_foods"]), json.dumps(r["max_values"]),
        ))


def _seed_drug_food_interactions(cursor) -> None:
    for i in _load_seed("drug_food_interactions.json"):
        cursor.execute("""
            INSERT INTO drug_food_interactions
                (interaction_id, drug_name, food_name, effect, severity, conclusion, advice)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (interaction_id) DO NOTHING
        """, (
            i["interaction_id"], i["drug_name"], i["food_name"],
            i["effect"], i["severity"], i["conclusion"], i["advice"],
        ))


def _seed_disease_symptoms(cursor) -> None:
    for d in _load_seed("disease_symptoms.json"):
        cursor.execute("""
            INSERT INTO disease_symptoms
                (disease_id, disease_name, symptoms, severity, description)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (disease_id) DO NOTHING
        """, (
            d["disease_id"], d["disease_name"],
            json.dumps(d["symptoms"]), d["severity"], d["description"],
        ))


def _seed_disease_precautions(cursor) -> None:
    cursor.execute("SELECT COUNT(*) FROM disease_precautions")
    if cursor.fetchone()[0] > 0:
        return

    precautions: dict = _load_seed("disease_precautions.json")
    for disease_id, steps in precautions.items():
        for step in steps:
            cursor.execute(
                "INSERT INTO disease_precautions (disease_id, precaution) VALUES (%s, %s)",
                (disease_id, step),
            )


def _seed_food_allergens(cursor) -> None:
    cursor.execute("SELECT COUNT(*) FROM food_allergens")
    if cursor.fetchone()[0] > 0:
        return

    for food_name, allergen in _load_seed("food_allergens.json"):
        cursor.execute(
            "INSERT INTO food_allergens (food_name, allergen) VALUES (%s, %s)",
            (food_name, allergen),
        )


def _seed_exercises(cursor) -> None:
    for e in _load_seed("exercises.json"):
        cursor.execute("""
            INSERT INTO exercises
                (exercise_id, name_ar, name_en, mobility_level, exercise_type,
                 duration, steps, benefits_ar, benefits_en, safety_ar, safety_en,
                 avoid_conditions)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (exercise_id) DO NOTHING
        """, (
            e["exercise_id"], e["name_ar"], e["name_en"],
            e["mobility_level"], e["exercise_type"], e["duration"],
            json.dumps(e["steps"]),
            e["benefits_ar"], e["benefits_en"],
            e["safety_ar"], e["safety_en"],
            json.dumps(e["avoid_conditions"]),
        ))


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


def reset_database() -> None:
    """Drop and recreate all tables. Use only in testing/dev environments."""
    conn = _connect(_require_database_url())
    cursor = conn.cursor()
    try:
        tables = [
            "disease_precautions", "food_allergens", "medical_reports",
            "exercises", "disease_symptoms", "drug_food_interactions",
            "condition_dietary_rules", "meals",
        ]
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    global _initialized
    _initialized = False
    _initialize_database()
