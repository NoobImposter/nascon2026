from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import AppState, League, Match, Sport
from app.services.validators import validate_league
from app.utils.errors import conflict, not_found, validation_error


def register_league(body) -> dict:
    bad, lg = validate_league(body)
    if bad:
        raise validation_error(bad)
    lid = lg["league_id"]
    try:
        with SessionLocal() as db:
            sport = db.get(Sport, lg["sport_id"])
            if sport is None:
                raise not_found("SPORT_NOT_FOUND", f"Sport {lg['sport_id']} not found.",
                                sport_id=lg["sport_id"])
            if db.get(League, lid) is not None:
                raise conflict("LEAGUE_EXISTS", f"League {lid} already exists.", league_id=lid)
            ids = [f["match_id"] for f in lg["fixtures"]]
            if ids:
                used = db.execute(select(Match.match_id).where(Match.match_id.in_(ids))).first()
                if used:
                    raise conflict("MATCH_EXISTS", f"Match {used[0]} already exists.",
                                   match_id=used[0])
            lots = lg["lots_seed"]
            if lots is None:
                st = db.get(AppState, "lots_seed")
                lots = st.value["v"] if st else 42
            db.add(League(
                league_id=lid, tenant_id=None, name=lid, sport_id=lg["sport_id"],
                teams=lg["teams"], points=lg["points"],
                tie_break_order=lg["tie_break_order"] or sport.config["tie_break_order"],
                qualification_spots=lg["qualification_spots"], lots_seed=lots))
            for f in lg["fixtures"]:
                db.add(Match(match_id=f["match_id"], sport_id=lg["sport_id"], league_id=lid,
                             home_team_id=f["home"], away_team_id=f["away"], kind="fixture"))
            db.commit()
    except IntegrityError:
        raise conflict("LEAGUE_EXISTS", f"League {lid} or one of its matches already exists.",
                       league_id=lid)
    return {"league_id": lid, "status": "created", "team_count": len(lg["teams"]),
            "fixture_count": len(lg["fixtures"])}
