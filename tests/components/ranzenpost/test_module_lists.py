from . import setup_entry
from .test_school_notices import childless_info, ranzenpost_entities

TODOS = "sensor.ranzenpost_school_open_todos"
PRINT_JOBS = "sensor.ranzenpost_school_print_jobs"
COUNTS = (
    PRINT_JOBS,
    "sensor.ranzenpost_school_course_selections",
    "sensor.ranzenpost_school_video_rooms",
    "sensor.ranzenpost_school_polls",
)


async def test_the_module_sensors_need_the_module_listed_by_the_school(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock, info=childless_info())
    entities = ranzenpost_entities(hass)
    assert TODOS not in entities
    assert not [name for name in COUNTS if name in entities]


async def test_the_to_do_sensor_counts_and_lists_the_open_to_dos(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock, info=childless_info(todo=True))
    assert hass.states.get(TODOS).state == "2"
    assert [item["title"] for item in hass.states.get(TODOS).attributes["todos"]] == ["Sportzeug", "Buch abgeben"]


async def test_a_listed_module_with_an_unknown_count_says_so(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock, info=childless_info(print=True))
    assert hass.states.get(PRINT_JOBS).state == "unknown"
