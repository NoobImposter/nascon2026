"""Event-sourced score projection. Pure functions: the score is ALWAYS rebuilt from the log.

Branches only on the scoring MODEL (event / innings / round) and on sport CONFIG values.
Never on a sport name or event name.
"""


def derive_status(events: list[dict]) -> str:
    status = "upcoming"
    for e in events:
        if e["type"] == "match_start":
            status = "in_progress"
        elif e["type"] == "match_end":
            status = "completed"
    return status


def compensated_map(events: list[dict]) -> dict:
    """target event_id -> compensating event_id."""
    return {e["payload"]["compensates"]: e["event_id"]
            for e in events if e["type"] == "compensation"}


def active_events(events: list[dict]) -> list[dict]:
    cmap = compensated_map(events)
    return [e for e in events if e["type"] != "compensation" and e["event_id"] not in cmap]


def team_totals(cfg: dict, active: list[dict], team_id: str) -> dict:
    model = cfg["scoring_model"]
    specs = cfg["scoring_events"]
    score = balls = wickets = fair = 0
    for e in active:
        p = e["payload"]
        if p.get("team_id") != team_id:
            continue
        if e["type"] == "score":
            spec = specs.get(p["event_type"], {})
            if model == "event":
                score += spec.get("points", 0)
            elif model == "innings":
                score += spec.get("runs", 0)
                balls += 1 if spec.get("legal_ball") else 0
                wickets += 1 if spec.get("wicket") else 0
            else:
                score += spec.get("rounds", 0)
        elif e["type"] == "discipline":
            fair += p["points"]
    return {"score": score, "balls": balls, "wickets": wickets, "fair_play": fair}


def limit_error(cfg: dict, active: list[dict], team_id: str, home: str, away: str):
    """Config-driven limits for a NEW score event by team_id. Returns an error code or None."""
    model = cfg["scoring_model"]
    per = cfg["periods"]
    if model == "innings":
        t = team_totals(cfg, active, team_id)
        cap_balls = per["innings_per_team"] * per["overs_per_innings"] * per["balls_per_over"]
        cap_wkts = per["innings_per_team"] * per["wickets_per_innings"]
        if t["balls"] >= cap_balls or t["wickets"] >= cap_wkts:
            return "INNINGS_COMPLETE"
    elif model == "round":
        need = (per["best_of"] + 1) // 2
        best = max(team_totals(cfg, active, home)["score"], team_totals(cfg, active, away)["score"])
        if best >= need:
            return "SERIES_ALREADY_DECIDED"
    return None


def active_tiebreak_winner(active: list[dict]):
    winner = None
    for e in active:
        if e["type"] == "tiebreak_winner":
            winner = e["payload"]["team_id"]
    return winner


def project(match: dict, cfg: dict, events: list[dict]) -> dict:
    model = cfg["scoring_model"]
    cmap = compensated_map(events)
    active = active_events(events)
    status = derive_status(events)
    home_id, away_id = match["home_team_id"], match["away_team_id"]
    ht, at = team_totals(cfg, active, home_id), team_totals(cfg, active, away_id)
    tb = active_tiebreak_winner(active)
    if tb not in (home_id, away_id):
        tb = None

    if ht["score"] > at["score"]:
        winner = home_id
    elif at["score"] > ht["score"]:
        winner = away_id
    else:
        winner = tb

    if status != "completed":
        outcome = "pending"
    elif winner == home_id:
        outcome = "home_win"
    elif winner == away_id:
        outcome = "away_win"
    elif cfg["draw_allowed"]:
        outcome = "draw"
    else:
        outcome = "undecided"

    def side(team_id, t):
        if model == "innings":
            bpo = cfg["periods"]["balls_per_over"]
            return {"team_id": team_id, "score": t["score"], "wickets": t["wickets"],
                    "balls": t["balls"], "overs": f"{t['balls'] // bpo}.{t['balls'] % bpo}",
                    "fair_play": t["fair_play"]}
        return {"team_id": team_id, "score": t["score"], "wickets": None, "balls": None,
                "overs": None, "fair_play": t["fair_play"]}

    return {
        "match_id": match["match_id"], "sport_id": match["sport_id"],
        "league_id": match.get("league_id"),
        "status": status, "outcome": outcome, "winner_team_id": winner,
        "tiebreak_winner_team_id": tb,
        "home": side(home_id, ht), "away": side(away_id, at),
        "version": len(events),
        "events": [{"sequence": e["sequence"], "event_id": e["event_id"], "type": e["type"],
                    "payload": e["payload"], "signature": e["signature"],
                    "compensated": e["event_id"] in cmap,
                    "compensated_by": cmap.get(e["event_id"])} for e in events],
    }
