"""Запуск из консоли.

    python main.py input.txt     # собрать контакты по ссылкам из файла
    python main.py --login       # один раз войти в LinkedIn руками
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import Settings


def login(settings: Settings) -> None:
    from playwright.sync_api import sync_playwright

    from runner import open_browser_context

    settings.headless = False
    with sync_playwright() as pw:
        ctx = open_browser_context(pw, settings)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/login")
        print("Войдите в LinkedIn в открывшемся окне браузера (логин, пароль, код подтверждения).")
        input("Когда увидите свою ленту LinkedIn — нажмите Enter здесь, чтобы сохранить сессию… ")
        ctx.close()
    print(f"Сессия сохранена в {settings.profile_dir}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Сбор контактов с dou.ua и LinkedIn в Google Sheets")
    ap.add_argument("input", nargs="?", help="файл со ссылками, по одной в строке")
    ap.add_argument("--login", action="store_true", help="открыть браузер для первого входа в LinkedIn")
    ap.add_argument("--limit", type=int, help="лимит профилей LinkedIn за запуск (по умолчанию LIMIT из .env)")
    args = ap.parse_args()

    settings = Settings()
    if args.login:
        login(settings)
        return 0
    if not args.input:
        ap.print_help()
        return 1
    if args.limit:
        settings.limit = args.limit

    from runner import Runner, read_links
    from sheets import open_store

    path = Path(args.input)
    if not path.is_file():
        print(f"Файл не найден: {path}")
        return 1
    urls = read_links(path.read_text(encoding="utf-8"))
    if not urls:
        print("В файле нет ссылок")
        return 1

    try:
        store = open_store(settings)
    except Exception as e:
        print(f"Не удалось подключиться к таблице: {e}")
        return 1
    print(f"Результат: {store.url}")

    runner = Runner(store, settings, on_log=print)
    try:
        result = runner.run(urls)
    except KeyboardInterrupt:
        runner.stop()
        return 130
    return 0 if not result["message"].startswith(("СТОП", "Запуск прерван")) else 2


if __name__ == "__main__":
    sys.exit(main())
