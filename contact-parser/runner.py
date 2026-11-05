"""Общий движок запуска: используется и консолью (main.py), и интерфейсом (app.py)."""
from __future__ import annotations

import random
import threading
import time
from collections import deque
from datetime import datetime
from typing import Callable

import dou
import linkedin
from common import LinkError, Settings, StopRun, clean


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


def open_browser_context(pw, settings: Settings):
    """Постоянный профиль браузера — сессия LinkedIn сохраняется между запусками."""
    kwargs = dict(
        user_data_dir=settings.profile_dir,
        headless=settings.headless,
        viewport={"width": 1366, "height": 900},
        locale="uk-UA",
    )
    if settings.browser_path:
        kwargs["executable_path"] = settings.browser_path
    return pw.chromium.launch_persistent_context(**kwargs)


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
            "errors": 0, "current": "", "message": "", "started_at": "", "finished_at": "",
        }
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

    def sleep(self, seconds: float) -> None:
        """Сон, который прерывается кнопкой «Остановить»."""
        self._stop.wait(max(seconds, 0))

    def sleep_random(self, lo: float, hi: float) -> None:
        self.sleep(random.uniform(lo, hi))

    def snapshot(self) -> dict:
        with self.lock:
            return {**self.state, "log": list(self.logs)[-80:]}

    def open(self, url: str, wait_for: str | None = None, retry: bool = True) -> str:
        """Переход на страницу со случайной паузой PAUSE_MIN–PAUSE_MAX между страницами."""
        if self.stopped:
            raise LinkError("запуск остановлен")
        if self._navigated:
            self.sleep_random(self.settings.pause_min, self.settings.pause_max)
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
                self.sleep(wait)
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
        with self.lock:
            self.state.update(running=True, total=len(urls), processed=0, added_people=0, added_companies=0,
                              errors=0, current="", message="", started_at=datetime.now().isoformat(timespec="seconds"),
                              finished_at="")
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
                        with self.lock:
                            self.state["current"] = url
                        self.log(f"[{i}/{len(urls)}] {url}")
                        try:
                            found = detect(url)
                            if not found:
                                raise LinkError("ссылка не распознана (поддерживаются dou.ua и linkedin.com)")
                            for people, companies in scrapers[found[0]].scrape(url):
                                self._save(people, companies)
                        except StopRun:
                            raise
                        except LinkError as e:
                            if not self.stopped:
                                self.error(url, str(e))
                        except Exception as e:  # не падаем из-за одной ссылки
                            self.error(url, f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}")
                        if not self.stopped:
                            with self.lock:
                                self.state["processed"] = i
                finally:
                    ctx.close()
            msg = "Остановлено пользователем" if self.stopped else "Готово"
        except StopRun as e:
            msg = f"СТОП: {e}"
            self.error(self.state["current"], str(e))
        except Exception as e:
            msg = f"Запуск прерван: {type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"
        with self.lock:
            self.state.update(running=False, current="", message=msg,
                              finished_at=datetime.now().isoformat(timespec="seconds"))
        s = self.state
        self.log(f"{msg}. Обработано {s['processed']}/{s['total']}, добавлено людей {s['added_people']}, "
                 f"компаний {s['added_companies']}, ошибок {s['errors']}")
        return self.snapshot()

    def _save(self, people, companies) -> None:
        added_c = self.store.add_companies(companies) if companies else 0
        added_p = self.store.add_people(people) if people else 0
        with self.lock:
            self.state["added_companies"] += added_c
            self.state["added_people"] += added_p
        found = []
        if companies:
            found.append(f"компаний {len(companies)} (новых {added_c})")
        if people:
            found.append(f"людей {len(people)} (новых {added_p})")
        self.log("  найдено: " + ", ".join(found))
