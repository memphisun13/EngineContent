"""Общий движок запуска: используется и консолью (main.py), и интерфейсом (app.py)."""
from __future__ import annotations

import json
import random
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable

import dou
import linkedin
from common import BASE_DIR, Company, LinkError, Person, Settings, StopRun, clean

HISTORY_FILE = BASE_DIR / "runs.json"
HISTORY_KEEP = 50


def read_links(text: str) -> list[str]:
    """Ссылки по одной в строке; пустые строки, комментарии (#) и дубли пропускаем."""
    out: list[str] = []
    for line in text.splitlines():
        line = clean(line)
        if not line or line.startswith("#"):
            continue
        if "://" not in line:
            line = "https://" + line
        if line not in out:
            out.append(line)
    return out


def detect(url: str) -> tuple[str, str] | None:
    """(источник, тип) или None."""
    if dou.is_dou(url):
        kind = dou.classify(url)
        return ("dou", kind) if kind else None
    if linkedin.is_linkedin(url):
        kind = linkedin.classify(url)
        return ("linkedin", kind) if kind else None
    return None


KIND_LABELS = {
    "company": "компания",
    "company_list": "каталог компаний",
    "company_people": "компания + люди",
    "search": "поиск людей",
    "person": "профиль",
}


def describe(url: str) -> dict:
    """Что инструмент понял про ссылку — для подсказки в интерфейсе."""
    found = detect(url)
    if not found:
        reason = "это не dou.ua и не linkedin.com"
        if dou.is_dou(url) or linkedin.is_linkedin(url):
            reason = "такой тип страницы не поддерживается"
        return {"url": url, "source": "", "kind": "", "label": "", "ok": False, "reason": reason}
    return {"url": url, "source": found[0], "kind": found[1], "label": KIND_LABELS[found[1]], "ok": True, "reason": ""}


def open_browser_context(pw, settings: Settings, headless: bool | None = None):
    """Постоянный профиль браузера — сессия LinkedIn сохраняется между запусками."""
    kwargs = dict(
        user_data_dir=settings.profile_dir,
        headless=settings.headless if headless is None else headless,
        viewport={"width": 1366, "height": 900},
        locale="uk-UA",
    )
    if settings.browser_path:
        kwargs["executable_path"] = settings.browser_path
    return pw.chromium.launch_persistent_context(**kwargs)


def linkedin_login(settings: Settings, on_status: Callable[[str], None] = print,
                   cancel: threading.Event | None = None, timeout: float = 600) -> bool:
    """Открывает окно входа LinkedIn и ждёт, пока пользователь войдёт. True — вход выполнен."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = open_browser_context(pw, settings, headless=False)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            on_status("Окно браузера открыто — войдите в LinkedIn. Окно закроется само после входа.")
            deadline = time.time() + timeout
            while time.time() < deadline:
                if cancel is not None and cancel.is_set():
                    on_status("Вход отменён")
                    return False
                if not ctx.pages:
                    on_status("Окно закрыто до входа в LinkedIn")
                    return False
                try:
                    url = ctx.pages[-1].url
                    has_cookie = any(c["name"] == "li_at" for c in ctx.cookies("https://www.linkedin.com"))
                except Exception:
                    return False  # браузер закрыли
                if has_cookie and not any(p in url for p in ("/login", "/checkpoint", "/uas/", "/authwall")):
                    time.sleep(2)  # даём сохраниться cookies
                    on_status("Вход выполнен, сессия сохранена")
                    return True
                time.sleep(1)
            on_status("Время на вход истекло (10 минут)")
            return False
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def load_history() -> list[dict]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_history(entry: dict) -> None:
    runs = [entry] + load_history()
    try:
        HISTORY_FILE.write_text(json.dumps(runs[:HISTORY_KEEP], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


class Runner:
    def __init__(self, store, settings: Settings | None = None, on_log: Callable[[str], None] | None = None):
        self.store = store
        self.settings = settings or Settings()
        self.on_log = on_log
        self._stop = threading.Event()
        self.page = None
        self._navigated = False
        self.li_profiles = 0
        self.lock = threading.Lock()
        self.state = {
            "running": False, "total": 0, "processed": 0, "added_people": 0, "added_companies": 0,
            "errors": 0, "current": "", "message": "", "stopped_by": "", "started_at": "", "finished_at": "",
            "limit": self.settings.limit, "li_profiles": 0, "li_auth": "",
            "wait_label": "", "wait_until": 0.0, "wait_total": 0.0,
        }
        self._t0 = 0.0
        self.links: list[dict] = []
        self.records: list[dict] = []  # лента найденных записей для интерфейса
        self._seq = 0
        self.logs: deque[str] = deque(maxlen=300)

    # ---------- служебное ----------

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def stop(self) -> None:
        if not self.stopped:
            self._stop.set()
            self.log("Остановка запрошена — завершаю текущую страницу…")

    def log(self, msg: str) -> None:
        line = f"{datetime.now():%H:%M:%S} {msg}"
        with self.lock:
            self.logs.append(line)
        if self.on_log:
            self.on_log(line)

    def error(self, url: str, reason: str) -> None:
        with self.lock:
            self.state["errors"] += 1
        self.log(f"  ОШИБКА {url}: {reason}")
        with open(self.settings.errors_log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t{url}\t{reason}\n")

    def sleep(self, seconds: float, label: str = "") -> None:
        """Сон, который прерывается кнопкой «Остановить». С подписью — виден в интерфейсе как таймер."""
        seconds = max(seconds, 0)
        if label:
            with self.lock:
                self.state.update(wait_label=label, wait_until=time.time() + seconds, wait_total=seconds)
        try:
            self._stop.wait(seconds)
        finally:
            if label:
                with self.lock:
                    self.state.update(wait_label="", wait_until=0.0, wait_total=0.0)

    def sleep_random(self, lo: float, hi: float, label: str = "") -> None:
        self.sleep(random.uniform(lo, hi), label)

    def snapshot(self, since: int = 0) -> dict:
        with self.lock:
            data = {**self.state}
            data["li_profiles"] = self.li_profiles
            data["elapsed"] = round(time.time() - self._t0, 1) if self._t0 and data["running"] else 0
            data["wait_left"] = round(max(data.pop("wait_until") - time.time(), 0), 1)
            data["links"] = [dict(l) for l in self.links]
            data["records"] = [r for r in self.records if r["id"] > since]
            data["seq"] = self._seq
            data["log"] = list(self.logs)[-120:]
        return data

    def open(self, url: str, wait_for: str | None = None, retry: bool = True) -> str:
        """Переход на страницу со случайной паузой PAUSE_MIN–PAUSE_MAX между страницами."""
        if self.stopped:
            raise LinkError("запуск остановлен")
        if self._navigated:
            self.sleep_random(self.settings.pause_min, self.settings.pause_max, "Пауза между страницами")
            if self.stopped:
                raise LinkError("запуск остановлен")
        self._navigated = True
        for attempt in (1, 2):
            try:
                resp = self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:  # сеть, таймаут и т.п.
                raise LinkError(f"страница не открылась: {str(e).splitlines()[0][:150]}") from None
            # сайт ограничил частоту запросов — одна повторная попытка после длинной паузы
            if retry and attempt == 1 and resp is not None and resp.status in (403, 429, 503):
                wait = random.uniform(30, 60)
                self.log(f"  сайт ответил HTTP {resp.status}, жду {wait:.0f} с и пробую ещё раз")
                self.sleep(wait, f"Сайт ограничил запросы (HTTP {resp.status}), повтор")
                if self.stopped:
                    raise LinkError("запуск остановлен")
                continue
            break
        if resp is not None and resp.status >= 400 and resp.status != 999:
            raise LinkError(f"HTTP {resp.status}")
        if wait_for:
            try:
                self.page.wait_for_selector(wait_for, timeout=15000)
            except Exception:
                pass  # поле может отсутствовать — разбираем то, что есть
        return self.page.content()

    # ---------- запуск ----------

    def run(self, urls: list[str]) -> dict:
        from playwright.sync_api import sync_playwright

        self._stop.clear()
        self._navigated = False
        self.li_profiles = 0
        self._t0 = time.time()
        with self.lock:
            self.links = [{**describe(u), "status": "queued", "people": 0, "companies": 0, "error": "",
                           "seconds": 0} for u in urls]
            self.state.update(running=True, total=len(urls), processed=0, added_people=0, added_companies=0,
                              errors=0, current="", message="", stopped_by="", limit=self.settings.limit,
                              started_at=datetime.now().isoformat(timespec="seconds"), finished_at="")
        self.log(f"Старт: {len(urls)} ссылок, лимит LinkedIn {self.settings.limit} профилей")
        try:
            with sync_playwright() as pw:
                ctx = open_browser_context(pw, self.settings)
                try:
                    self.page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    scrapers = {"dou": dou.DouScraper(self), "linkedin": linkedin.LinkedInScraper(self)}
                    for i, url in enumerate(urls, 1):
                        if self.stopped:
                            break
                        self._process(i, url, scrapers)
                finally:
                    ctx.close()
            msg = "Остановлено пользователем" if self.stopped else "Готово"
            stopped_by = "user" if self.stopped else ""
        except StopRun as e:
            msg, stopped_by = f"СТОП: {e}", "linkedin"
            if "не залогинены" in str(e):
                with self.lock:
                    self.state["li_auth"] = "out"
            self.error(self.state["current"], str(e))
        except Exception as e:
            msg = f"Запуск прерван: {type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"
            stopped_by = "crash"
        with self.lock:
            for l in self.links:
                if l["status"] in ("queued", "running"):
                    l["status"] = "skipped"
            self.state.update(running=False, current="", message=msg, stopped_by=stopped_by,
                              wait_label="", wait_until=0.0, finished_at=datetime.now().isoformat(timespec="seconds"))
        s = self.state
        self.log(f"{msg}. Обработано {s['processed']}/{s['total']}, добавлено людей {s['added_people']}, "
                 f"компаний {s['added_companies']}, ошибок {s['errors']}")
        save_history({
            "started_at": s["started_at"], "finished_at": s["finished_at"],
            "seconds": round(time.time() - self._t0), "total": s["total"], "processed": s["processed"],
            "added_people": s["added_people"], "added_companies": s["added_companies"],
            "errors": s["errors"], "li_profiles": self.li_profiles, "message": msg,
        })
        return self.snapshot()

    def _process(self, i: int, url: str, scrapers: dict) -> None:
        link = self.links[i - 1]
        t = time.time()
        with self.lock:
            self.state["current"] = url
            link["status"] = "running"
        self.log(f"[{i}/{len(self.links)}] {url}")
        status, err = "done", ""
        try:
            if not link["ok"]:
                raise LinkError(f"ссылка не распознана: {link['reason']}")
            for people, companies in scrapers[link["source"]].scrape(url):
                p, c = self._save(people, companies)
                with self.lock:
                    link["people"] += p
                    link["companies"] += c
        except StopRun:
            with self.lock:
                link.update(status="error", error="остановлено защитой LinkedIn", seconds=round(time.time() - t))
            raise
        except LinkError as e:
            if self.stopped:
                status = "skipped"
            else:
                status, err = "error", str(e)
                self.error(url, err)
        except Exception as e:  # не падаем из-за одной ссылки
            status, err = "error", f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"
            self.error(url, err)
        with self.lock:
            link.update(status=status, error=err, seconds=round(time.time() - t))
            if not self.stopped or status != "skipped":
                self.state["processed"] = i

    def _save(self, people: list[Person], companies: list[Company]) -> tuple[int, int]:
        new_c = self.store.add_companies(companies) if companies else []
        new_p = self.store.add_people(people) if people else []
        new_ids = {id(r) for r in new_c + new_p}
        with self.lock:
            self.state["added_companies"] += len(new_c)
            self.state["added_people"] += len(new_p)
            for r in companies:
                self._seq += 1
                self.records.append({"id": self._seq, "type": "company", "new": id(r) in new_ids,
                                     "name": r.name, "website": r.website, "city": r.city, "size": r.size,
                                     "url": r.url, "source": r.source})
            for r in people:
                self._seq += 1
                self.records.append({"id": self._seq, "type": "person", "new": id(r) in new_ids,
                                     "name": f"{r.first_name} {r.last_name}".strip(), "title": r.title,
                                     "company": r.company, "url": r.url, "source": r.source})
            del self.records[:-1000]
        found = []
        if companies:
            found.append(f"компаний {len(companies)} (новых {len(new_c)})")
        if people:
            found.append(f"людей {len(people)} (новых {len(new_p)})")
        self.log("  найдено: " + ", ".join(found))
        return len(new_p), len(new_c)
