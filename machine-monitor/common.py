"""Shared configuration, topic layout and MQTT client factory.

Topic layout (prefix defaults to "factory"):
    <prefix>/<machine_id>/status   JSON state, retained; also used as Last Will
    <prefix>/<machine_id>/info     JSON documentation (name, model, ...), retained
"""

import logging
import os
from dataclasses import dataclass

import paho.mqtt.client as mqtt

# Valid machine states. OFFLINE/ERROR may also arrive via Last Will.
STATES = ("RUNNING", "IDLE", "MAINTENANCE", "ERROR", "OFFLINE")


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    username: str | None
    password: str | None
    prefix: str
    db_path: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            host=os.getenv("MQTT_HOST", "localhost"),
            port=int(os.getenv("MQTT_PORT", "1883")),
            username=os.getenv("MQTT_USERNAME") or None,
            password=os.getenv("MQTT_PASSWORD") or None,
            prefix=os.getenv("MQTT_TOPIC_PREFIX", "factory"),
            db_path=os.getenv("DB_PATH", "machines.db"),
        )

    def topic(self, machine_id: str, kind: str) -> str:
        return f"{self.prefix}/{machine_id}/{kind}"


def setup_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_client(cfg: Config, client_id: str) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    if cfg.username:
        client.username_pw_set(cfg.username, cfg.password)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client
