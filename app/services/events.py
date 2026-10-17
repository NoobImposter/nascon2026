from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Match, MatchEvent, Sport
from app.services import scoring
from app.services.validators import COMPENSABLE, validate_event
from app.utils.errors import ApiError, conflict, not_found, validation_error
from app.utils.signing import canonical, sign_record


def _as_dict(r: MatchEvent) -> dict:
    return {"sequence": r.sequence, "event_id": r.event_id, "type": r.type,
            "payload": r.payload, "signature": r.signature}


def _load_events(db, match_id: str) -> list[dict]:
    rows = db.execute(select(MatchEvent).where(MatchEvent.match_id == match_id)
                      .order_by(MatchEvent.sequence)).scalars().all()
    return [_as_dict(r) for r in rows]


def _meta(m: Match) -> dict:
    return {"match_id": m.match_id, "sport_id": m.sport_id, "league_id": m.league_id,
            "home_team_id": m.home_team_id, "away_team_id": m.away_team_id}


def _response(event_id, match_id, etype, seq, sig) -> dict:
    return {"event_id": event_id, "match_id": match_id, "type": etype, "sequence": seq,
            "match_version": seq, "signature": sig}


def _replay(existing: MatchEvent, ev: dict):
    same = canonical(existing.request) == canonical(
        {"match_id": ev["match_id"], "type": ev["type"], "payload": ev["payload"]})
    if not same:
        raise conflict("DUPLICATE_EVENT_ID", f"event_id {ev['event_id']} already used with a "
                       "different body.", event_id=ev["event_id"])
    return 200, _response(existing.event_id, existing.match_id, existing.type,
                          existing.sequence, existing.signature)


def _find_event(db, event_id: str):
    return db.execute(select(MatchEvent).where(MatchEvent.event_id == event_id)).scalar_one_or_none()


def _insert(db, ev: dict, seq: int):
    sig = sign_record(ev["event_id"], ev["payload"])
    db.add(MatchEvent(event_id=ev["event_id"], match_id=ev["match_id"], sequence=seq,
                      type=ev["type"], payload=ev["payload"], signature=sig,
                      request={"match_id": ev["match_id"], "type": ev["type"],
                               "payload": ev["payload"]}))
    db.commit()
    return 201, _response(ev["event_id"], ev["match_id"], ev["type"], seq, sig)


def _append(ev: dict):
    p, t = ev["payload"], ev["type"]
    with SessionLocal() as db:
        existing = _find_event(db, ev["event_id"])
        if existing:
            return _replay(existing, ev)

        if t == "match_init":
            if db.get(Sport, p["sport_id"]) is None:
                raise not_found("SPORT_NOT_FOUND", f"Sport {p['sport_id']} not found.",
                                sport_id=p["sport_id"])
            if db.get(Match, ev["match_id"]) is not None:
                raise conflict("MATCH_EXISTS", f"Match {ev['match_id']} already exists.",
                               match_id=ev["match_id"])
            db.add(Match(match_id=ev["match_id"], sport_id=p["sport_id"],
                         league_id=p.get("league_id"), home_team_id=p["home_team_id"],
                         away_team_id=p["away_team_id"], kind="standalone"))
            return _insert(db, ev, 1)

        # Serialise appends per match: row lock, then rebuild state from the log.
        m = db.execute(select(Match).where(Match.match_id == ev["match_id"])
                       .with_for_update()).scalar_one_or_none()
        if m is None:
            raise not_found("MATCH_NOT_FOUND", f"Match {ev['match_id']} not found.",
                            match_id=ev["match_id"])
        existing = _find_event(db, ev["event_id"])
        if existing:
            return _replay(existing, ev)

        cfg = db.get(Sport, m.sport_id).config
        events = _load_events(db, m.match_id)
        status = scoring.derive_status(events)
        home, away = m.home_team_id, m.away_team_id

        if t == "match_start":
            if status != "upcoming":
                raise conflict("ILLEGAL_TRANSITION", f"Cannot start a match that is {status}.",
                               status=status)
        elif t == "match_end":
            if status != "in_progress":
                raise conflict("ILLEGAL_TRANSITION", f"Cannot end a match that is {status}.",
                               status=status)
            proj = scoring.project(_meta(m), cfg, events)
            if (proj["home"]["score"] == proj["away"]["score"] and not cfg["draw_allowed"]
                    and proj["tiebreak_winner_team_id"] is None):
                raise conflict("TIE_NOT_ALLOWED", "Score is level and draws are not allowed.")
        elif t in ("score", "discipline", "tiebreak_winner"):
            if p["team_id"] not in (home, away):
                raise validation_error(["payload"], "team_id must be the home or away team.")
            if t == "score" and p["event_type"] not in cfg["scoring_events"]:
                raise ApiError(400, "UNKNOWN_EVENT_TYPE",
                               f"event_type {p['event_type']} is not defined for this sport.",
                               {"event_type": p["event_type"]})
            if status != "in_progress":
                raise conflict("MATCH_NOT_IN_PROGRESS", "Match is not in progress.", status=status)
            if t == "score":
                code = scoring.limit_error(cfg, scoring.active_events(events), p["team_id"],
                                           home, away)
                if code:
                    raise conflict(code, "Scoring limit reached for this match.")
        elif t == "compensation":
            target = _find_event(db, p["compensates"])
            if target is None:
                raise not_found("EVENT_NOT_FOUND", f"Event {p['compensates']} not found.",
                                event_id=p["compensates"])
            if (target.match_id != m.match_id or target.type not in COMPENSABLE
                    or p["compensates"] in scoring.compensated_map(events)):
                raise conflict("INVALID_COMPENSATION", "This event cannot be compensated.",
                               event_id=p["compensates"])

        return _insert(db, ev, len(events) + 1)


def append_event(body):
    bad, ev = validate_event(body)
    if bad:
        raise validation_error(bad)
    for _ in range(3):
        try:
            return _append(ev)
        except IntegrityError:
            continue  # lost a creation race; the next pass sees the winner's rows
    raise conflict("DUPLICATE_EVENT_ID", "Concurrent conflicting writes.", event_id=ev["event_id"])


def get_score(match_id: str) -> dict:
    with SessionLocal() as db:
        m = db.get(Match, match_id)
        if m is None:
            raise not_found("MATCH_NOT_FOUND", f"Match {match_id} not found.", match_id=match_id)
        cfg = db.get(Sport, m.sport_id).config
        return scoring.project(_meta(m), cfg, _load_events(db, match_id))


def project_match(db, match_id: str) -> dict:
    """Score projection for one match, rebuilt from the event log (same as get_score)."""
    m = db.get(Match, match_id)
    cfg = db.get(Sport, m.sport_id).config
    return scoring.project(_meta(m), cfg, _load_events(db, match_id))
