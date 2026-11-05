"""Парсер dou.ua: страница компании, офисы (люди), каталог компаний, профиль пользователя."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterator
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from common import Company, LinkError, Person, clean, normalize_url

if TYPE_CHECKING:
    from runner import Runner

SOURCE = "dou"
COMPANY_RE = re.compile(r"^/companies/([^/]+)/?")
USER_RE = re.compile(r"^/users/([^/]+)/?")


def is_dou(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return host == "dou.ua" or host.endswith(".dou.ua")


def classify(url: str) -> str | None:
    parts = urlsplit(url)
    path = parts.path or "/"
    if USER_RE.match(path):
        return "person"
    if path.rstrip("/") == "/companies":
        return "company_list"
    if COMPANY_RE.match(path):
        return "company"
    return None


def company_root(url: str) -> str:
    slug = COMPANY_RE.match(urlsplit(url).path).group(1)
    return f"https://jobs.dou.ua/companies/{slug}/"


# ---------- разбор HTML (без браузера, легко тестировать) ----------

def parse_company(html: str, url: str) -> Company:
    s = BeautifulSoup(html, "html.parser")
    info = s.select_one(".company-info") or s
    c = Company(url=normalize_url(url), source=SOURCE)

    h1 = info.select_one("h1")
    c.name = clean(h1.get_text(" ")) if h1 else ""

    offices = info.select_one(".offices")
    c.city = clean(offices.get_text(" ")) if offices else ""

    site = info.select_one(".site a[href]")
    if site:
        href = site.get("href", "")
        c.website = href if href.startswith("http") and "dou.ua" not in href else clean(site.get_text())

    # размер — «голый» текст внутри .company-info, напр. «понад 1500 спеціалістів»
    for node in info.find_all(string=True, recursive=False):
        text = clean(node)
        if re.search(r"\d", text) and re.search(r"спеціаліст|специалист|employee|співробітник", text, re.I):
            c.size = text
            break
    return c


def parse_people(html: str, company: str) -> list[Person]:
    """Люди со страницы /offices/ (контакты компании)."""
    from common import split_name

    s = BeautifulSoup(html, "html.parser")
    seen, people = set(), []
    for a in s.select("ul.persons li a.name[href], .persons a[href*='/users/']"):
        href = urljoin("https://dou.ua/", a.get("href", ""))
        key = normalize_url(href)
        if key in seen or not USER_RE.match(urlsplit(href).path):
            continue
        seen.add(key)
        name = clean(a.get_text(" "))
        li = a.find_parent("li")
        title = ""
        if li:
            title = clean(li.get_text(" ").replace(a.get_text(" "), "", 1))
        first, last = split_name(name)
        people.append(Person(first, last, title, company, key, SOURCE))
    return people


def parse_company_list(html: str) -> list[str]:
    s = BeautifulSoup(html, "html.parser")
    urls = []
    # подгруженные кнопкой «Більше компаній» карточки приходят без <li class="l-company">
    for a in s.select("a.cn-a[href]"):
        u = company_root(urljoin("https://jobs.dou.ua/", a["href"]))
        if u not in urls:
            urls.append(u)
    return urls


def parse_user(html: str, url: str) -> Person:
    from common import split_name

    s = BeautifulSoup(html, "html.parser")
    h1 = s.select_one(".b-user-info h1, h1")
    name = ""
    if h1:
        name = clean("".join(t for t in h1.find_all(string=True, recursive=False)))
    first, last = split_name(name)
    title = company = ""
    descr = s.select_one(".descr")
    if descr:
        a = descr.select_one("a.company")
        company = clean(a.get_text(" ")) if a else ""
        text = clean(descr.get_text(" "))
        if company and text.endswith(company):
            text = text[: -len(company)]
        title = re.sub(r"\s+(в|at|у|@)\s*$", "", clean(text))
    return Person(first, last, title, company, normalize_url(url), SOURCE)


# ---------- работа с браузером ----------

class DouScraper:
    def __init__(self, runner: "Runner"):
        self.r = runner

    def scrape(self, url: str) -> Iterator[tuple[list[Person], list[Company]]]:
        kind = classify(url)
        if kind == "company":
            yield from self._company(company_root(url))
        elif kind == "person":
            html = self.r.open(url)
            p = parse_user(html, url)
            if not p.first_name:
                raise LinkError("не найдено имя на странице пользователя")
            yield [p], []
        elif kind == "company_list":
            yield from self._company_list(url)
        else:
            raise LinkError("неизвестный тип ссылки dou.ua (нужна компания, каталог /companies/ или /users/)")

    def _company(self, root: str) -> Iterator[tuple[list[Person], list[Company]]]:
        html = self.r.open(root)
        company = parse_company(html, root)
        if not company.name:
            raise LinkError("страница компании не распознана (нет названия)")
        yield [], [company]
        if self.r.stopped:
            return
        try:
            people = parse_people(self.r.open(root + "offices/"), company.name)
        except LinkError as e:
            self.r.log(f"  офисы {company.name}: {e}")
            return
        if people:
            yield people, []

    def _company_list(self, url: str) -> Iterator[tuple[list[Person], list[Company]]]:
        page = self.r.page
        self.r.open(url)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        limit = self.r.settings.dou_list_limit
        # подгружаем ещё компании кнопкой «Більше компаній»
        while len(parse_company_list(page.content())) < limit and not self.r.stopped:
            btn = page.locator(".more-btn a")
            if not btn.count() or not btn.first.is_visible():
                break
            before = len(parse_company_list(page.content()))
            self.r.sleep_random(self.r.settings.pause_min, self.r.settings.pause_max)
            try:
                with page.expect_response(lambda resp: "xhr-load" in resp.url, timeout=15000):
                    btn.first.click()
            except Exception:
                break
            self.r.sleep_random(1, 2)
            if len(parse_company_list(page.content())) == before:
                break
        urls = parse_company_list(page.content())[:limit]
        if not urls:
            raise LinkError("в каталоге не найдено компаний")
        self.r.log(f"  в каталоге {len(urls)} компаний")
        for u in urls:
            if self.r.stopped:
                return
            try:
                yield from self._company(u)
            except LinkError as e:
                self.r.error(u, str(e))
            except Exception as e:  # одна компания не должна обрывать весь каталог
                self.r.error(u, f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}")
