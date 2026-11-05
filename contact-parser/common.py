"""Общие модели, настройки и утилиты."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _path(value: str) -> str:
    """Относительные пути из .env считаем от папки проекта."""
    if not value:
        return ""
    p = Path(value).expanduser()
    return str(p if p.is_absolute() else BASE_DIR / p)


@dataclass
class Settings:
    sheet_id: str = field(default_factory=lambda: os.getenv("SHEET_ID", "").strip())
    google_key_path: str = field(default_factory=lambda: _path(os.getenv("GOOGLE_KEY_PATH", "").strip()))
    limit: int = field(default_factory=lambda: _int("LIMIT", 100))
    dou_list_limit: int = field(default_factory=lambda: _int("DOU_LIST_LIMIT", 50))
    pause_min: float = field(default_factory=lambda: _float("PAUSE_MIN", 3))
    pause_max: float = field(default_factory=lambda: _float("PAUSE_MAX", 8))
    headless: bool = field(default_factory=lambda: os.getenv("HEADLESS", "false").strip().lower() in ("1", "true", "yes"))
    profile_dir: str = field(default_factory=lambda: _path(os.getenv("BROWSER_PROFILE_DIR", "browser_profile")))
    browser_path: str = field(default_factory=lambda: os.getenv("BROWSER_PATH", "").strip())
    errors_log: str = field(default_factory=lambda: str(BASE_DIR / "errors.log"))


PEOPLE_HEADERS = ["Имя", "Фамилия", "Должность", "Компания", "Ссылка на профиль", "Источник", "Дата сбора"]
COMPANY_HEADERS = ["Название", "Сайт", "Город", "Размер", "Ссылка на страницу", "Источник", "Дата сбора"]
LINK_COLUMN = 5  # в обоих листах ссылка — 5-я колонка (ключ для дублей)


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


@dataclass
class Person:
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    company: str = ""
    url: str = ""
    source: str = ""
    date: str = field(default_factory=today)

    def row(self) -> list[str]:
        return [self.first_name, self.last_name, self.title, self.company, self.url, self.source, self.date]


@dataclass
class Company:
    name: str = ""
    website: str = ""
    city: str = ""
    size: str = ""
    url: str = ""
    source: str = ""
    date: str = field(default_factory=today)

    def row(self) -> list[str]:
        return [self.name, self.website, self.city, self.size, self.url, self.source, self.date]


class StopRun(Exception):
    """Нужно остановить весь запуск (капча, предупреждение LinkedIn)."""


class LinkError(Exception):
    """Ошибка по конкретной ссылке — пишем в errors.log и идём дальше."""


def clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(url: str) -> str:
    """Ключ для дублей: https, без www/параметров/якоря, со слэшем в конце."""
    url = clean(url)
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # ua.linkedin.com, de.linkedin.com и т.п. — тот же профиль
    if host.endswith(".linkedin.com"):
        host = "linkedin.com"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if not path.endswith("/"):
        path += "/"
    if host == "linkedin.com":
        path = path.lower() if not re.match(r"^/in/acoa", path, re.I) else path
    return urlunsplit(("https", host, path, "", ""))


_NAME_SUFFIX = re.compile(r",.*$")          # «, MBA», «, PhD» и т.п.
_NAME_PARENS = re.compile(r"\([^)]*\)|\[[^\]]*\]")  # «(Lena)», «[she/her]»


def split_name(full: str) -> tuple[str, str]:
    """'Анна Петренко, MBA' -> ('Анна', 'Петренко')."""
    full = clean(_NAME_SUFFIX.sub("", _NAME_PARENS.sub(" ", clean(full))))
    # убираем эмодзи и прочие не-буквенные символы по краям
    full = clean(re.sub(r"[^\w\s'’.\-]", " ", full))
    if not full:
        return "", ""
    parts = full.split(" ", 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


# длинные варианты раньше коротких; «in» не берём: «Engineer in Kyiv» — это город, а не компания
_AT = re.compile(r"\s+(?:в компании|at|в|у)\s+|\s*@\s*", re.I)


def split_headline(headline: str) -> tuple[str, str]:
    """'CEO at Acme | Investor' -> ('CEO', 'Acme'). Если компании нет — ('<headline>', '')."""
    headline = clean(headline)
    if not headline:
        return "", ""
    m = _AT.search(headline)
    if not m:
        return headline, ""
    title = clean(headline[: m.start()])
    company = clean(re.split(r"\s+[|•·–—-]\s+|\s*\|\s*|,\s+", headline[m.end():])[0])
    return title, company
