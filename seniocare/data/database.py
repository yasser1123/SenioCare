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
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")

DATABASE_URL = os.environ.get("APP_DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError(
        "APP_DATABASE_URL is not set. Add it to the root .env file.\n"
        "Example: APP_DATABASE_URL=postgresql://user:pass@host/db?sslmode=require"
    )

_SEEDS_DIR = Path(__file__).parent / "seeds"

# Track whether tables have been initialized this process
_initialized = False


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def get_connection() -> psycopg2.extensions.connection:
    """Return a new psycopg2 connection using RealDictCursor."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


# ---------------------------------------------------------------------------
# Initialization (idempotent)
# ---------------------------------------------------------------------------


def _initialize_database() -> None:
    """Create all tables and populate with seed data (idempotent)."""
    global _initialized
    if _initialized:
        return

    conn = psycopg2.connect(DATABASE_URL)
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
    conn = psycopg2.connect(DATABASE_URL)
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
