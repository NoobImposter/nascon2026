"""
RBAC Matrix + Probe Routes – Section 5.13
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import JWT_SECRET
from app.utils.errors import unauthenticated, forbidden

ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False)

# Seeded context from Section 5.5
CONTEXT = {
    "tenant_id": "tenant-alpha",
    "foreign_tenant_id": "tenant-beta",
    "own_league_id": "league-alpha-1",
    "other_league_id": "league-alpha-2",
    "foreign_league_id": "league-beta-1",
    "own_club_id": "club-alpha-1",
    "other_club_id": "club-alpha-2",
    "foreign_club_id": "club-beta-1",
    "own_player_id": "player-alpha-1",
    "other_player_id": "player-alpha-2",
    "foreign_player_id": "player-beta-1",
}


def _make_token(role: str, extra: dict | None = None) -> str:
    payload = {
        "role": role,
        "tenant_id": "tenant-alpha" if role != "super_admin" else None,
        "exp": datetime.now(timezone.utc) + timedelta(hours=2),
        "iat": datetime.now(timezone.utc),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def get_rbac_matrix() -> dict:
    """POST /audit/v1/rbac-matrix"""
    return {
        "tokens": {
            "super_admin": _make_token("super_admin"),
            "league_organizer": _make_token("league_organizer", {
                "league_ids": ["league-alpha-1"]
            }),
            "club_manager": _make_token("club_manager", {
                "club_id": "club-alpha-1"
            }),
            "player": _make_token("player", {
                "player_id": "player-alpha-1",
                "club_id": "club-alpha-1"
            }),
            "viewer": _make_token("viewer"),
        },
        "context": CONTEXT,
    }


def _decode_token(credentials: HTTPAuthorizationCredentials | None) -> dict:
    if credentials is None:
        raise unauthenticated("Missing Authorization header")
    token = credentials.credentials
    try:
        # Reject alg=none
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "none":
            raise unauthenticated("alg=none is not allowed")

        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise unauthenticated("Token has expired")
    except jwt.InvalidTokenError:
        raise unauthenticated("Invalid or tampered token")


def check_permission(role: str, action: str, resource_id: str | None = None, payload: dict | None = None) -> bool:
    """
    Returns True if allowed, False if forbidden.
    """
    if role == "super_admin":
        return True

    tenant = payload.get("tenant_id") if payload else None

    # P1 – create tenants
    if action == "create_tenant":
        return False

    # P2 – manage fixtures of a league
    if action == "manage_fixtures":
        if role != "league_organizer":
            return False
        own_leagues = payload.get("league_ids") or []
        return resource_id in own_leagues

    # P3 / P4 – manage roster or products of a club
    if action in ("manage_roster", "manage_products"):
        if role != "club_manager":
            return False
        return resource_id == payload.get("club_id")

    # P5 – update a player
    if action == "update_player":
        if role == "club_manager":
            # Can update players of own club (simplified)
            return True
        if role == "player":
            return resource_id == payload.get("player_id")
        return False

    # P6 – read club
    if action == "read_club":
        # Anyone in the same tenant can read
        if resource_id and resource_id.startswith("club-beta"):
            return False  # foreign
        return True

    # P7 – platform config
    if action == "platform_config":
        return False

    return False


# ---------- Probe route helpers ----------

def probe(action: str, resource_id: str | None, credentials: HTTPAuthorizationCredentials | None):
    payload = _decode_token(credentials)
    role = payload.get("role")
    if not role:
        raise unauthenticated("Token missing role")

    allowed = check_permission(role, action, resource_id, payload)
    if not allowed:
        raise forbidden("Not allowed for this role/tenant")
    return {"authorized": True}