import json

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import DEFAULT_SEED
from app.db import SessionLocal
from app.services.seed import reset_all
from app.utils.errors import error_body, validation_error
from app.utils.validation import is_int, valid_id

router = APIRouter()


@router.get("/health")
def health():
    try:
        with SessionLocal() as db:
            tenants = db.execute(text("SELECT count(*) FROM tenants")).scalar()
            sports = db.execute(text("SELECT count(*) FROM sports")).scalar()
        if tenants >= 2 and sports >= 4:
            return {"status": "ok"}
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse(status_code=503,
                        content=error_body("NOT_READY", "Database not reachable or not seeded."))


@router.post("/audit/v1/reset")
async def reset(request: Request):
    raw = await request.body()
    body: dict = {}
    if raw.strip():
        try:
            body = json.loads(raw)
        except ValueError:
            raise validation_error(["body"], "Malformed JSON.")
        if not isinstance(body, dict):
            raise validation_error(["body"], "Body must be a JSON object.")

    bad: list[str] = []
    seed = body.get("seed")
    if seed is None:
        seed = DEFAULT_SEED
    elif not is_int(seed):
        bad.append("seed")

    stock = body.get("stock")
    if stock is None:
        stock = {}
    elif not isinstance(stock, dict) or any(
            not valid_id(k) or not is_int(v) or v < 0 for k, v in stock.items()):
        bad.append("stock")
    if bad:
        raise validation_error(bad)

    return await run_in_threadpool(reset_all, seed, stock)
