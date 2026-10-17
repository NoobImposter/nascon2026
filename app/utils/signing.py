import hashlib
import hmac
import json

from app.config import DAY1_SALT


def canonical(obj) -> str:
    """Section 5.3 canonical JSON."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(salt: str, id_: str, payload_obj) -> str:
    msg = (id_ + "|" + canonical(payload_obj)).encode("utf-8")
    return hmac.new(salt.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def sign_record(id_: str, payload_obj) -> str:
    """Sign with the team's DAY1_SALT (from the environment)."""
    return sign(DAY1_SALT, id_, payload_obj)


def lots_key(seed: int, league_id: str, team_id: str) -> str:
    return hashlib.sha256(f"{seed}|{league_id}|{team_id}".encode("utf-8")).hexdigest()
