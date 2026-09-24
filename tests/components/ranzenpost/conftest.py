import pytest
from freezegun import freeze_time

from . import FROZEN_NOW, FROZEN_SATURDAY


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
async def berlin_time_zone(hass):
    await hass.config.async_set_time_zone("Europe/Berlin")


@pytest.fixture
def frozen_now():
    with freeze_time(FROZEN_NOW) as frozen:
        yield frozen


@pytest.fixture
def frozen_saturday():
    with freeze_time(FROZEN_SATURDAY) as frozen:
        yield frozen
