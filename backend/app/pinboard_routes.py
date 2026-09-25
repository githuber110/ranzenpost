import logging

import requests
from fastapi import Body
from fastapi.responses import PlainTextResponse, Response

from .failure import failure_cause
from .iserv.errors import LoginError, TwoFactorError
from .service import NotConfiguredError
from .upstream import binary_upstream_response, read_endpoint, write_endpoint

logger = logging.getLogger(__name__)


def register_routes(app, service):
    @app.get("/api/pinboard")
    def pinboard():
        return read_endpoint(service.pinboard)

    @app.post("/api/pinboard/seen")
    def pinboard_seen(body: dict = Body(...)):
        return write_endpoint(
            lambda: service.mark_pinboard_seen(
                body.get("keys"), body.get("all", False), body.get("unseen", False)
            )
        )

    @app.get("/api/pinboard/attachment/{filename}")
    def pinboard_attachment(filename: str, connection: str = ""):
        try:
            upstream = service.pinboard_attachment(connection, filename)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
            logger.warning("pinboard attachment could not be fetched: %s", failure_cause(error))
            return binary_upstream_response(error)
        except Exception as error:
            logger.warning("pinboard attachment was refused before the request: %s", failure_cause(error))
            return PlainTextResponse("invalid attachment", status_code=400)
        headers = {}
        disposition = upstream.headers.get("content-disposition")
        if disposition:
            headers["Content-Disposition"] = disposition
        return Response(
            content=upstream.content,
            media_type=upstream.headers.get("content-type", "application/octet-stream"),
            headers=headers,
        )
