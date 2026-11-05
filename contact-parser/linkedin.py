"""Парсер LinkedIn: страница компании, вкладка People, поиск людей, профиль.

Работает через уже залогиненный постоянный профиль браузера (см. `python main.py --login`).
Разметка LinkedIn часто меняется, поэтому у каждого поля несколько запасных вариантов;
если поле не найдено — оно остаётся пустым.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterator
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from common import Company, LinkError, Person, StopRun, clean, normalize_url, split_headline, split_name

if TYPE_CHECKING:
    from runner import Runner

SOURCE = "linkedin"
BASE = "https://www.linkedin.com"

COMPANY_RE = re.compile(r"^/company/([^/]+)/?(.*)$")
PROFILE_RE = re.compile(r"^/in/([^/?#]+)")


def is_linkedin(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def classify(url: str) -> str | None:
    path = urlsplit(url).path or "/"
    if PROFILE_RE.match(path):
        return "person"
    if path.startswith("/search/results/people"):
        return "search"
    m = COMPANY_RE.match(path)
    if m:
        return "company_people" if m.group(2).startswith("people") else "company"
    return None


def company_root(url: str) -> str:
    slug = COMPANY_RE.match(urlsplit(url).path).group(1)
    return f"{BASE}/company/{slug}/"


def profile_url(href: str) -> str:
    """Чистая ссылка на профиль: https://linkedin.com/in/<slug>/"""
    m = PROFILE_RE.match(urlsplit(urljoin(BASE, href)).path)
    return normalize_url(f"{BASE}/in/{m.group(1)}/") if m else ""


# ---------- сохранённая сессия ----------

def session_info(profile_dir: str) -> dict:
    """Есть ли в профиле браузера cookie входа LinkedIn (li_at) и до какого числа она действует.

    Читаем базу cookies Chromium только на чтение, браузер для этого не запускаем.
    Само значение cookie зашифровано и нам не нужно — смотрим только имя и срок.
    """
    import sqlite3
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    base = Path(profile_dir)
    for db in (base / "Default" / "Network" / "Cookies", base / "Default" / "Cookies"):
        if not db.is_file():
            continue
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True)
            row = con.execute("SELECT MAX(expires_utc) FROM cookies WHERE name='li_at' "
                              "AND host_key LIKE '%linkedin.com'").fetchone()
            con.close()
        except sqlite3.Error:
            continue
        if row and row[0]:
            expires = datetime(1601, 1, 1) + timedelta(microseconds=row[0])
            if expires > datetime.now(timezone.utc).replace(tzinfo=None):
                return {"status": "in", "expires": expires.strftime("%d.%m.%Y")}
            return {"status": "out", "expires": ""}
    return {"status": "out", "expires": ""}


# ---------- защита аккаунта ----------

WARNING_PATTERNS = [
    r"security verification", r"quick security check", r"let'?s do a quick", r"unusual activity",
    r"commercial use limit", r"temporarily restricted",
    r"перевірк[аи] безпеки", r"незвичн\w+ активн", r"проверк[аи] безопасности", r"необычн\w+ активн",
    r"обмежен\w+ доступ", r"ограничен\w+ доступ",
]
WARNING_RE = re.compile("|".join(WARNING_PATTERNS), re.I)


def check_page(url: str, html: str) -> None:
    """Бросает StopRun при капче/предупреждении, LinkError — если не залогинены."""
    path = urlsplit(url).path
    if "/checkpoint/" in path or "challenge" in path:
        raise StopRun("LinkedIn просит пройти проверку (капча/checkpoint). Запуск остановлен — "
                      "откройте LinkedIn в браузере вручную, пройдите проверку и подождите перед новым запуском.")
    if re.search(r"captcha-internal|<iframe[^>]+captcha|id=\"captcha", html, re.I):
        raise StopRun("LinkedIn показал капчу. Запуск остановлен — пройдите её вручную в браузере "
                      "и сделайте перерыв перед новым запуском.")
    if path.startswith(("/login", "/authwall", "/uas/login", "/signup")) or 'name="session_key"' in html:
        raise StopRun("Вы не залогинены в LinkedIn. Нажмите «Войти» вверху страницы (или выполните `python main.py --login`), "
                      "войдите и повторите запуск.")
    text = BeautifulSoup(html, "html.parser").get_text(" ")[:20000]
    m = WARNING_RE.search(text)
    if m:
        raise StopRun(f"LinkedIn показал предупреждение («{m.group(0)}»). Запуск остановлен, чтобы не рисковать аккаунтом.")


# ---------- разбор HTML ----------

SIZE_LABELS = ("company size", "розмір компанії", "размер компании", "size")
SITE_LABELS = ("website", "вебсайт", "веб-сайт", "сайт")
HQ_LABELS = ("headquarters", "штаб-квартира", "головний офіс", "location", "місцезнаходження", "местоположение")


def parse_company(html: str, url: str) -> Company:
    s = BeautifulSoup(html, "html.parser")
    c = Company(url=normalize_url(company_root(url)), source=SOURCE)
    h1 = s.select_one("main h1") or s.select_one("h1")
    c.name = clean(h1.get_text(" ")) if h1 else ""
    if not c.name:
        title = clean(s.title.get_text()) if s.title else ""
        c.name = clean(re.split(r"\s*[|:]\s*", title)[0]) if title else ""

    for dt in s.select("dl dt"):
        label = clean(dt.get_text(" ")).lower()
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        value = clean(dd.get_text(" "))
        if not c.website and any(label.startswith(l) for l in SITE_LABELS):
            a = dd.select_one("a[href]")
            c.website = clean(a.get_text(" ")) if a else value
        elif not c.size and any(label.startswith(l) for l in SIZE_LABELS):
            # «1 001–5 000 employees  1 234 on LinkedIn» -> первая часть
            m = re.search(r"[\d\s,. –—+-]+\s*(?:employees|працівник\w*|співробітник\w*|сотрудник\w*)", value, re.I)
            c.size = clean(m.group(0)) if m else value
        elif not c.city and any(label.startswith(l) for l in HQ_LABELS):
            c.city = value

    if not c.size:
        m = re.search(r"\d[\d,.\s K+–-]*\s*(?:employees|працівник\w*|співробітник\w*|сотрудник\w*)",
                      s.get_text(" "), re.I)
        c.size = clean(m.group(0)) if m else ""
    return c


NOISE_RE = re.compile(
    r"^(?:•|·)|degree connection|^\d(?:st|nd|rd|th)\+?$|^(?:1st|2nd|3rd\+?)$|view .* profile|"
    r"переглянути|посмотреть|^(?:connect|message|follow|pending|send inmail)$|"
    r"^(?:встановити контакт|повідомлення|стежити|установить контакт|сообщение|отслеживать)$|"
    r"mutual connection|спільн\w+ контакт|общи\w+ контакт|^status is|^linkedin member$|"
    r"^учасник linkedin$|^участник linkedin$|followers$|підписник|подписчик|^premium$",
    re.I,
)
CURRENT_RE = re.compile(r"^(?:current|зараз|поточна посада|сейчас|текущая должность)\s*:\s*(.+)$", re.I)


def _lines(tag: Tag) -> list[str]:
    out: list[str] = []
    for raw in tag.get_text("\n").split("\n"):
        line = clean(raw)
        if line and (not out or out[-1] != line):
            out.append(line)
    return out


def _card_name(card: Tag, link: Tag) -> str:
    for sel in (".artdeco-entity-lockup__title", ".entity-result__title-text a span[aria-hidden='true']"):
        el = card.select_one(sel)
        if el and clean(el.get_text(" ")):
            return clean(el.get_text(" "))
    for el in [link] + card.select("a[href*='/in/']"):
        span = el.select_one("span[aria-hidden='true']")
        text = clean(span.get_text(" ")) if span else (_lines(el)[0] if _lines(el) else "")
        if text and not NOISE_RE.search(text):
            return text
    return ""


def parse_people_cards(html: str, default_company: str = "") -> list[Person]:
    """Карточки людей: вкладка People компании или результаты поиска."""
    s = BeautifulSoup(html, "html.parser")
    root = s.select_one("main") or s
    people, seen = [], set()
    for link in root.select("a[href*='/in/']"):
        url = profile_url(link.get("href", ""))
        if not url or url in seen:
            continue
        card = link.find_parent("li") or link.find_parent("div")
        if card is None:
            continue
        name = _card_name(card, link)
        if not name or NOISE_RE.search(name):
            continue
        seen.add(url)

        headline = ""
        for sel in (".artdeco-entity-lockup__subtitle", ".entity-result__primary-subtitle"):
            el = card.select_one(sel)
            if el and clean(el.get_text(" ")):
                headline = clean(el.get_text(" "))
                break
        lines = [l for l in _lines(card) if l != name and not NOISE_RE.search(l)]
        current = next((CURRENT_RE.match(l).group(1) for l in lines if CURRENT_RE.match(l)), "")
        if not headline:
            headline = next((l for l in lines if not CURRENT_RE.match(l)), "")

        title, company = split_headline(current or headline)
        if not company and current:
            title, company = split_headline(headline)
        if default_company:
            company = company or default_company
        first, last = split_name(name)
        people.append(Person(first, last, title, company, url, SOURCE))
    return people


CURRENT_COMPANY_RE = re.compile(
    r"(?:current company|поточна компанія|текущая компания|company)\s*:\s*(.+?)(?:\.\s|$)", re.I)


def parse_profile(html: str, url: str) -> Person:
    s = BeautifulSoup(html, "html.parser")
    main = s.select_one("main") or s
    h1 = main.select_one("h1")
    name = clean(h1.get_text(" ")) if h1 else ""
    headline_el = main.select_one(".text-body-medium.break-words, [data-generated-suggestion-target]")
    headline = clean(headline_el.get_text(" ")) if headline_el else ""
    title, company = split_headline(headline)

    for el in main.select("[aria-label]"):
        m = CURRENT_COMPANY_RE.search(el.get("aria-label", ""))
        if m:
            company = clean(m.group(1))
            break
    first, last = split_name(name)
    return Person(first, last, title, company, profile_url(url) or normalize_url(url), SOURCE)


# ---------- работа с браузером ----------

class LinkedInScraper:
    def __init__(self, runner: "Runner"):
        self.r = runner

    # сколько ещё профилей можно собрать в этом запуске
    @property
    def budget(self) -> int:
        return self.r.settings.limit - self.r.li_profiles

    def _need_budget(self) -> None:
        if self.budget <= 0:
            raise LinkError(f"достигнут лимит {self.r.settings.limit} профилей LinkedIn за запуск (LIMIT в .env)")

    def _open(self, url: str, wait_for: str | None = None) -> str:
        try:
            # без повтора при 403: лишние запросы к LinkedIn только вредят аккаунту
            self.r.open(url, wait_for=wait_for or "main", retry=False)
        except LinkError as e:
            check_page(self.r.page.url, self.r.page.content())  # логин/капча -> понятный StopRun
            if str(e).startswith("HTTP"):
                raise LinkError(f"{e}: LinkedIn не отдал страницу. Проверьте вход: кнопка «Войти» или python main.py --login") from None
            raise
        self.r.sleep_random(1.5, 3)  # даём догрузиться динамике
        html = self.r.page.content()
        check_page(self.r.page.url, html)
        return html

    def _take(self, people: list[Person]) -> list[Person]:
        people = people[: max(self.budget, 0)]
        self.r.li_profiles += len(people)
        return people

    def scrape(self, url: str) -> Iterator[tuple[list[Person], list[Company]]]:
        kind = classify(url)
        if kind == "company":
            yield [], [self._company(url)]
        elif kind == "company_people":
            company = self._company(url)
            yield [], [company]
            if not self.r.stopped:
                self._need_budget()
                yield from self._people_tab(url, company.name)
        elif kind == "search":
            self._need_budget()
            yield from self._search(url)
        elif kind == "person":
            self._need_budget()
            html = self._open(url, wait_for="main h1")
            p = parse_profile(html, url)
            if not p.first_name:
                raise LinkError("не найдено имя в профиле")
            yield self._take([p]), []
        else:
            raise LinkError("неизвестный тип ссылки LinkedIn (нужны /company/…, /company/…/people/, "
                            "/search/results/people/… или /in/…)")

    def _company(self, url: str) -> Company:
        html = self._open(company_root(url) + "about/", wait_for="main h1")
        c = parse_company(html, url)
        if not c.name:
            raise LinkError("страница компании не распознана (нет названия)")
        return c

    def _people_tab(self, url: str, company: str) -> Iterator[tuple[list[Person], list[Company]]]:
        page = self.r.page
        self._open(company_root(url) + "people/")
        count, still = 0, 0
        while not self.r.stopped and count < self.budget and still < 2:
            page.mouse.wheel(0, 4000)
            self.r.sleep_random(1.5, 3)
            more = page.locator("button.scaffold-finite-scroll__load-button")
            if more.count() and more.first.is_visible():
                more.first.click()
                self.r.sleep_random(2, 4)
            new = len(parse_people_cards(page.content()))
            still = still + 1 if new == count else 0
            count = new
        html = page.content()
        check_page(page.url, html)
        people = self._take(parse_people_cards(html, default_company=company))
        if not people:
            raise LinkError("на вкладке People не найдено людей (возможно, видны только «LinkedIn Member»)")
        yield people, []

    def _search(self, url: str) -> Iterator[tuple[list[Person], list[Company]]]:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        start = int(query.get("page", "1") or 1)
        seen: set[str] = set()
        total = 0
        for n in range(start, start + 100):
            if self.r.stopped or self.budget <= 0:
                break
            query["page"] = str(n)
            page_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
            try:
                self._open(page_url, wait_for="main a[href*='/in/']")
            except LinkError:
                if n == start:
                    raise
                break
            self.r.page.mouse.wheel(0, 3000)
            self.r.sleep_random(1, 2)
            html = self.r.page.content()
            check_page(self.r.page.url, html)
            fresh = [p for p in parse_people_cards(html) if p.url not in seen]
            if not fresh:
                break
            seen.update(p.url for p in fresh)
            people = self._take(fresh)
            total += len(people)
            self.r.log(f"  поиск, стр. {n}: {len(people)} чел.")
            yield people, []
        if not total and not self.r.stopped:
            raise LinkError("в результатах поиска не найдено людей")
