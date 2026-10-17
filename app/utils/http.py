import json

from fastapi import Request

from app.utils.errors import validation_error


async def json_object(request: Request) -> dict:
    """Parse the body as a JSON object, or raise 400 VALIDATION_ERROR."""
    raw = await request.body()
    try:
        body = json.loads(raw) if raw.strip() else None
    except ValueError:
        raise validation_error(["body"], "Malformed JSON.")
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object.")
    return body
