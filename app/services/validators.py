"""Pure request validators (no DB, no framework). Each returns (bad_fields, parsed_or_None).

details.fields uses TOP-LEVEL field names (e.g. "periods", "payload").
"""
import re

from app.config import DEFAULT_TIE_BREAK
from app.utils.validation import is_int, valid_id

SPORT_ID_RE = re.compile(r"^[a-z0-9_-]{2,40}$")
EVENT_KEY_RE = re.compile(r"^[a-z0-9_]{1,40}$")
SCORING_MODELS = ("event", "innings", "round")
OVERTIME_POLICIES = ("none", "extra_time", "shootout", "golden_score", "super_over")
TIE_TOKENS = tuple(DEFAULT_TIE_BREAK)
EVENT_TYPES = ("match_init", "match_start", "score", "discipline",
               "tiebreak_winner", "match_end", "compensation")
COMPENSABLE = ("score", "discipline", "tiebreak_winner")


def _pos(v, lo=1) -> bool:
    return is_int(v) and v >= lo


def _str(v, lo=1, hi=200) -> bool:
    return isinstance(v, str) and lo <= len(v) <= hi


def tie_break_ok(v) -> bool:
    return (isinstance(v, list) and all(isinstance(x, str) and x in TIE_TOKENS for x in v)
            and len(set(v)) == len(v))


# ----------------------------------------------------------------- sports
def _periods_ok(model, p) -> bool:
    if not isinstance(p, dict):
        return False
    if model == "event":
        return _pos(p.get("count")) and _pos(p.get("duration_minutes"))
    if model == "innings":
        return all(_pos(p.get(k)) for k in
                   ("innings_per_team", "overs_per_innings", "balls_per_over", "wickets_per_innings"))
    b = p.get("best_of")  # round
    return _pos(b) and b % 2 == 1


def _scoring_events_ok(model, ev) -> bool:
    if not isinstance(ev, dict) or len(ev) < 1:
        return False
    for key, spec in ev.items():
        if not EVENT_KEY_RE.match(key) or not isinstance(spec, dict):
            return False
        if model == "event":
            ok = _pos(spec.get("points"))
        elif model == "innings":
            ok = (_pos(spec.get("runs"), 0) and isinstance(spec.get("legal_ball"), bool)
                  and isinstance(spec.get("wicket"), bool))
        else:
            ok = _pos(spec.get("rounds"))
        if not ok:
            return False
    return True


def _roster_ok(r) -> bool:
    if not isinstance(r, dict):
        return False
    mn, mx, rp = r.get("min_squad_size"), r.get("max_squad_size"), r.get("required_positions")
    if not (_pos(mn) and _pos(mx) and mn <= mx):
        return False
    return isinstance(rp, dict) and all(isinstance(k, str) and _pos(v, 0) for k, v in rp.items())


def _overtime_ok(o) -> bool:
    if not isinstance(o, dict):
        return False
    if not (isinstance(o.get("policy"), str) and o["policy"] in OVERTIME_POLICIES):
        return False
    return "duration_minutes" not in o or o["duration_minutes"] is None or _pos(o["duration_minutes"], 0)


def validate_sport(body):
    if not isinstance(body, dict):
        return ["body"], None
    bad: list[str] = []
    sid = body.get("sport_id")
    if not (isinstance(sid, str) and SPORT_ID_RE.match(sid)):
        bad.append("sport_id")
    if not _str(body.get("name"), 1, 80):
        bad.append("name")
    model = body.get("scoring_model")
    if not (isinstance(model, str) and model in SCORING_MODELS):
        bad.append("scoring_model")
    else:
        if not _periods_ok(model, body.get("periods")):
            bad.append("periods")
        if not _scoring_events_ok(model, body.get("scoring_events")):
            bad.append("scoring_events")
    if not isinstance(body.get("draw_allowed"), bool):
        bad.append("draw_allowed")
    if not _overtime_ok(body.get("overtime")):
        bad.append("overtime")
    tb = body.get("tie_break_order")
    if tb is not None and not tie_break_ok(tb):
        bad.append("tie_break_order")
    if not _roster_ok(body.get("roster")):
        bad.append("roster")
    if bad:
        return bad, None
    config = {
        "sport_id": sid, "name": body["name"], "scoring_model": model,
        "periods": body["periods"], "scoring_events": body["scoring_events"],
        "draw_allowed": body["draw_allowed"], "overtime": body["overtime"],
        "tie_break_order": tb if tb is not None else list(DEFAULT_TIE_BREAK),
        "roster": body["roster"],
    }
    return [], config


# ----------------------------------------------------------------- events
def validate_event(body):
    if not isinstance(body, dict):
        return ["body"], None
    bad: list[str] = []
    if not valid_id(body.get("event_id")):
        bad.append("event_id")
    if not valid_id(body.get("match_id")):
        bad.append("match_id")
    etype = body.get("type")
    if not (isinstance(etype, str) and etype in EVENT_TYPES):
        bad.append("type")
    payload = body.get("payload")
    if payload is None and etype in ("match_start", "match_end"):
        payload = {}
    if not isinstance(payload, dict):
        bad.append("payload")
    elif etype == "match_init":
        ok = (valid_id(payload.get("sport_id")) and valid_id(payload.get("home_team_id"))
              and valid_id(payload.get("away_team_id"))
              and payload.get("home_team_id") != payload.get("away_team_id")
              and ("league_id" not in payload or payload["league_id"] is None
                   or valid_id(payload["league_id"])))
        if not ok:
            bad.append("payload")
    elif etype == "score":
        if not (_str(payload.get("team_id"), 1, 64) and _str(payload.get("event_type"), 1, 64)):
            bad.append("payload")
    elif etype == "discipline":
        if not (_str(payload.get("team_id"), 1, 64) and is_int(payload.get("points"))):
            bad.append("payload")
    elif etype == "tiebreak_winner":
        if not _str(payload.get("team_id"), 1, 64):
            bad.append("payload")
    elif etype == "compensation":
        if not (valid_id(payload.get("compensates"))
                and ("reason" not in payload or payload["reason"] is None
                     or isinstance(payload["reason"], str))):
            bad.append("payload")
    if bad:
        return bad, None
    return [], {"event_id": body["event_id"], "match_id": body["match_id"],
                "type": etype, "payload": payload}


# ----------------------------------------------------------------- leagues
def validate_league(body):
    if not isinstance(body, dict):
        return ["body"], None
    bad: list[str] = []
    if not valid_id(body.get("league_id")):
        bad.append("league_id")
    if not valid_id(body.get("sport_id")):
        bad.append("sport_id")

    teams = body.get("teams")
    teams_ok = (isinstance(teams, list) and 2 <= len(teams) <= 40
                and all(valid_id(t) for t in teams) and len(set(teams)) == len(teams))
    if not teams_ok:
        bad.append("teams")

    fixtures = body.get("fixtures")
    fx_ok = isinstance(fixtures, list)
    if fx_ok:
        seen = set()
        for f in fixtures:
            if not (isinstance(f, dict) and valid_id(f.get("match_id"))
                    and valid_id(f.get("home")) and valid_id(f.get("away"))
                    and f["home"] != f["away"] and f["match_id"] not in seen):
                fx_ok = False
                break
            seen.add(f["match_id"])
            if teams_ok and (f["home"] not in teams or f["away"] not in teams):
                fx_ok = False
                break
    if not fx_ok:
        bad.append("fixtures")

    pts = body.get("points")
    points = {"win": 3, "draw": 1, "loss": 0}
    if pts is not None:
        if not isinstance(pts, dict) or any(k in pts and not is_int(pts[k]) for k in points):
            bad.append("points")
        else:
            for k in points:
                if k in pts:
                    points[k] = pts[k]

    tb = body.get("tie_break_order")
    if tb is not None and not tie_break_ok(tb):
        bad.append("tie_break_order")

    q = body.get("qualification")
    spots = q.get("spots") if isinstance(q, dict) else None
    if not (_pos(spots) and (not teams_ok or spots <= len(teams))):
        bad.append("qualification")

    lots = body.get("lots_seed")
    if lots is not None and not is_int(lots):
        bad.append("lots_seed")
    if bad:
        return bad, None
    return [], {"league_id": body["league_id"], "sport_id": body["sport_id"], "teams": teams,
                "fixtures": [{"match_id": f["match_id"], "home": f["home"], "away": f["away"]}
                             for f in fixtures],
                "points": points, "tie_break_order": tb, "qualification_spots": spots,
                "lots_seed": lots}
