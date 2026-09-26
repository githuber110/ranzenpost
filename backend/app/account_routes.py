import logging

import requests
from fastapi import Body

from . import messages
from .iserv.errors import DataError, LoginError, PasswordError, TwoFactorError
from .service import NotConfiguredError
from .upstream import upstream_code, upstream_write_error, write_endpoint

logger = logging.getLogger(__name__)


def _logged(label, call):
    def run():
        try:
            return call()
        except Exception as error:
            logger.warning("%s failed: %s", label, type(error).__name__)
            raise

    return run


def register_routes(app, service, wizard):
    @app.post("/api/password")
    def change_password(body: dict = Body(...)):
        current = body.get("current", "")
        new = body.get("new", "")
        if not current or not new:
            return messages.result(False, "api.password.missing", error="missing")
        if len(new) < 8:
            return messages.result(False, "api.password.tooShort", error="too_short")
        try:
            outcome = service.change_password(body.get("connection_id") or None, current, new)
        except NotConfiguredError:
            return messages.result(False, "api.notConfigured", error="not_configured")
        except PasswordError:
            logger.warning("password change was refused")
            return messages.result(False, "api.password.rejected", error="rejected")
        except (LoginError, TwoFactorError):
            return messages.result(False, "api.password.authFailed", error="auth_failed")
        except requests.RequestException as error:
            logger.warning("password change failed: %s", type(error).__name__)
            return messages.result(False, "api.network", error="network")
        except DataError as error:
            logger.info("password change refused: %s", error.message_key)
            return upstream_write_error(upstream_code(error), error)
        if outcome == "unverified":
            return messages.result(True, "api.password.unverified")
        return messages.result(True, "api.password.changed")

    @app.post("/api/password/repair")
    def repair_password(body: dict = Body(...)):
        password = body.get("password", "")
        if not password:
            return messages.result(False, "api.repair.missing")
        return write_endpoint(
            _logged("password repair", lambda: service.repair_password(body.get("connection_id") or None, password))
        )

    @app.post("/api/account/disconnect")
    def disconnect_account(body: dict = Body(default=None)):
        result = write_endpoint(
            _logged(
                "account disconnect",
                lambda: service.disconnect((body or {}).get("connection_id") or None),
            )
        )
        if wizard is not None and not service.store.connections():
            wizard.reset()
        return result
