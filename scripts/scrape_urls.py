"""Опциональный скрипт для грубого сохранения текста страниц в data/docs/scraped.

Для курсовой основной бот уже работает на подготовленных .txt файлах.
Этот скрипт нужен только если хочешь попробовать автоматически подтянуть текст
из открытых страниц.

Запуск:
    python scripts/scrape_urls.py
"""

from __future__ import annotations

from pathlib import Path
import re

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "docs" / "scraped"
URLS_FILE = ROOT / "data" / "source_urls.txt"


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def slugify(url: str) -> str:
    value = re.sub(r"https?://", "", url)
    value = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "_", value)
    return value.strip("_").lower()[:120] or "page"


def fetch_text(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 SupportRagBotCoursework/1.0"
    }
    response = requests.get(url, timeout=25, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form", "header", "footer"]):
        tag.extract()

    title = clean_text(soup.title.get_text(" ")) if soup.title else url
    main = soup.find("main") or soup.body or soup
    text = clean_text(main.get_text("\n"))
    return f"# {title}\n\nИсточник: {url}\n\n{text}\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    urls = [
        line.strip()
        for line in URLS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    for url in urls:
        try:
            text = fetch_text(url)
            path = OUT_DIR / f"{slugify(url)}.txt"
            path.write_text(text, encoding="utf-8")
            print(f"OK: {url} -> {path}")
        except Exception as exc:
            print(f"ERROR: {url}: {exc}")


if __name__ == "__main__":
    main()
