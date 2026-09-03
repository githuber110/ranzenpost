import requests
from fastapi import Body
from fastapi.responses import PlainTextResponse, Response

from .iserv.errors import LoginError, TwoFactorError
from .service import NotConfiguredError


def register_routes(app, service, read_endpoint, write_endpoint, binary_upstream_response):
    @app.get("/api/messenger/rooms")
    def messenger_rooms():
        return read_endpoint(service.messenger_rooms)

    @app.get("/api/messenger/room")
    def messenger_room(id: str, before: str = ""):
        return read_endpoint(lambda: service.messenger_room_messages(id, before or None))

    @app.post("/api/messenger/send")
    def messenger_send(body: dict = Body(...)):
        return write_endpoint(
            lambda: service.messenger_send(body.get("room_id", ""), body.get("text", ""))
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
            return binary_upstream_response(error)
        except Exception:
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
