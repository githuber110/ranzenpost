import json

from app.mqtt_bridge import discovery_configs, state_payload, state_topic
from app.mqtt_publisher import MqttPublisher


class FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))


CHILD_A = {"child_id": "child-1", "name": "Kind Eins"}
CHILD_B = {"child_id": "child-2", "name": "Kind Zwei"}


def test_publish_discovery_publishes_all_configs_with_retain():
    client = FakeClient()
    publisher = MqttPublisher(client, app_slug="iserv_connector")

    publisher.publish_discovery([CHILD_A])

    expected_configs = discovery_configs("iserv_connector", CHILD_A)
    assert len(client.published) == len(expected_configs)
    assert all(retain is True for _, _, retain in client.published)


def test_publish_discovery_topics_match_bridge_configs():
    client = FakeClient()
    publisher = MqttPublisher(client, app_slug="iserv_connector")

    publisher.publish_discovery([CHILD_A])

    expected_configs = discovery_configs("iserv_connector", CHILD_A)
    published_topics = {topic for topic, _, _ in client.published}
    expected_topics = {config["topic"] for config in expected_configs}
    assert published_topics == expected_topics


def test_publish_discovery_payloads_are_valid_json():
    client = FakeClient()
    publisher = MqttPublisher(client, app_slug="iserv_connector")

    publisher.publish_discovery([CHILD_A])

    for _, payload, _ in client.published:
        assert isinstance(json.loads(payload), dict)


def test_publish_discovery_payload_content_matches_bridge():
    client = FakeClient()
    publisher = MqttPublisher(client, app_slug="iserv_connector")

    publisher.publish_discovery([CHILD_A])

    expected_configs = {
        config["topic"]: config["payload"]
        for config in discovery_configs("iserv_connector", CHILD_A)
    }
    for topic, payload, _ in client.published:
        assert json.loads(payload) == expected_configs[topic]


def test_publish_state_uses_correct_topic():
    client = FakeClient()
    publisher = MqttPublisher(client, app_slug="iserv_connector")

    publisher.publish_state("child-1", "2026-08-31T10:00:00", True)

    assert len(client.published) == 1
    topic, _, _ = client.published[0]
    assert topic == state_topic("iserv_connector", "child-1", "state")


def test_publish_state_payload_matches_bridge_with_has_changes_and_error():
    client = FakeClient()
    publisher = MqttPublisher(client, app_slug="iserv_connector")

    publisher.publish_state("child-1", "2026-08-31T10:00:00", False, error="timeout")

    _, payload, _ = client.published[0]
    expected = state_payload("2026-08-31T10:00:00", False, "timeout")
    assert json.loads(payload) == expected


def test_publish_discovery_multiple_children_produce_disjoint_topics():
    client = FakeClient()
    publisher = MqttPublisher(client, app_slug="iserv_connector")

    publisher.publish_discovery([CHILD_A, CHILD_B])

    topics_a = {config["topic"] for config in discovery_configs("iserv_connector", CHILD_A)}
    topics_b = {config["topic"] for config in discovery_configs("iserv_connector", CHILD_B)}
    published_topics = [topic for topic, _, _ in client.published]

    assert topics_a.isdisjoint(topics_b)
    assert len(published_topics) == len(topics_a) + len(topics_b)


def test_publish_state_multiple_children_produce_disjoint_topics():
    client = FakeClient()
    publisher = MqttPublisher(client, app_slug="iserv_connector")

    publisher.publish_state("child-1", "2026-08-31T10:00:00", True)
    publisher.publish_state("child-2", "2026-08-31T10:00:00", False)

    topics = [topic for topic, _, _ in client.published]
    assert len(set(topics)) == 2
