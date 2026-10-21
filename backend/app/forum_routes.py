from fastapi import Body

from .upstream import read_endpoint, write_endpoint


def register_routes(app, service):
    @app.get("/api/forums")
    def forums():
        return read_endpoint(service.forums)

    @app.post("/api/forums/read")
    def forums_read(body: dict = Body(...)):
        return write_endpoint(
            lambda: service.forum_mark_read(str(body.get("connection_id") or ""), body.get("confirmed") is True),
            "act_failed",
        )

    @app.get("/api/texts")
    def texts():
        return read_endpoint(service.texts)

    @app.get("/api/infodisplay")
    def infodisplay():
        return read_endpoint(service.infodisplay)

    @app.get("/api/whiteboards")
    def whiteboards():
        return read_endpoint(service.whiteboards)
