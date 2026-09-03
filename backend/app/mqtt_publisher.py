import json

from .mqtt_bridge import discovery_configs, state_payload, state_topic


class MqttPublisher:
    def __init__(self, client, app_slug="iserv_connector"):
        self.client = client
        self.app_slug = app_slug

    def publish_discovery(self, children):
        for child in children:
            for config in discovery_configs(self.app_slug, child):
                self.client.publish(
                    config["topic"],
                    json.dumps(config["payload"], ensure_ascii=False),
                    retain=True,
                )

    def publish_state(self, child_id, last_updated, has_changes, error=None):
        payload = state_payload(last_updated, has_changes, error)
        topic = state_topic(self.app_slug, child_id, "state")
        self.client.publish(
            topic,
            json.dumps(payload, ensure_ascii=False),
            retain=False,
        )


def connect_from_env():
    import os

    import paho.mqtt.client as mqtt

    host = os.environ.get("ISERV_MQTT_HOST", "localhost")
    port = int(os.environ.get("ISERV_MQTT_PORT", "1883"))
    user = os.environ.get("ISERV_MQTT_USER")
    password = os.environ.get("ISERV_MQTT_PASSWORD")

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    if user:
        client.username_pw_set(user, password)
    client.connect(host, port)
    return client
