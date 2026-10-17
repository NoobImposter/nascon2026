from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (AppState, Base, Club, DiscountCode, League, Player, Product, Sport,
                        Tenant, User, Variant)
from app.services import seed_data as sd
from app.utils.security import hash_password

RESET_LOCK = 727001


def seed_baseline(db: Session, seed: int = 42, stock_override: dict | None = None) -> dict:
    """Insert baseline rows. Returns the effective stock map."""
    stock = dict(sd.DEFAULT_STOCK)
    stock.update(stock_override or {})

    db.add_all([Tenant(**t) for t in sd.TENANTS])
    db.add_all([
        Sport(sport_id=sid, name=cfg["name"], scoring_model=cfg["scoring_model"],
              config=cfg, is_seed=True)
        for sid, cfg in sd.SEED_SPORTS.items()
    ])
    db.add_all([
        League(league_id=lid, tenant_id=tid, name=name, sport_id="football", teams=[],
               points={"win": 3, "draw": 1, "loss": 0},
               tie_break_order=list(sd.SEED_SPORTS["football"]["tie_break_order"]),
               qualification_spots=1, lots_seed=seed)
        for lid, tid, name in sd.LEAGUES
    ])
    db.add_all([
        Club(club_id=cid, tenant_id=tid, name=name, profile={
            "home_venue": {"name": f"{name} Ground", "lat": lat, "lng": lng},
            "social": {"instagram": f"@{cid}", "twitter": f"@{cid}"},
            "staff": [{"role": "coach", "name": "Coach"}, {"role": "manager", "name": "Manager"},
                      {"role": "physio", "name": "Physio"}],
            "history": [],
        })
        for cid, tid, name, lat, lng in sd.CLUBS
    ])
    db.add_all([Player(player_id=p, club_id=c, tenant_id=t, name=n, position=pos)
                for p, c, t, n, pos in sd.PLAYERS])
    db.add_all([User(password_hash=hash_password(sd.DEMO_PASSWORD), **u) for u in sd.DEMO_USERS])
    db.add(Product(**sd.PRODUCT))
    for vid, qty in stock.items():
        db.add(Variant(variant_id=vid, product_id=sd.PRODUCT["product_id"],
                       attributes=sd.VARIANT_ATTRS.get(vid, {}), price_minor=sd.PRICE_MINOR,
                       currency="PKR", stock=qty, reserved=0))
    db.add(DiscountCode(code="WELCOME10", percent=10))
    db.add(AppState(key="lots_seed", value={"v": seed}))
    db.flush()
    return stock


def reset_all(seed: int, stock_override: dict) -> dict:
    from app.db import SessionLocal
    with SessionLocal() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": RESET_LOCK})
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        stock = seed_baseline(db, seed, stock_override)
        db.commit()
    return {
        "status": "reset_complete",
        "seed": seed,
        "sports": list(sd.SEED_SPORTS.keys()),
        "tenants": [t["id"] for t in sd.TENANTS],
        "stock": stock,
    }


def init_db() -> None:
    """Create tables and seed once (safe with multiple workers via advisory lock)."""
    from app.db import SessionLocal
    with SessionLocal() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": RESET_LOCK})
        Base.metadata.create_all(bind=db.connection())
        if db.query(Tenant).count() == 0:
            seed_baseline(db, 42, None)
        db.commit()
