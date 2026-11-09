from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

URL = "https://t.me/s/SvitloOleksandriyskohoRaionu"
TZ_NAME = "Europe/Kyiv"
TZ = ZoneInfo(TZ_NAME)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
}

# ---------- Регулярні вирази ----------

# Рядок черги: "Черга 1.1: 07-08, 10-12", "🔴 1.1 — 07:00-08:00", "Підчерга 3.2: ..."
# Префікс — лише нецифрові символи (емодзі, слово "Черга" тощо), щоб не
# плутати з датою "09.11.2026".
QUEUE_LINE_RE = re.compile(
    r"^[^\d\n]*?(?<![\d.])([1-6])\.([12])(?![\d.])\s*[:：\-–—]?\s*(.*)$"
)

# Інтервал: "07-08", "7–9", "07:00-08:30", "22-24", "22-00"
INTERVAL_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*[-–—]\s*(\d{1,2})(?::(\d{2}))?(?!\d)"
)

DATE_RE = re.compile(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{4})(?!\d)")
AS_OF_RE = re.compile(r"станом\s+на\s+(\d{1,2})[:.](\d{2})", re.IGNORECASE)
KEYWORD_RE = re.compile(r"Черга|ГПВ|Підчерга", re.IGNORECASE)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------- Завантаження ----------

def fetch_html(url: str = URL, retries: int = 3, timeout: int = 20) -> str:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as e:
            last_err = e
            log(f"[fetch] спроба {attempt}/{retries} не вдалася: {e}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"Не вдалося завантажити {url}: {last_err}")


# ---------- Допоміжне ----------

def message_text(msg) -> str:
    """Текст повідомлення з <br> -> \\n, без втрати рядків усередині <b>/<i>/<a>."""
    node = msg.select_one(".tgme_widget_message_text")
    if node is None:
        return ""
    for br in node.find_all("br"):
        br.replace_with("\n")
    text = node.get_text("")
    text = text.replace("\xa0", " ").replace("\u200b", "")
    return text


def post_datetime(msg) -> datetime | None:
    """Час публікації з <time datetime="..."> у Europe/Kyiv."""
    t = msg.select_one("a.tgme_widget_message_date time, time.tgme_widget_message_date, time")
    if t is None or not t.get("datetime"):
        return None
    try:
        dt = datetime.fromisoformat(t["datetime"].replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TZ)


def fmt_hhmm(h: int, m: int = 0) -> str:
    return f"{h:02d}:{m:02d}"


def parse_intervals(rest: str) -> list[dict]:
    out: list[dict] = []
    for m in INTERVAL_RE.finditer(rest):
        sh, sm = int(m.group(1)), int(m.group(2) or 0)
        eh, em = int(m.group(3)), int(m.group(4) or 0)
        if eh == 0 and em == 0:  # "22-00" -> північ
            eh = 24
        if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 < eh <= 24 and 0 <= em <= 59):
            continue
        if eh == 24 and em != 0:
            continue
        if (eh, em) <= (sh, sm):
            continue
        out.append({"start": fmt_hhmm(sh, sm), "end": fmt_hhmm(eh, em), "status": "off"})
    return out


def merge_adjacent(intervals: list[dict]) -> list[dict]:
    """Склеює 10-11 + 11-12 у 10-12 (залишає порядок за часом)."""
    intervals = sorted(intervals, key=lambda x: x["start"])
    merged: list[dict] = []
    for iv in intervals:
        if merged and merged[-1]["end"] == iv["start"]:
            merged[-1]["end"] = iv["end"]
        else:
            merged.append(dict(iv))
    return merged


# ---------- Розбір одного поста ----------

def parse_post_text(text: str, fallback_date: date) -> dict[str, dict[str, list[dict]]]:
    """
    Повертає {"YYYY-MM-DD": {"1.1": [intervals], ...}}.
    Якщо в пості кілька дат (сьогодні + завтра), рядки черг
    привʼязуються до останньої дати, що зустрілась вище.
    """
    result: dict[str, dict[str, list[dict]]] = {}

    # Дата, що зустрілась у тексті до першої черги (напр. у заголовку).
    current = fallback_date
    first_date = DATE_RE.search(text)
    if first_date:
        d, mth, y = map(int, first_date.groups())
        try:
            current = date(y, mth, d)
        except ValueError:
            pass

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        qm = QUEUE_LINE_RE.match(line)
        if qm:
            sub = f"{qm.group(1)}.{qm.group(2)}"
            intervals = parse_intervals(qm.group(3))
            if intervals:
                day = result.setdefault(current.isoformat(), {})
                day.setdefault(sub, []).extend(intervals)
            continue

        dm = DATE_RE.search(line)
        if dm:
            d, mth, y = map(int, dm.groups())
            try:
                current = date(y, mth, d)
            except ValueError:
                pass

    for day in result.values():
        for sub in list(day):
            day[sub] = merge_adjacent(day[sub])

    return result


def sort_subqueues(day: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {k: day[k] for k in sorted(day, key=lambda s: tuple(map(int, s.split("."))))}


# ---------- Пошук останнього релевантного поста ----------

def find_latest_schedule(html: str, debug: bool = False):
    soup = BeautifulSoup(html, "html.parser")
    messages = soup.select("div.tgme_widget_message")
    if debug:
        log(f"[parse] знайдено повідомлень: {len(messages)}")

    # На t.me/s/ найновіші пости — в кінці сторінки.
    for msg in reversed(messages):
        text = message_text(msg)
        if not text or not KEYWORD_RE.search(text):
            continue

        dt = post_datetime(msg)
        fallback = dt.date() if dt else datetime.now(TZ).date()

        schedules = parse_post_text(text, fallback)
        if not schedules:
            if debug:
                log("[parse] пост має ключові слова, але інтервалів не знайдено — пропускаю")
            continue

        # Час публікації: тег <time>, інакше «станом на HH:MM».
        if dt:
            last_post_time = dt.strftime("%H:%M")
        else:
            am = AS_OF_RE.search(text)
            last_post_time = fmt_hhmm(int(am.group(1)), int(am.group(2))) if am else ""

        if debug:
            link = msg.select_one("a.tgme_widget_message_date")
            log(f"[parse] обрано пост: {link.get('href') if link else '?'} ({last_post_time})")
        return last_post_time, schedules

    return None


# ---------- Збереження ----------

def load_existing(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json_atomic(path: str, data: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".schedule.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def build_output(last_post_time: str, new_schedules: dict, existing: dict, merge: bool) -> dict:
    schedules: dict[str, dict] = {}

    if merge:
        # Зберігаємо раніше збережені дати від вчора й пізніше (напр. «завтра» з попереднього поста).
        cutoff = (datetime.now(TZ).date() - timedelta(days=1)).isoformat()
        for day_key, day_val in (existing.get("schedules") or {}).items():
            if day_key >= cutoff and isinstance(day_val, dict):
                schedules[day_key] = day_val

    for day_key, subs in new_schedules.items():
        schedules[day_key] = {"subqueues": sort_subqueues(subs)}

    return {
        "timezone": TZ_NAME,
        "last_post_time": last_post_time,
        "schedules": dict(sorted(schedules.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Парсер графіка відключень з Telegram")
    ap.add_argument("--out", default="schedule.json", help="шлях до вихідного JSON")
    ap.add_argument("--html", help="розібрати локальний HTML-файл замість завантаження")
    ap.add_argument("--no-merge", action="store_true", help="не зберігати раніші дати з існуючого файлу")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    try:
        if args.html:
            with open(args.html, "r", encoding="utf-8") as f:
                html = f.read()
        else:
            html = fetch_html()
    except Exception as e:
        log(f"[error] {e}")
        return 1

    found = find_latest_schedule(html, debug=args.debug)
    if not found:
        # Порожній результат НЕ перезаписує останній робочий schedule.json.
        log("[error] не знайдено жодного поста з графіком; файл не змінено")
        return 2

    last_post_time, new_schedules = found
    output = build_output(
        last_post_time,
        new_schedules,
        load_existing(args.out),
        merge=not args.no_merge,
    )
    write_json_atomic(args.out, output)

    total = sum(len(v["subqueues"]) for v in output["schedules"].values())
    log(f"[ok] {args.out}: дат {len(output['schedules'])}, підчерг {total}, пост о {last_post_time}")
    return 0


if __name__ == "__main__":
    sys.exit(main())