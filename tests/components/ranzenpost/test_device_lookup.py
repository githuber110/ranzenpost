from datetime import timedelta

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.ranzenpost.const import DOMAIN, EVENT_RANZENPOST
from custom_components.ranzenpost.signals import Signal, async_fire_signals

from . import CHILD_1, SCHOOL, fixture, make_entry, mock_addon

PANEL_LINK = "homeassistant://hassio/ingress/ranzenpost"


def record_lookups(monkeypatch):
    calls = []
    legacy_calls = []
    original = dr.DeviceRegistry.async_get_device

    def by_identifier(self, identifier, config_entry_id):
        calls.append((identifier, config_entry_id))
        device = self.devices.get_entry({identifier}, None)
        return device if device is not None and config_entry_id in device.config_entries else None

    def legacy(self, *args, **kwargs):
        legacy_calls.append(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(dr.DeviceRegistry, "async_get_device_by_identifier", by_identifier, raising=False)
    monkeypatch.setattr(dr.DeviceRegistry, "async_get_device", legacy)
    return calls, legacy_calls


async def test_devices_are_looked_up_per_entry_when_home_assistant_offers_it(
    hass, aioclient_mock, frozen_now, monkeypatch
):
    calls, legacy_calls = record_lookups(monkeypatch)
    info = fixture("info")
    info["ingress_path"] = ""
    mock_addon(aioclient_mock, info=info)
    entry = make_entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    legacy = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "school:school.example")}, name="Ranzenpost Sample School"
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    events = async_capture_events(hass, EVENT_RANZENPOST)
    async_fire_signals(hass, entry.entry_id, [Signal("new_letter", SCHOOL, CHILD_1)])
    await hass.async_block_till_done()

    school = registry.async_get(legacy.id)
    child = next(
        device
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
        if (DOMAIN, f"child:{entry.entry_id}:{CHILD_1}") in device.identifiers
    )
    assert legacy_calls == []
    assert {config_entry_id for _, config_entry_id in calls} == {entry.entry_id}
    assert (DOMAIN, "school:school.example") in {identifier for identifier, _ in calls}
    assert school.identifiers == {(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")}
    assert school.configuration_url == PANEL_LINK
    assert child.configuration_url == PANEL_LINK
    assert [event.data[ATTR_DEVICE_ID] for event in events] == [child.id]


async def test_without_the_per_entry_lookup_a_device_of_another_entry_is_ignored(hass, monkeypatch):
    monkeypatch.delattr(dr.DeviceRegistry, "async_get_device_by_identifier", raising=False)
    entry = make_entry()
    entry.add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN, title="Other", unique_id="other-host:8099")
    other.add_to_hass(hass)
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=other.entry_id, identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")}
    )
    own = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_1}")}
    )
    events = async_capture_events(hass, EVENT_RANZENPOST)

    async_fire_signals(hass, entry.entry_id, [Signal("holiday", SCHOOL), Signal("new_letter", SCHOOL, CHILD_1)])
    await hass.async_block_till_done()

    assert not hasattr(registry, "async_get_device_by_identifier")
    assert [event.data[ATTR_DEVICE_ID] for event in events] == [own.id]
