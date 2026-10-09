"""Subscribes to all machine topics and persists status/info messages in SQLite."""

import json
import logging
import socket

import paho.mqtt.client as mqtt

import db
from common import STATES, Config, create_client, setup_logging

log = logging.getLogger("collector")


def main() -> None:
    setup_logging()
    cfg = Config.from_env()
    conn = db.connect(cfg.db_path)
    db.init(conn)
    client = create_client(cfg, f"collector-{socket.gethostname()}")

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("Connect failed: %s", reason_code)
            return
        log.info("Connected to %s:%s", cfg.host, cfg.port)
        client.subscribe([(cfg.topic("+", "status"), 1), (cfg.topic("+", "info"), 1)])

    def on_message(client, userdata, msg: mqtt.MQTTMessage):
        parts = msg.topic.split("/")
        if len(parts) != 3:
            return
        _, machine_id, kind = parts
        try:
            payload = json.loads(msg.payload)
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
        except ValueError as e:
            log.warning("Invalid payload on %s: %s", msg.topic, e)
            return

        if kind == "info":
            db.save_info(conn, machine_id, payload)
            log.info("[%s] info updated", machine_id)
            return

        state = str(payload.get("state", "")).upper()
        if state not in STATES:
            log.warning("[%s] unknown state %r", machine_id, state)
            return
        # Retained messages are replayed on every collector restart; skip them
        # if they don't change the stored state, to avoid duplicate history rows.
        if msg.retain:
            current = db.get_machine(conn, machine_id)
            if current and current["state"] == state and current["detail"] == payload.get("detail"):
                return
        is_will = bool(payload.get("will"))
        db.save_status(conn, machine_id, state, payload.get("detail"), payload, is_will)
        log.info("[%s] %s%s %s", machine_id, state, " (Last Will)" if is_will else "", payload.get("detail") or "")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(cfg.host, cfg.port, keepalive=30)
    try:
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == "__main__":
    main()
