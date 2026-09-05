import logging

import requests
from fastapi import Body
from fastapi.responses import PlainTextResponse, Response

from .iserv.errors import LoginError, TwoFactorError
from .service import NotConfiguredError

logger = logging.getLogger(__name__)


def _logged(label, call):
    def run():
        try:
            return call()
        except Exception:
            logger.warning("messenger route %s failed", label, exc_info=True)
            raise

    return run


def register_routes(app, service, read_endpoint, write_endpoint, binary_upstream_response):
    @app.get("/api/messenger/rooms")
    def messenger_rooms():
        return read_endpoint(_logged("rooms", service.messenger_rooms))

    @app.get("/api/messenger/room")
    def messenger_room(id: str, before: str = ""):
        return read_endpoint(_logged("room", lambda: service.messenger_room_messages(id, before or None)))

    @app.post("/api/messenger/send")
    def messenger_send(body: dict = Body(...)):
        return write_endpoint(
            _logged("send", lambda: service.messenger_send(body.get("room_id", ""), body.get("text", "")))
        )

    @app.post("/api/messenger/read")
    def messenger_read(body: dict = Body(...)):
        return write_endpoint(
            _logged("read", lambda: service.messenger_mark_read(body.get("room_id", ""), body.get("event_id", ""))),
            fallback="read_failed",
        )

    @app.get("/api/messenger/teachers")
    def messenger_teachers(query: str = ""):
        return read_endpoint(_logged("teachers", lambda: service.messenger_teacher_search(query)))

    @app.post("/api/messenger/room/teacher")
    def messenger_teacher_room(body: dict = Body(...)):
        return write_endpoint(
            _logged("teacher_room", lambda: service.messenger_create_teacher_room(
                body.get("teacher", ""),
                body.get("child_ids") or [],
                bool(body.get("add_other_parents")),
            )),
            fallback="room_failed",
        )

    @app.get("/api/messenger/media/{server_name}/{media_id}")
    def messenger_media(server_name: str, media_id: str):
        try:
            upstream = service.messenger_media(server_name, media_id)
        except (
            NotConfiguredError,
            LoginError,
            TwoFactorError,
            requests.RequestException,
        ) as error:
            logger.warning("messenger media could not be fetched", exc_info=True)
            return binary_upstream_response(error)
        except Exception:
            logger.warning("messenger media was refused before the request", exc_info=True)
            return PlainTextResponse("invalid media", status_code=400)
        headers = {}
        disposition = upstream.headers.get("content-disposition")
        if disposition:
            headers["Content-Disposition"] = disposition
        return Response(
            content=upstream.content,
            media_type=upstream.headers.get("content-type", "application/octet-stream"),
            headers=headers,
        )
