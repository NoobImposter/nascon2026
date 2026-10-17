from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    logo_url: Mapped[str] = mapped_column(String(300), default="")
    primary_color: Mapped[str] = mapped_column(String(16), default="#000000")
    secondary_color: Mapped[str] = mapped_column(String(16), default="#ffffff")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(32))
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    league_ids: Mapped[list] = mapped_column(JSONB, default=list)
    club_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    player_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Sport(Base):
    __tablename__ = "sports"
    sport_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    scoring_model: Mapped[str] = mapped_column(String(16))
    config: Mapped[dict] = mapped_column(JSONB)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)


class League(Base):
    __tablename__ = "leagues"
    league_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    sport_id: Mapped[str] = mapped_column(String(64))
    teams: Mapped[list] = mapped_column(JSONB, default=list)
    points: Mapped[dict] = mapped_column(JSONB, default=dict)
    tie_break_order: Mapped[list] = mapped_column(JSONB, default=list)
    qualification_spots: Mapped[int] = mapped_column(Integer, default=1)
    lots_seed: Mapped[int] = mapped_column(Integer, default=42)


class Club(Base):
    __tablename__ = "clubs"
    club_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(120))
    profile: Mapped[dict] = mapped_column(JSONB, default=dict)


class Player(Base):
    __tablename__ = "players"
    player_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    club_id: Mapped[str] = mapped_column(String(64), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[str] = mapped_column(String(32), default="")


class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    club_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32), default="apparel")


class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (
        CheckConstraint("stock >= 0", name="ck_variant_stock_nonneg"),
        CheckConstraint("reserved >= 0", name="ck_variant_reserved_nonneg"),
    )
    variant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(64), index=True)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    price_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    stock: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)


class DiscountCode(Base):
    __tablename__ = "discount_codes"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    percent: Mapped[int] = mapped_column(Integer)


class AppState(Base):
    __tablename__ = "app_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)


class Match(Base):
    """A match stream. Status/score are NOT stored: they are projected from match_events."""
    __tablename__ = "matches"
    match_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sport_id: Mapped[str] = mapped_column(String(64))
    league_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    home_team_id: Mapped[str] = mapped_column(String(64))
    away_team_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), default="standalone")  # fixture | standalone


class MatchEvent(Base):
    """Append-only event log. Rows are inserted, never updated or deleted."""
    __tablename__ = "match_events"
    __table_args__ = (UniqueConstraint("match_id", "sequence", name="uq_match_event_seq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    match_id: Mapped[str] = mapped_column(String(64), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    request: Mapped[dict] = mapped_column(JSONB)   # {"match_id","type","payload"} for idempotency
    payload: Mapped[dict] = mapped_column(JSONB)
    signature: Mapped[str] = mapped_column(String(64))
