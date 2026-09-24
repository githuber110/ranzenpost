from fastapi import Body
from fastapi.responses import JSONResponse

from . import marks, messages


def register_routes(app, marks_registry):
    def _mark_error(error):
        return JSONResponse(status_code=400, content=messages.result(False, error.message_key))

    @app.get("/api/marks")
    def list_marks(child: str = ""):
        return marks_registry.list(child)

    @app.post("/api/marks")
    def create_mark(body: dict = Body(...)):
        try:
            return marks_registry.create(
                body.get("child_key", ""),
                body.get("date", ""),
                body.get("period"),
                body.get("subject_code", ""),
                body.get("name", ""),
            )
        except marks.MarkError as error:
            return _mark_error(error)

    @app.post("/api/marks/{mark_id}")
    def update_mark(mark_id: str, body: dict = Body(...)):
        try:
            return marks_registry.update(
                mark_id,
                date_value=body.get("date"),
                period=body.get("period"),
                subject_code=body.get("subject_code"),
                name=body.get("name"),
            )
        except marks.MarkError as error:
            return _mark_error(error)

    @app.delete("/api/marks/{mark_id}")
    def delete_mark(mark_id: str):
        try:
            return marks_registry.delete(mark_id)
        except marks.MarkError as error:
            return _mark_error(error)
