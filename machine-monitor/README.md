# Machine Monitor – MQTT PoC für Raspberry Pi 3

Maschinen melden ihren Status per MQTT, ein Collector speichert ihn in SQLite, ein Flask-Dashboard zeigt Status, Verlauf, Dokumentation und ein Logbuch an. Verbindungsabbrüche werden per **Last Will** als `ERROR` gemeldet.

```
Maschine(n) ──MQTT──► Mosquitto (Raspi) ──► collector.py ──► SQLite ◄── web.py (Flask, :8080)
  status / info          retained + LWT
```

## Komponenten

| Datei | Aufgabe |
|---|---|
| `machine_sim.py` | Simuliert eine Maschine: sendet `info` (Doku), periodisch `status`, registriert Last Will |
| `collector.py` | Abonniert `factory/+/status` und `factory/+/info`, schreibt in SQLite |
| `web.py` + `templates/` | Dashboard (Übersicht, Detailseite mit Doku, Logbuch, Statusverlauf) + JSON-API |
| `db.py` | SQLite-Schema und Zugriffe (WAL-Modus) |
| `common.py` | Konfiguration (Umgebungsvariablen), Topics, MQTT-Client |
| `deploy/` | Mosquitto-Konfiguration und systemd-Units |

## Topics & Payloads

| Topic | Retained | Payload |
|---|---|---|
| `factory/<id>/status` | ja | `{"state": "RUNNING", "detail": null, "ts": 1700000000, "will": false}` |
| `factory/<id>/info` | ja | `{"name": "Presse 1", "model": "...", "location": "...", "manual_url": "..."}` |

Gültige States: `RUNNING`, `IDLE`, `MAINTENANCE`, `ERROR`, `OFFLINE`.

**Last Will:** Beim Connect hinterlegt die Maschine auf `factory/<id>/status` die Nachricht `{"state": "ERROR", "detail": "connection lost", "will": true}`. Verschwindet sie ohne sauberes Disconnect (Absturz, Strom, Netzwerk), veröffentlicht der Broker diese Nachricht spätestens nach 1,5 × Keepalive (hier 15 s). Bei sauberem Beenden sendet die Maschine selbst `OFFLINE`.

Eigene Maschinen (z. B. ESP32, SPS-Gateway) müssen nur dieses Schema einhalten.

## Installation auf dem Raspberry Pi 3

Getestet mit Python 3.11 (Raspberry Pi OS Bookworm) bzw. 3.13.

```bash
# 1. Broker
sudo apt update && sudo apt install -y mosquitto mosquitto-clients python3-venv
sudo mosquitto_passwd -c /etc/mosquitto/passwd monitor
sudo cp deploy/mosquitto.conf /etc/mosquitto/conf.d/machine-monitor.conf
sudo systemctl restart mosquitto

# 2. Projekt
cp -r iot/machine-monitor ~/machine-monitor && cd ~/machine-monitor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp machine-monitor.env.example machine-monitor.env   # Passwort eintragen

# 3. Dienste
sudo cp deploy/machine-monitor-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now machine-monitor-collector machine-monitor-web
```

Dashboard: `http://<raspi-ip>:8080`

## Ausprobieren

```bash
set -a; . ./machine-monitor.env; set +a
.venv/bin/python machine_sim.py press-01 --name "Presse 1" --location "Halle A"
.venv/bin/python machine_sim.py cnc-02 --name "CNC 2" &
kill -9 %1        # Absturz simulieren -> Last Will "ERROR" im Dashboard

# Manuell senden / mitlesen
mosquitto_pub -u monitor -P <pw> -t factory/test-01/status -r -m '{"state":"RUNNING"}'
mosquitto_sub -u monitor -P <pw> -t 'factory/#' -v
```

JSON-API: `GET /api/machines`, `GET /api/machines/<id>/history?limit=50`

## Grenzen des PoC

- Kein TLS und keine Benutzerverwaltung im Dashboard → nur im lokalen Netz betreiben.
- Flask-Entwicklungsserver; für Produktion `gunicorn` o. ä. davor.
- SQLite wächst unbegrenzt; für Dauerbetrieb Aufräumjob (z. B. Verlauf > 90 Tage löschen) ergänzen.
- Pro Maschine wird ein eigenes MQTT-Login empfohlen (ACLs in Mosquitto), damit Maschinen nur ihr eigenes Topic beschreiben können.
