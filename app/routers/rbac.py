from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.services import rbac as rbac_svc
from app.utils.http import json_object

router = APIRouter(prefix="/audit/v1")


@router.post("/rbac-matrix")
def rbac_matrix():
    return rbac_svc.get_rbac_matrix()


# Probe routes
@router.post("/rbac/tenants")
def probe_tenants(credentials: HTTPAuthorizationCredentials = Depends(rbac_svc.security)):
    return rbac_svc.probe("create_tenant", None, credentials)


@router.post("/rbac/leagues/{league_id}/fixtures")
def probe_fixtures(league_id: str, credentials: HTTPAuthorizationCredentials = Depends(rbac_svc.security)):
    return rbac_svc.probe("manage_fixtures", league_id, credentials)


@router.post("/rbac/clubs/{club_id}/roster")
def probe_roster(club_id: str, credentials: HTTPAuthorizationCredentials = Depends(rbac_svc.security)):
    return rbac_svc.probe("manage_roster", club_id, credentials)


@router.post("/rbac/clubs/{club_id}/products")
def probe_products(club_id: str, credentials: HTTPAuthorizationCredentials = Depends(rbac_svc.security)):
    return rbac_svc.probe("manage_products", club_id, credentials)


@router.patch("/rbac/players/{player_id}")
def probe_player(player_id: str, credentials: HTTPAuthorizationCredentials = Depends(rbac_svc.security)):
    return rbac_svc.probe("update_player", player_id, credentials)


@router.get("/rbac/clubs/{club_id}")
def probe_read_club(club_id: str, credentials: HTTPAuthorizationCredentials = Depends(rbac_svc.security)):
    return rbac_svc.probe("read_club", club_id, credentials)


@router.get("/rbac/platform/config")
def probe_platform(credentials: HTTPAuthorizationCredentials = Depends(rbac_svc.security)):
    return rbac_svc.probe("platform_config", None, credentials)