"""Small Flask dashboard: machine overview, status history, documentation and logbook."""

import os
from contextlib import closing
from datetime import datetime

from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for

import db
from common import Config

cfg = Config.from_env()
with closing(db.connect(cfg.db_path)) as _conn:
    db.init(_conn)

app = Flask(__name__)


def get_conn():
    # One connection per request; sqlite connections must not be shared across threads.
    if "conn" not in g:
        g.conn = db.connect(cfg.db_path)
    return g.conn


@app.teardown_appcontext
def close_conn(exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


@app.template_filter("dt")
def format_ts(ts: int | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M:%S") if ts else "–"


@app.get("/")
def index():
    return render_template("index.html", machines=db.list_machines(get_conn()))


@app.get("/machines/<machine_id>")
def machine(machine_id: str):
    m = db.get_machine(get_conn(), machine_id) or abort(404)
    return render_template(
        "machine.html",
        m=m,
        history=db.status_history(get_conn(), machine_id),
        notes=db.notes(get_conn(), machine_id),
    )


@app.post("/machines/<machine_id>/notes")
def add_note(machine_id: str):
    db.get_machine(get_conn(), machine_id) or abort(404)
    text = request.form.get("text", "").strip()
    if text:
        db.add_note(get_conn(), machine_id, request.form.get("author", "").strip() or None, text[:2000])
    return redirect(url_for("machine", machine_id=machine_id))


@app.get("/api/machines")
def api_machines():
    return jsonify(db.list_machines(get_conn()))


@app.get("/api/machines/<machine_id>/history")
def api_history(machine_id: str):
    return jsonify(db.status_history(get_conn(), machine_id, limit=int(request.args.get("limit", 100))))


if __name__ == "__main__":
    # Built-in server is sufficient for a PoC on the local network.
    app.run(host=os.getenv("WEB_HOST", "0.0.0.0"), port=int(os.getenv("WEB_PORT", "8080")))
