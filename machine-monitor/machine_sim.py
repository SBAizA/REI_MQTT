"""Simulated machine: publishes documentation, periodic status and a Last Will.

Usage:
    python machine_sim.py press-01 --name "Hydraulic press" --location "Hall A"

Kill the process with SIGKILL (or pull the network cable) to see the Last Will
arrive as ERROR. Ctrl+C performs a clean shutdown and reports OFFLINE instead.
"""

import argparse
import json
import logging
import random
import signal
import threading
import time

from common import Config, create_client, setup_logging

log = logging.getLogger("machine")

# Weighted transitions to make the simulated data look plausible.
NEXT_STATE = {
    "RUNNING": (["RUNNING", "IDLE", "ERROR"], [85, 12, 3]),
    "IDLE": (["RUNNING", "IDLE", "MAINTENANCE"], [50, 45, 5]),
    "MAINTENANCE": (["MAINTENANCE", "IDLE"], [70, 30]),
    "ERROR": (["ERROR", "MAINTENANCE", "IDLE"], [60, 30, 10]),
}
ERROR_CODES = ["E101 overtemperature", "E202 motor stall", "E303 emergency stop pressed"]


def status_payload(state: str, detail: str | None = None, will: bool = False) -> str:
    return json.dumps({"state": state, "detail": detail, "ts": int(time.time()), "will": will})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("machine_id")
    parser.add_argument("--name", default=None)
    parser.add_argument("--model", default="SIM-1000")
    parser.add_argument("--location", default="Hall A")
    parser.add_argument("--manual", default="https://example.com/manuals/sim-1000.pdf")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    setup_logging()
    cfg = Config.from_env()
    status_topic = cfg.topic(args.machine_id, "status")
    stop = threading.Event()

    client = create_client(cfg, f"machine-{args.machine_id}")
    # Last Will: sent by the broker if this client disappears without a clean disconnect.
    client.will_set(status_topic, status_payload("ERROR", "connection lost", will=True), qos=1, retain=True)

    info = {
        "name": args.name or args.machine_id,
        "model": args.model,
        "location": args.location,
        "manual_url": args.manual,
    }

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("Connect failed: %s", reason_code)
            return
        log.info("Connected to %s:%s", cfg.host, cfg.port)
        client.publish(cfg.topic(args.machine_id, "info"), json.dumps(info), qos=1, retain=True)

    client.on_connect = on_connect
    client.connect_async(cfg.host, cfg.port, keepalive=10)
    client.loop_start()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    state = "IDLE"
    try:
        while not stop.is_set():
            if client.is_connected():
                states, weights = NEXT_STATE[state]
                state = random.choices(states, weights)[0]
                detail = random.choice(ERROR_CODES) if state == "ERROR" else None
                client.publish(status_topic, status_payload(state, detail), qos=1, retain=True)
                log.info("%s %s", state, detail or "")
            stop.wait(args.interval)
    finally:
        client.publish(status_topic, status_payload("OFFLINE", "shutdown"), qos=1, retain=True).wait_for_publish(2)
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
