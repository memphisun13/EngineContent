"""Локальный интерфейс: python app.py -> http://localhost:8000"""
from __future__ import annotations

import os
import threading

from flask import Flask, jsonify, render_template, request

from common import Settings
from runner import Runner, read_links
from sheets import open_store

app = Flask(__name__)
_lock = threading.Lock()  # одновременно — только один запуск
_runner: Runner | None = None
_thread: threading.Thread | None = None


def _sheet_url(settings: Settings) -> str:
    return f"https://docs.google.com/spreadsheets/d/{settings.sheet_id}" if settings.sheet_id else ""


@app.get("/")
def index():
    return render_template("index.html", sheet_url=_sheet_url(Settings()))


@app.post("/start")
def start():
    global _runner, _thread
    urls = read_links((request.get_json(silent=True) or {}).get("links", ""))
    if not urls:
        return jsonify(ok=False, error="Вставьте хотя бы одну ссылку"), 400
    with _lock:
        if _thread and _thread.is_alive():
            return jsonify(ok=False, error="Запуск уже идёт — дождитесь окончания или остановите его"), 409
        settings = Settings()
        try:
            store = open_store(settings)
        except Exception as e:
            return jsonify(ok=False, error=f"Не удалось подключиться к таблице: {e}"), 500
        _runner = Runner(store, settings)
        _runner.state.update(running=True, total=len(urls))  # чтобы статус сразу показал запуск
        _thread = threading.Thread(target=_runner.run, args=(urls,), daemon=True)
        _thread.start()
    return jsonify(ok=True, total=len(urls))


@app.post("/stop")
def stop():
    if _runner and _thread and _thread.is_alive():
        _runner.stop()
        return jsonify(ok=True)
    return jsonify(ok=False, error="Сейчас ничего не запущено")


@app.get("/status")
def status():
    if not _runner:
        return jsonify(running=False, total=0, processed=0, added_people=0, added_companies=0,
                       errors=0, current="", message="", log=[])
    data = _runner.snapshot()
    data["running"] = bool(_thread and _thread.is_alive())
    return jsonify(data)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"Откройте http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
