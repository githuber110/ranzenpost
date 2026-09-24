import logging
import os
import threading

from . import diagnostics, integration, logbuffer, logfile, namebook
from .holidays import HolidayCalendar
from .iserv_prober import IServProber
from .server import create_app
from .service import IServService
from .store import Store
from .subscriptions import SubscriptionRegistry
from .wizard import Wizard

logging.basicConfig(level=logging.INFO, format=logbuffer.LOG_FORMAT)
logbuffer.install()
DATA_DIR = os.environ.get("ISERV_DATA_DIR", "/data")
logfile.install(DATA_DIR, scrub=diagnostics.scrub_line)
threading.Thread(target=logfile.mark_start, args=(integration.addon_version, DATA_DIR), daemon=True).start()

store = Store(DATA_DIR)
namebook.install(DATA_DIR, store)
service = IServService(store)
wizard = Wizard(store, IServProber())
registry = SubscriptionRegistry(store)
holiday_calendar = HolidayCalendar(store)
app = create_app(
    service,
    wizard=wizard,
    frontend_dir=os.environ.get("ISERV_FRONTEND_DIR"),
    holiday_calendar=holiday_calendar,
    registry=registry,
)

if os.environ.get("ISERV_ENABLE_CALENDAR", "1") == "1":
    from .calendar_listener import DEFAULT_PORT, start_calendar_listener
    from .calendar_server import create_calendar_app

    start_calendar_listener(
        create_calendar_app(store, registry, holiday_calendar=holiday_calendar),
        int(os.environ.get("ISERV_CALENDAR_PORT", str(DEFAULT_PORT))),
    )

app.state.integration_access.announce_now()

if os.environ.get("ISERV_ENABLE_POLLER") == "1":
    from .scheduler import poll_interval_from_env, start_poller

    start_poller(
        service,
        poll_interval_from_env(),
        registry=registry,
        holiday_calendar=holiday_calendar,
    )
