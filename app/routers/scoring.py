from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.services import events as events_svc
from app.services import leagues as leagues_svc
from app.services import sports as sports_svc
from app.utils.http import json_object
from app.services import fixtures as fixtures_svc
router = APIRouter(prefix="/audit/v1")


@router.post("/fixtures")
async def generate_fixtures(request: Request):
    body = await json_object(request)
    fmt = body.get("format")
    teams = body.get("teams")
    params = body.get("params") or {}

    if fmt == "round_robin":
        result = await run_in_threadpool(fixtures_svc.generate_round_robin, teams, params)
        return result
    else:
        # other formats later
        from app.utils.errors import validation_error
        raise validation_error(["format"], "Unsupported or missing format")


@router.post("/sports")
async def create_sport(request: Request):
    body = await json_object(request)
    config = await run_in_threadpool(sports_svc.create_sport, body)
    return JSONResponse(status_code=201,
                        content={"sport_id": config["sport_id"], "status": "created",
                                 "config": config})


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
