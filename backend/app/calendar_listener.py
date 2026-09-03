import logging
import threading

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8100
DEFAULT_HOST = "0.0.0.0"


def start_calendar_listener(app, port=DEFAULT_PORT, host=DEFAULT_HOST):
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    )

    def run():
        try:
            server.run()
        except Exception:
            logger.warning("calendar listener stopped", exc_info=True)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
