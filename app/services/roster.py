"""
Roster, Transfers, Loans & History – Section 5.11
"""

from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.core import AppState
from app.utils.errors import validation_error, not_found, conflict
from app.utils.validation import valid_id, is_int


# We store roster state in AppState for simplicity and speed
# Keys:
#   roster:league:{league_id} → full scenario
#   roster:player:{player_id} → current registration + history


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def roster_setup(body: dict) -> dict:
    league = body.get("league") or {}
    squads = body.get("squads") or []
    players = body.get("players") or []
    matches_in_progress = body.get("matches_in_progress") or []

    league_id = league.get("league_id")
    if not valid_id(league_id):
        raise validation_error(["league.league_id"])

    with SessionLocal() as db:
        # Build internal state
        state = {
            "league": league,
            "squads": {s["squad_id"]: s for s in squads},
            "players": {},
            "matches_in_progress": matches_in_progress,
            "audit": [],          # global audit log for this league
            "next_audit_id": 1,
        }

        for p in players:
            pid = p.get("player_id")
            if not valid_id(pid):
                raise validation_error(["players"])
            state["players"][pid] = {
                "player_id": pid,
                "name": p.get("name", ""),
                "position": p.get("position", ""),
                "squad_id": p.get("squad_id"),
                "role": p.get("role", "substitute"),
                "parent_squad_id": None,
                "registration_type": "transfer",
                "start_date": _today(),
                "loan_end_date": None,
                "history": [],
            }

        # Save
        db.merge(AppState(key=f"roster:league:{league_id}", value=state))
        for pid, pdata in state["players"].items():
            db.merge(AppState(key=f"roster:player:{pid}", value=pdata))
        db.commit()

        squad_counts = {}
        for sid in state["squads"]:
            squad_counts[sid] = sum(1 for p in state["players"].values() if p["squad_id"] == sid)

        return {
            "league_id": league_id,
            "status": "configured",
            "squad_counts": squad_counts,
        }


def roster_transfer(body: dict) -> tuple[int, dict]:
    request_id = body.get("request_id")
    league_id = body.get("league_id")
    player_id = body.get("player_id")
    typ = body.get("type")
    from_squad_id = body.get("from_squad_id")
    to_squad_id = body.get("to_squad_id")
    effective_date = body.get("effective_date")
    loan_end_date = body.get("loan_end_date")
    reason = body.get("reason", "")
    requested_by = body.get("requested_by", "unknown")

    # 1. Schema validation
    if not valid_id(request_id):
        raise validation_error(["request_id"])
    if not valid_id(league_id):
        raise validation_error(["league_id"])
    if not valid_id(player_id):
        raise validation_error(["player_id"])
    if typ not in ("transfer", "loan", "release"):
        raise validation_error(["type"])
    if not valid_id(from_squad_id):
        raise validation_error(["from_squad_id"])
    if typ != "release" and not valid_id(to_squad_id):
        raise validation_error(["to_squad_id"])
    if not isinstance(effective_date, str):
        raise validation_error(["effective_date"])
    if typ == "loan":
        if not isinstance(loan_end_date, str) or loan_end_date <= effective_date:
            raise validation_error(["loan_end_date"])

    with SessionLocal() as db:
        # Idempotency
        existing = db.get(AppState, f"roster:request:{request_id}")
        if existing:
            return 200, existing.value

        league_state = db.get(AppState, f"roster:league:{league_id}")
        if not league_state:
            raise not_found("LEAGUE_NOT_FOUND", f"League {league_id} not found")

        state = league_state.value
        player = state["players"].get(player_id)
        if not player:
            raise not_found("PLAYER_NOT_FOUND", f"Player {player_id} not found")

        if from_squad_id not in state["squads"]:
            raise not_found("SQUAD_NOT_FOUND", f"Squad {from_squad_id} not found")
        if typ != "release" and to_squad_id not in state["squads"]:
            raise not_found("SQUAD_NOT_FOUND", f"Squad {to_squad_id} not found")

        # 3. Cross-tenant check (simplified – assume same tenant for now)
        # 4. Must be in from_squad
        if player["squad_id"] != from_squad_id:
            raise conflict("NOT_IN_SQUAD", "Player is not in the specified from_squad")

        # 5. Transfer window
        window = state["league"].get("transfer_window") or {}
        open_d = window.get("open", "1900-01-01")
        close_d = window.get("close", "2100-12-31")
        if typ in ("transfer", "loan"):
            if not (open_d <= effective_date <= close_d):
                raise conflict("TRANSFER_WINDOW_CLOSED", "Transfer window is closed")

        # 6. Currently on loan?
        if player.get("registration_type") == "loan" and player.get("loan_end_date"):
            if player["loan_end_date"] >= _today():
                raise conflict("PLAYER_ON_LOAN", "Player is currently on loan")

        # 7. Squad full?
        if typ in ("transfer", "loan"):
            max_size = state["league"].get("max_squad_size", 99)
            current_size = sum(1 for p in state["players"].values() if p["squad_id"] == to_squad_id)
            if current_size + 1 > max_size:
                raise conflict("SQUAD_FULL", "Destination squad is full")

        # 8. Min position requirement
        required = state["league"].get("required_positions") or {}
        pos = player.get("position")
        if pos and pos in required:
            count_in_from = sum(
                1 for p in state["players"].values()
                if p["squad_id"] == from_squad_id and p.get("position") == pos
            )
            if count_in_from - 1 < required[pos]:
                raise conflict("MIN_POSITION_VIOLATION", f"Would drop below minimum for position {pos}")

        # Determine if deferred because of in-progress match
        blocking_match_id = None
        state_flag = "active"
        for m in state.get("matches_in_progress", []):
            if m.get("home_squad_id") == from_squad_id or m.get("away_squad_id") == from_squad_id:
                # Player is involved
                state_flag = "deferred_until_match_end"
                blocking_match_id = m.get("match_id")
                break

        # Apply the change
        audit_id = f"au-{state['next_audit_id']:04d}"
        state["next_audit_id"] += 1

        audit_entry = {
            "audit_id": audit_id,
            "action": typ,
            "player_id": player_id,
            "league_id": league_id,
            "from_squad_id": from_squad_id,
            "to_squad_id": to_squad_id if typ != "release" else None,
            "effective_date": effective_date,
            "state": state_flag,
            "who": requested_by,
            "when": _now(),
            "why": reason,
        }

        if typ == "release":
            player["squad_id"] = None
            player["parent_squad_id"] = None
            player["registration_type"] = "release"
            player["loan_end_date"] = None
            registration = None
        elif typ == "loan":
            player["parent_squad_id"] = from_squad_id
            player["squad_id"] = to_squad_id
            player["registration_type"] = "loan"
            player["loan_end_date"] = loan_end_date
            player["role"] = "substitute"
            registration = {
                "player_id": player_id,
                "league_id": league_id,
                "squad_id": to_squad_id,
                "parent_squad_id": from_squad_id,
                "registration_type": "loan",
                "start_date": effective_date,
                "loan_end_date": loan_end_date,
                "role": "substitute",
            }
        else:  # transfer
            player["squad_id"] = to_squad_id
            player["parent_squad_id"] = None
            player["registration_type"] = "transfer"
            player["loan_end_date"] = None
            player["role"] = "substitute"
            registration = {
                "player_id": player_id,
                "league_id": league_id,
                "squad_id": to_squad_id,
                "parent_squad_id": None,
                "registration_type": "transfer",
                "start_date": effective_date,
                "loan_end_date": None,
                "role": "substitute",
            }

        player["history"].append(audit_entry)
        state["audit"].append(audit_entry)

        # Save everything
        db.merge(AppState(key=f"roster:league:{league_id}", value=state))
        db.merge(AppState(key=f"roster:player:{player_id}", value=player))

        response = {
            "request_id": request_id,
            "status": "accepted",
            "state": state_flag,
            "blocking_match_id": blocking_match_id,
            "registration": registration,
            "audit_entry": audit_entry,
        }
        db.merge(AppState(key=f"roster:request:{request_id}", value=response))
        db.commit()

        return 201, response


def roster_history(player_id: str, as_of: str | None = None) -> dict:
    if not valid_id(player_id):
        raise validation_error(["player_id"])

    with SessionLocal() as db:
        pdata = db.get(AppState, f"roster:player:{player_id}")
        if not pdata:
            raise not_found("PLAYER_NOT_FOUND", f"Player {player_id} not found")

        player = pdata.value
        as_of = as_of or _today()

        # Simple history (already stored)
        history = player.get("history", [])

        # Determine current squad on as_of date (simplified)
        current_squad = player.get("squad_id")
        parent = player.get("parent_squad_id")

        # Auto loan return (very simplified)
        if (player.get("registration_type") == "loan" and
            player.get("loan_end_date") and
            player["loan_end_date"] < as_of):
            # Should have returned
            current_squad = player.get("parent_squad_id")
            parent = None

        return {
            "player_id": player_id,
            "as_of": as_of,
            "league_id": history[-1]["league_id"] if history else None,
            "current_squad_id": current_squad,
            "parent_squad_id": parent,
            "history": history,
        }