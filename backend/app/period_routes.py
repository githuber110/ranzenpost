from datetime import timedelta

from fastapi import Body
from fastapi.responses import JSONResponse

from . import holidays, messages, own_entries
from .iserv.errors import DataError
from .upstream import NETWORK, upstream_error

PERIODS_LOOKAHEAD_DAYS = 400
PERIOD_ADDED_KEY = "api.periods.added"
PERIOD_SAVED_KEY = "api.periods.saved"
PERIOD_RESET_KEY = "api.periods.reset"
PERIOD_REMOVED_KEY = "api.periods.removed"
PERIODS_RESET_KEY = "api.periods.resetAll"
ENTRY_ADDED_KEY = "api.ownEntries.added"
ENTRY_SAVED_KEY = "api.ownEntries.saved"
ENTRY_DELETED_KEY = "api.ownEntries.deleted"
ENTRIES_ROLLED_KEY = "api.ownEntries.rolledOver"
ENTRIES_ROLLED_PARTLY_KEY = "api.ownEntries.rolledOverPartly"


def register_routes(app, service, holiday_source):
    def _holiday_periods(config, first):
        payload = holiday_source.range_info(first, first + timedelta(days=PERIODS_LOOKAHEAD_DAYS), config)
        return payload.get("periods") if payload.get("status") == holidays.STATUS_OK else []

    def _periods_limits(config):
        today = holidays.berlin_today()
        periods = _holiday_periods(config, today)
        until_max, summer_start = own_entries.until_limit(today, periods)
        return today, until_max, summer_start, periods

    def _periods_body(connection, message_key=None, message_vars=None, **extra):
        config = connection.store.load_config()
        today, until_max, summer_start, periods = _periods_limits(config)
        body = own_entries.view(config, connection.id, today, until_max, summer_start, periods, lambda first: _holiday_periods(config, first))
        if message_key:
            body.update(messages.result(True, message_key, message_vars))
        body.update(extra)
        return body

    def _periods_call(connection_id, action, message_key):
        try:
            connection = service.known_connection(connection_id)
        except DataError as error:
            return JSONResponse(status_code=404, content=upstream_error(NETWORK, error))
        try:
            extra = action(connection) or {}
        except own_entries.OwnEntryError as error:
            status = 404 if error.message_key == own_entries.ERROR_NOT_FOUND else 400
            return JSONResponse(status_code=status, content=messages.result(False, error.message_key, error.variables))
        return _periods_body(connection, message_key, **extra)

    def _entry_limits(connection):
        config = connection.store.load_config()
        today, until_max = _periods_limits(config)[:2]
        return today, until_max, lambda first: own_entries.until_limit(first, _holiday_periods(config, first))[0]

    @app.get("/api/connections/{connection_id}/periods")
    def period_grid_view(connection_id: str):
        return _periods_call(connection_id, lambda connection: None, None)

    @app.post("/api/connections/{connection_id}/periods/lessons")
    def add_period_lesson(connection_id: str, body: dict = Body(...)):
        return _periods_call(
            connection_id,
            lambda connection: {"number": own_entries.add_lesson(connection.store, body.get("start"), body.get("duration"))},
            PERIOD_ADDED_KEY,
        )

    @app.post("/api/connections/{connection_id}/periods/lessons/{number}")
    def set_period_lesson(connection_id: str, number: int, body: dict = Body(...)):
        return _periods_call(
            connection_id,
            lambda connection: own_entries.set_lesson(connection.store, number, body.get("start"), body.get("duration")),
            PERIOD_SAVED_KEY,
        )

    @app.post("/api/connections/{connection_id}/periods/lessons/{number}/reset")
    def reset_period_lesson(connection_id: str, number: int):
        return _periods_call(connection_id, lambda connection: own_entries.reset_lessons(connection.store, [number]), PERIOD_RESET_KEY)

    @app.delete("/api/connections/{connection_id}/periods/lessons/{number}")
    def remove_period_lesson(connection_id: str, number: int):
        return _periods_call(connection_id, lambda connection: own_entries.remove_lesson(connection.store, number), PERIOD_REMOVED_KEY)

    @app.post("/api/connections/{connection_id}/periods/reset")
    def reset_period_grid(connection_id: str):
        return _periods_call(connection_id, lambda connection: own_entries.reset_lessons(connection.store), PERIODS_RESET_KEY)

    @app.post("/api/connections/{connection_id}/own-entries")
    def create_own_entry(connection_id: str, body: dict = Body(...)):
        def action(connection):
            today, until_max, later_limit = _entry_limits(connection)
            return {"entry_id": own_entries.create(connection.store, body, today, until_max, later_limit=later_limit)["id"]}

        return _periods_call(connection_id, action, ENTRY_ADDED_KEY)

    @app.post("/api/connections/{connection_id}/own-entries/rollover")
    def roll_own_entries(connection_id: str):
        try:
            connection = service.known_connection(connection_id)
        except DataError as error:
            return JSONResponse(status_code=404, content=upstream_error(NETWORK, error))
        config = connection.store.load_config()
        today, _, _, periods = _periods_limits(config)
        try:
            outcome = own_entries.rollover(connection.store, today, periods, lambda first: _holiday_periods(config, first))
        except own_entries.OwnEntryError as error:
            return JSONResponse(status_code=400, content=messages.result(False, error.message_key, error.variables))
        key = ENTRIES_ROLLED_PARTLY_KEY if outcome["skipped"] else ENTRIES_ROLLED_KEY
        return _periods_body(connection, key, {"count": outcome["copied"], "skipped": outcome["skipped"]}, **outcome)

    @app.post("/api/connections/{connection_id}/own-entries/{entry_id}")
    def update_own_entry(connection_id: str, entry_id: str, body: dict = Body(...)):
        def action(connection):
            today, until_max, later_limit = _entry_limits(connection)
            return {"entry_id": own_entries.update(connection.store, entry_id, body, today, until_max, later_limit=later_limit)["id"]}

        return _periods_call(connection_id, action, ENTRY_SAVED_KEY)

    @app.delete("/api/connections/{connection_id}/own-entries/{entry_id}")
    def delete_own_entry(connection_id: str, entry_id: str):
        return _periods_call(connection_id, lambda connection: own_entries.delete(connection.store, entry_id), ENTRY_DELETED_KEY)
