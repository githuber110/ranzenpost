import json
import os

import pytest
from freezegun import freeze_time

from custom_components.ranzenpost.const import DOMAIN

from . import FROZEN_NOW, FROZEN_SATURDAY, MANIFEST_VERSION


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


@pytest.fixture
def manifest_on_disk(hass, tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    stamps = iter(range(1_700_000_000, 1_800_000_000, 10))

    def write(version):
        path.write_text(json.dumps({"domain": DOMAIN, "version": version}), encoding="utf-8")
        stamp = next(stamps)
        os.utime(path, (stamp, stamp))

    async def install(version):
        await hass.async_add_executor_job(write, version)

    write(MANIFEST_VERSION)
    monkeypatch.setattr("custom_components.ranzenpost.coordinator.MANIFEST_FILE", path)
    return install
