"""Локальный интерфейс: python app.py -> http://localhost:8000"""
from __future__ import annotations

import os
import threading
import time

from flask import Flask, jsonify, render_template, request

import linkedin
from common import Settings
from runner import Runner, describe, linkedin_login, load_history, read_links
from sheets import open_store

app = Flask(__name__)
_lock = threading.Lock()  # одновременно — только один запуск или один вход в LinkedIn
_runner: Runner | None = None
_thread: threading.Thread | None = None

_login = {"state": "idle", "message": ""}  # idle | waiting | success | failed
_login_thread: threading.Thread | None = None
_login_cancel = threading.Event()

_session_cache = {"at": 0.0, "value": {"status": "out", "expires": ""}}


def _running() -> bool:
    return bool(_thread and _thread.is_alive())


def _logging_in() -> bool:
    return bool(_login_thread and _login_thread.is_alive())


def _sheet_url(settings: Settings) -> str:
    return f"https://docs.google.com/spreadsheets/d/{settings.sheet_id}" if settings.sheet_id else ""


def _session() -> dict:
    """Статус входа в LinkedIn (кэш на 5 секунд, чтобы не читать файл на каждый опрос)."""
    if time.time() - _session_cache["at"] > 5:
        _session_cache.update(at=time.time(), value=linkedin.session_info(Settings().profile_dir))
    value = dict(_session_cache["value"])
    if _runner and _runner.state.get("li_auth") == "out" and not _logging_in():
        value["status"] = "out"  # во время запуска LinkedIn сказал, что сессии нет
    return value


@app.get("/")
def index():
    s = Settings()
    return render_template("index.html", sheet_url=_sheet_url(s), limit=s.limit,
                           pause=f"{s.pause_min:g}–{s.pause_max:g}")


@app.post("/classify")
def classify():
    links = read_links((request.get_json(silent=True) or {}).get("links", ""))
    return jsonify(links=[describe(u) for u in links])


@app.post("/start")
def start():
    global _runner, _thread
    urls = read_links((request.get_json(silent=True) or {}).get("links", ""))
    if not urls:
        return jsonify(ok=False, error="Вставьте хотя бы одну ссылку"), 400
    with _lock:
        if _running():
            return jsonify(ok=False, error="Запуск уже идёт. Дождитесь окончания или остановите его."), 409
        if _logging_in():
            return jsonify(ok=False, error="Сначала завершите вход в LinkedIn в открытом окне браузера."), 409
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
    if _runner and _running():
        _runner.stop()
        return jsonify(ok=True)
    return jsonify(ok=False, error="Сейчас ничего не запущено")


@app.post("/linkedin/login")
def login():
    global _login_thread
    with _lock:
        if _running():
            return jsonify(ok=False, error="Идёт сбор. Войти можно после его окончания."), 409
        if _logging_in():
            return jsonify(ok=True)  # окно уже открыто

        def work():
            def status(msg):
                _login["message"] = msg

            try:
                ok = linkedin_login(Settings(), on_status=status, cancel=_login_cancel)
                _login["state"] = "success" if ok else "failed"
            except Exception as e:
                _login.update(state="failed", message=f"Не удалось открыть браузер: {str(e).splitlines()[0][:200]}")
            _session_cache["at"] = 0  # перечитать сессию
            if _runner:
                _runner.state["li_auth"] = ""

        _login_cancel.clear()
        _login.update(state="waiting", message="Открываю окно браузера…")
        _login_thread = threading.Thread(target=work, daemon=True)
        _login_thread.start()
    return jsonify(ok=True)


@app.post("/linkedin/cancel")
def login_cancel():
    _login_cancel.set()
    return jsonify(ok=True)


@app.get("/status")
def status():
    since = request.args.get("since", default=0, type=int)
    if _runner:
        data = _runner.snapshot(since)
        data["running"] = _running()
    else:
        data = dict(running=False, total=0, processed=0, added_people=0, added_companies=0, errors=0,
                    current="", message="", stopped_by="", links=[], records=[], seq=0, log=[],
                    li_profiles=0, limit=Settings().limit, elapsed=0, wait_left=0, wait_total=0, wait_label="")
    data["session"] = _session()
    data["login"] = {**_login, "active": _logging_in()}
    return jsonify(data)


@app.get("/history")
def history():
    return jsonify(runs=load_history())


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"Откройте http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
