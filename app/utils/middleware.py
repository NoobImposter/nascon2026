from fastapi.responses import JSONResponse

from app.config import MAX_BODY_BYTES
from app.utils.errors import error_body


class _TooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Pure ASGI middleware: bodies over 1 MB -> 413 PAYLOAD_TOO_LARGE."""

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def _reject(self, scope, receive, send):
        # Drain the request body first so the client doesn't hit a broken pipe.
        while True:
            msg = await receive()
            if msg["type"] != "http.request" or not msg.get("more_body"):
                break
        resp = JSONResponse(status_code=413, content=error_body(
            "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.", {}))
        await resp(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        cl = dict(scope["headers"]).get(b"content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            return await self._reject(scope, receive, send)

        received = 0
        started = False

        async def counting_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLarge()
            return msg

        async def tracking_send(msg):
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if not started:
                await self._reject(scope, receive, send)
