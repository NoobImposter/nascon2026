from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Sport
from app.services.validators import validate_sport
from app.utils.errors import conflict, validation_error


def create_sport(body) -> dict:
    bad, config = validate_sport(body)
    if bad:
        raise validation_error(bad)
    sid = config["sport_id"]
    try:
        with SessionLocal() as db:
            if db.get(Sport, sid) is not None:
                raise conflict("SPORT_EXISTS", f"Sport {sid} already exists.", sport_id=sid)
            db.add(Sport(sport_id=sid, name=config["name"], scoring_model=config["scoring_model"],
                         config=config, is_seed=False))
            db.commit()
    except IntegrityError:
        raise conflict("SPORT_EXISTS", f"Sport {sid} already exists.", sport_id=sid)
    return config
