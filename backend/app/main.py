import logging
import os

from .holidays import HolidayCalendar
from .iserv_prober import IServProber
from .server import create_app
from .service import IServService
from .store import Store
from .subscriptions import SubscriptionRegistry
from .wizard import Wizard

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

store = Store(os.environ.get("ISERV_DATA_DIR", "/data"))
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

if os.environ.get("ISERV_ENABLE_POLLER") == "1":
    from .scheduler import start_poller

    start_poller(
        service,
        int(os.environ.get("ISERV_POLL_INTERVAL", "1800")),
        registry=registry,
        holiday_calendar=holiday_calendar,
    )
