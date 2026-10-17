"""
Standings engine – Section 5.10
Recomputes everything from the event logs on every call.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.core import League, Match, MatchEvent, Sport
from app.services.events import project_match   # we will use the existing projection
from app.utils.errors import not_found
from app.utils.signing import lots_key
from app.config import DEFAULT_TIE_BREAK


def get_standings(league_id: str) -> dict:
    with SessionLocal() as db:
        league = db.get(League, league_id)
        if not league:
            raise not_found("LEAGUE_NOT_FOUND", f"League {league_id} not found")

        sport = db.get(Sport, league.sport_id)
        if not sport:
            raise not_found("SPORT_NOT_FOUND", f"Sport {league.sport_id} not found")

        teams: list[str] = list(league.teams or [])
        points_cfg = league.points or {"win": 3, "draw": 1, "loss": 0}
        tie_break_order = league.tie_break_order or sport.config.get("tie_break_order") or DEFAULT_TIE_BREAK
        lots_seed = league.lots_seed
        qualification_spots = league.qualification_spots or 1

        # Collect all completed matches for this league
        matches = db.query(Match).filter(Match.league_id == league_id).all()

        # Stats containers
        stats = {
            t: {
                "played": 0, "won": 0, "drawn": 0, "lost": 0,
                "scored": 0, "conceded": 0, "diff": 0.0,
                "points": 0, "fair_play": 0,
                "remaining": 0,
            }
            for t in teams
        }

        # Head-to-head matrix
        h2h = {a: {b: {"played": 0, "points": 0, "scored": 0, "conceded": 0} for b in teams if b != a} for a in teams}

        completed_matches = []

        for match in matches:
            projection = project_match(db, match.match_id)  # existing function from events service

            if projection["status"] != "completed" or projection["outcome"] == "undecided":
                # Still remaining
                if projection["home"]["team_id"] in stats:
                    stats[projection["home"]["team_id"]]["remaining"] += 1
                if projection["away"]["team_id"] in stats:
                    stats[projection["away"]["team_id"]]["remaining"] += 1
                continue

            home_id = projection["home"]["team_id"]
            away_id = projection["away"]["team_id"]
            home_score = projection["home"]["score"] or 0
            away_score = projection["away"]["score"] or 0
            home_fp = projection["home"].get("fair_play") or 0
            away_fp = projection["away"].get("fair_play") or 0

            # Update basic stats
            for tid, scored, conceded, fp in [
                (home_id, home_score, away_score, home_fp),
                (away_id, away_score, home_score, away_fp),
            ]:
                if tid not in stats:
                    continue
                stats[tid]["played"] += 1
                stats[tid]["scored"] += scored
                stats[tid]["conceded"] += conceded
                stats[tid]["fair_play"] += fp

            # Outcome
            outcome = projection["outcome"]
            if outcome == "home_win":
                stats[home_id]["won"] += 1
                stats[away_id]["lost"] += 1
                stats[home_id]["points"] += points_cfg.get("win", 3)
                stats[away_id]["points"] += points_cfg.get("loss", 0)
            elif outcome == "away_win":
                stats[away_id]["won"] += 1
                stats[home_id]["lost"] += 1
                stats[away_id]["points"] += points_cfg.get("win", 3)
                stats[home_id]["points"] += points_cfg.get("loss", 0)
            elif outcome == "draw":
                stats[home_id]["drawn"] += 1
                stats[away_id]["drawn"] += 1
                stats[home_id]["points"] += points_cfg.get("draw", 1)
                stats[away_id]["points"] += points_cfg.get("draw", 1)

            # Head-to-head
            if home_id in h2h and away_id in h2h[home_id]:
                h2h[home_id][away_id]["played"] += 1
                h2h[home_id][away_id]["scored"] += home_score
                h2h[home_id][away_id]["conceded"] += away_score
                if outcome == "home_win":
                    h2h[home_id][away_id]["points"] += points_cfg.get("win", 3)
                elif outcome == "draw":
                    h2h[home_id][away_id]["points"] += points_cfg.get("draw", 1)

                h2h[away_id][home_id]["played"] += 1
                h2h[away_id][home_id]["scored"] += away_score
                h2h[away_id][home_id]["conceded"] += home_score
                if outcome == "away_win":
                    h2h[away_id][home_id]["points"] += points_cfg.get("win", 3)
                elif outcome == "draw":
                    h2h[away_id][home_id]["points"] += points_cfg.get("draw", 1)

            completed_matches.append(projection)

        # Calculate diff according to scoring model
        model = sport.scoring_model
        for t, s in stats.items():
            if model == "innings":
                # Net Run Rate – simplified (full version needs balls/overs)
                # For now use scored - conceded as placeholder; improve later if needed
                s["diff"] = round(s["scored"] - s["conceded"], 3)
            else:
                s["diff"] = s["scored"] - s["conceded"]

        # ---------- Ranking with full tie-break ----------
        def resolve(group: list[str]) -> list[str]:
            if len(group) <= 1:
                return group

            for criterion in tie_break_order + ["draw_lots"]:
                values = {}
                for t in group:
                    if criterion == "h2h_points":
                        values[t] = sum(h2h[t][o]["points"] for o in group if o != t)
                    elif criterion == "h2h_diff":
                        values[t] = sum(h2h[t][o]["scored"] - h2h[t][o]["conceded"] for o in group if o != t)
                    elif criterion == "overall_diff":
                        values[t] = stats[t]["diff"]
                    elif criterion == "scored":
                        values[t] = stats[t]["scored"]
                    elif criterion == "fair_play":
                        values[t] = stats[t]["fair_play"]
                    elif criterion == "draw_lots":
                        values[t] = lots_key(lots_seed, league_id, t)
                    else:
                        values[t] = 0

                # Group by value
                from collections import defaultdict
                buckets = defaultdict(list)
                for t in group:
                    buckets[values[t]].append(t)

                if len(buckets) == 1:
                    continue  # still fully tied

                # Sort buckets (higher better, except draw_lots which is ascending hex)
                if criterion == "draw_lots":
                    ordered_keys = sorted(buckets.keys())  # ascending = better
                else:
                    ordered_keys = sorted(buckets.keys(), reverse=True)

                result = []
                for k in ordered_keys:
                    result.extend(resolve(buckets[k]))
                return result

            return group  # fallback

        # Initial sort by points
        by_points = defaultdict(list)
        for t in teams:
            by_points[stats[t]["points"]].append(t)

        ordered = []
        for pts in sorted(by_points.keys(), reverse=True):
            ordered.extend(resolve(by_points[pts]))

        # Build table + qualification status
        table = []
        W = points_cfg.get("win", 3)

        for rank, t in enumerate(ordered, 1):
            s = stats[t]
            max_possible = s["points"] + W * s["remaining"]

            # Clinched / Eliminated / still_possible
            better_or_equal = sum(1 for other in teams if other != t and stats[other]["points"] + W * stats[other]["remaining"] >= s["points"])
            worse = sum(1 for other in teams if other != t and stats[other]["points"] > max_possible)

            if better_or_equal < qualification_spots:
                status = "clinched"
            elif worse >= qualification_spots:
                status = "eliminated"
            else:
                status = "still_possible"

            table.append({
                "rank": rank,
                "team_id": t,
                "played": s["played"],
                "won": s["won"],
                "drawn": s["drawn"],
                "lost": s["lost"],
                "scored": s["scored"],
                "conceded": s["conceded"],
                "diff": s["diff"],
                "points": s["points"],
                "fair_play": s["fair_play"],
                "status": status,
                "resolved_by": None,  # can be improved later
            })

        return {
            "league_id": league_id,
            "sport_id": league.sport_id,
            "qualification_spots": qualification_spots,
            "table": table,
            "h2h": h2h,
        }