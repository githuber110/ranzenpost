from fastapi import Body
from fastapi.responses import JSONResponse

from . import cancellations, messages


def register_routes(app, cancellation_registry):
    def _cancellation_error(error):
        return JSONResponse(status_code=400, content=messages.result(False, error.message_key))

    @app.get("/api/cancellations")
    def list_cancellations(child: str = ""):
        return cancellation_registry.list(child)

    @app.post("/api/cancellations")
    def create_cancellation(body: dict = Body(...)):
        try:
            return cancellation_registry.create(
                body.get("child_key", ""),
                body.get("date", ""),
                body.get("period"),
            )
        except cancellations.CancellationError as error:
            return _cancellation_error(error)

    @app.delete("/api/cancellations/{cancellation_id}")
    def delete_cancellation(cancellation_id: str):
        try:
            return cancellation_registry.delete(cancellation_id)
        except cancellations.CancellationError as error:
            return _cancellation_error(error)
