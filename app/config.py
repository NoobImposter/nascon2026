import hashlib
import os

# DAY1_SALT is read ONLY from the environment, never hard-coded.
DAY1_SALT: str = os.environ.get("DAY1_SALT", "")

_db = os.environ.get("DATABASE_URL", "postgresql://nascon:nascon@db:5432/nascon")
if _db.startswith("postgres://"):
    _db = "postgresql://" + _db[len("postgres://"):]
if _db.startswith("postgresql://"):
    _db = "postgresql+psycopg2://" + _db[len("postgresql://"):]
DATABASE_URL: str = _db

REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# JWT secret: explicit env var, else derived from the salt so all workers agree.
JWT_SECRET: str = os.environ.get("JWT_SECRET") or hashlib.sha256(
    ("jwt|" + DAY1_SALT).encode("utf-8")
).hexdigest()

MAX_BODY_BYTES: int = 1024 * 1024
DEFAULT_SEED: int = 42
DEFAULT_TIE_BREAK = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]
