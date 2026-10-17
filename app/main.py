import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import DAY1_SALT
from app.db import wait_for_db
from app.routers import scoring, system
from app.services.seed import init_db
from app.utils.errors import register_handlers
from app.utils.middleware import BodyLimitMiddleware

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nascon")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DAY1_SALT:
        log.warning("DAY1_SALT is empty - signatures will NOT match the grader!")
    wait_for_db()
    init_db()
    yield


app = FastAPI(title="NaSCon 26 League Platform", lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware)
register_handlers(app)
app.include_router(system.router)
app.include_router(scoring.router)
