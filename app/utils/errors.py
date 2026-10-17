from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error_body(code: str, message: str = "", details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message or code, "details": details or {}}}


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str = "",
                 details: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message or code
        self.details = details or {}
        self.headers = headers
        super().__init__(self.message)


def validation_error(fields: list[str], message: str = "Request validation failed.") -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message, {"fields": list(fields)})


def not_found(code: str, message: str, **details: Any) -> ApiError:
    return ApiError(404, code, message, details)


def conflict(code: str, message: str, **details: Any) -> ApiError:
    return ApiError(409, code, message, details)


def forbidden(message: str = "Not allowed.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def unauthenticated(message: str = "Missing or invalid token.") -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", message)


async def _api_error(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code,
                        content=error_body(exc.code, exc.message, exc.details),
                        headers=exc.headers)


async def _request_validation(request: Request, exc: RequestValidationError):
    fields: list[str] = []
    for err in exc.errors():
        if err.get("type") == "json_invalid":
            name = "body"
        else:
            parts = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            name = ".".join(parts) if parts else "body"
        if name not in fields:
            fields.append(name)
    return JSONResponse(status_code=400,
                        content=error_body("VALIDATION_ERROR", "Request validation failed.",
                                           {"fields": fields}))


async def _http_error(request: Request, exc: StarletteHTTPException):
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    status = 400 if exc.status_code == 422 else exc.status_code
    if status == 400:
        code = "VALIDATION_ERROR"
    return JSONResponse(status_code=status,
                        content=error_body(code, str(exc.detail), {}),
                        headers=getattr(exc, "headers", None))


async def _unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500,
                        content=error_body("INTERNAL_ERROR", "Unexpected server error.", {}))


def register_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _request_validation)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)
