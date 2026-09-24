import json
import pathlib

import pytest
from jsonschema import Draft202012Validator

from . import FIXTURES, fixture

CONTRACT = pathlib.Path(__file__).resolve().parents[3] / "custom_components" / "ranzenpost" / "contract.json"
SHAPES = {
    "info": "info",
    "state_child_1": "state",
    "state_child_2": "state",
    "events_lessons": "events",
    "events_exams": "events",
    "events_absences": "events",
    "events_holidays": "events",
    "events_own_entries": "events",
    "school": "school",
    "changes": "changes",
}


def validator(reference):
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": f"#/$defs/{reference}", "$defs": document["$defs"]})


@pytest.mark.parametrize(("name", "shape"), sorted(SHAPES.items()))
def test_every_fixture_matches_the_contract(name, shape):
    errors = [error.message for error in validator(shape).iter_errors(fixture(name))]
    assert errors == []


def test_every_fixture_file_is_covered_by_a_shape():
    assert {path.stem for path in FIXTURES.glob("*.json")} == set(SHAPES)
