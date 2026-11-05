"""Запись в Google Sheets (листы People и Companies) без дублей.

Если SHEET_ID в .env не задан — пишет в CSV в папку output/ (удобно для проверки).
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from common import BASE_DIR, COMPANY_HEADERS, LINK_COLUMN, PEOPLE_HEADERS, Company, Person, Settings, normalize_url

PEOPLE_SHEET = "People"
COMPANIES_SHEET = "Companies"


class _Dedup:
    def __init__(self):
        self.keys: dict[str, set[str]] = {PEOPLE_SHEET: set(), COMPANIES_SHEET: set()}

    def fresh(self, sheet: str, records: list) -> list:
        out = []
        for r in records:
            key = normalize_url(r.url)
            if not key or key in self.keys[sheet]:
                continue
            self.keys[sheet].add(key)
            out.append(r)
        return out


class SheetStore(_Dedup):
    def __init__(self, sheet_id: str, key_path: str):
        super().__init__()
        import gspread

        if not key_path or not Path(key_path).is_file():
            raise RuntimeError(f"Не найден ключ service account: {key_path or '(GOOGLE_KEY_PATH не задан)'}")
        gc = gspread.service_account(filename=key_path)
        try:
            self.sh = gc.open_by_key(sheet_id)
        except gspread.exceptions.SpreadsheetNotFound:
            raise RuntimeError("Таблица не найдена или нет доступа. Откройте таблицу и дайте доступ "
                               "«Редактор» для client_email из JSON-ключа.") from None
        self.ws = {
            PEOPLE_SHEET: self._sheet(PEOPLE_SHEET, PEOPLE_HEADERS),
            COMPANIES_SHEET: self._sheet(COMPANIES_SHEET, COMPANY_HEADERS),
        }
        for name, ws in self.ws.items():
            self.keys[name] = {normalize_url(v) for v in ws.col_values(LINK_COLUMN)[1:] if v}
        self.url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"

    def _sheet(self, title: str, headers: list[str]):
        import gspread

        try:
            ws = self.sh.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            ws = self.sh.add_worksheet(title=title, rows=1000, cols=len(headers))
        first = ws.row_values(1)
        if not any(first):
            ws.update(range_name="A1", values=[headers])
        elif first[: len(headers)] != headers:
            raise RuntimeError(
                f"На листе «{title}» уже есть другие заголовки: {', '.join(first[:len(headers)])}. "
                f"Нужны: {', '.join(headers)}. Переименуйте этот лист или очистите первую строку."
            )
        return ws

    def _append(self, sheet: str, records: list) -> list:
        """Пишет только новые записи и возвращает их список."""
        records = self.fresh(sheet, records)
        if records:
            self.ws[sheet].append_rows([r.row() for r in records], value_input_option="RAW")
        return records

    def add_people(self, people: list[Person]) -> list[Person]:
        return self._append(PEOPLE_SHEET, people)

    def add_companies(self, companies: list[Company]) -> list[Company]:
        return self._append(COMPANIES_SHEET, companies)


class CsvStore(_Dedup):
    def __init__(self, folder: str | Path = BASE_DIR / "output"):
        super().__init__()
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.files = {
            PEOPLE_SHEET: (self.folder / "people.csv", PEOPLE_HEADERS),
            COMPANIES_SHEET: (self.folder / "companies.csv", COMPANY_HEADERS),
        }
        for name, (path, headers) in self.files.items():
            if path.exists():
                with path.open(encoding="utf-8-sig", newline="") as f:
                    rows = list(csv.reader(f))[1:]
                self.keys[name] = {normalize_url(r[LINK_COLUMN - 1]) for r in rows if len(r) >= LINK_COLUMN}
            else:
                with path.open("w", encoding="utf-8-sig", newline="") as f:
                    csv.writer(f).writerow(headers)
        self.url = self.folder.resolve().as_uri()

    def _append(self, sheet: str, records: list) -> list:
        records = self.fresh(sheet, records)
        if records:
            with self.files[sheet][0].open("a", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(r.row() for r in records)
        return records

    def add_people(self, people: list[Person]) -> list[Person]:
        return self._append(PEOPLE_SHEET, people)

    def add_companies(self, companies: list[Company]) -> list[Company]:
        return self._append(COMPANIES_SHEET, companies)


def open_store(settings: Settings):
    if settings.sheet_id:
        return SheetStore(settings.sheet_id, settings.google_key_path)
    return CsvStore(os.getenv("OUTPUT_DIR") or BASE_DIR / "output")
