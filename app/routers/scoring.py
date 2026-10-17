from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.services import events as events_svc
from app.services import leagues as leagues_svc
from app.services import sports as sports_svc
from app.utils.http import json_object
from app.services import fixtures as fixtures_svc
router = APIRouter(prefix="/audit/v1")


from app.services import offline as offline_svc

@router.post("/offline-sync")
async def offline_sync(request: Request):
    body = await json_object(request)
    result = await run_in_threadpool(offline_svc.offline_sync, body)
    return result

from app.services import roster as roster_svc
from fastapi.responses import JSONResponse

@router.post("/roster/setup")
async def roster_setup(request: Request):
    body = await json_object(request)
    result = await run_in_threadpool(roster_svc.roster_setup, body)
    return JSONResponse(status_code=201, content=result)


@router.post("/roster/transfer")
async def roster_transfer(request: Request):
    body = await json_object(request)
    status, content = await run_in_threadpool(roster_svc.roster_transfer, body)
    return JSONResponse(status_code=status, content=content)


@router.get("/roster/history/{player_id}")
def roster_history(player_id: str, as_of: str | None = None):
    return roster_svc.roster_history(player_id, as_of)



@router.post("/fixtures")
async def generate_fixtures(request: Request):
    body = await json_object(request)
    result = await run_in_threadpool(fixtures_svc.generate_fixtures, body)
    return result
# @router.post("/fixtures")
# async def generate_fixtures_endpoint(request: Request):
#     body = await json_object(request)
#     result = await run_in_threadpool(fixtures_svc.generate_fixtures, body)
#     return result

# @router.post("/fixtures")
# async def generate_fixtures(request: Request):
#     body = await json_object(request)
#     fmt = body.get("format")
#     teams = body.get("teams")
#     params = body.get("params") or {}

#     if fmt == "round_robin":
#         result = await run_in_threadpool(fixtures_svc.generate_round_robin, teams, params)
#         return result
#     else:
#         # other formats later
#         from app.utils.errors import validation_error
#         raise validation_error(["format"], "Unsupported or missing format")



from app.services import standings as standings_svc

@router.get("/standings/{league_id}")
def get_standings(league_id: str):
    return standings_svc.get_standings(league_id)

@router.post("/sports")
async def create_sport(request: Request):
    body = await json_object(request)
    config = await run_in_threadpool(sports_svc.create_sport, body)
    return JSONResponse(status_code=201,
                        content={"sport_id": config["sport_id"], "status": "created",
                                 "config": config})

from app.services import store as store_svc
from fastapi.responses import JSONResponse

@router.post("/checkout")
async def checkout(request: Request):
    body = await json_object(request)
    status, content = await run_in_threadpool(store_svc.checkout, body)
    return JSONResponse(status_code=status, content=content)


@router.get("/inventory/{variant_id}")
def inventory(variant_id: str):
    return store_svc.get_inventory(variant_id)


@router.post("/leagues")
async def register_league(request: Request):
    body = await json_object(request)
    result = await run_in_threadpool(leagues_svc.register_league, body)
    return JSONResponse(status_code=201, content=result)


@router.post("/events")
async def append_event(request: Request):
    body = await json_object(request)
    status, content = await run_in_threadpool(events_svc.append_event, body)
    return JSONResponse(status_code=status, content=content)


@router.get("/score/{match_id}")
def get_score(match_id: str):
    return events_svc.get_score(match_id)
