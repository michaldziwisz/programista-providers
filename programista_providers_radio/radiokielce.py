from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_text


RKIELCE_BASE = "https://radiokielce.pl"
RKIELCE_INDEX_URL = f"{RKIELCE_BASE}/ramowka/"


@dataclass(frozen=True)
class _RkielceProgramme:
    start: time | None
    title: str


class RadioKielceProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "radiokielce"

    @property
    def display_name(self) -> str:
        return "Radio Kielce"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("rkielce"),
                name="Radio Kielce",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
        index = self._fetch_index(force_refresh=force_refresh)
        days = sorted(index.keys())
        if days:
            return days

        today = date.today()
        start = today - timedelta(days=3)
        return [start + timedelta(days=i) for i in range(7)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        if str(source.id) != "rkielce":
            return []

        index = self._fetch_index(force_refresh=force_refresh)
        url = index.get(day)
        if not url:
            return []

        html = self._http.get_text(
            url,
            cache_key=f"rkielce:day:{day.isoformat()}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        programmes = parse_rkielce_day_html(html)
        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=p.start,
                end_time=None,
                title=p.title,
                subtitle=None,
                details_ref=None,
                details_summary=None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title

    def _fetch_index(self, *, force_refresh: bool) -> dict[date, str]:
        html = self._http.get_text(
            RKIELCE_INDEX_URL,
            cache_key="rkielce:index",
            ttl_seconds=60 * 20,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        return parse_rkielce_index_html(html)


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def _parse_month_number(month_name: str) -> int | None:
    key = _strip_accents(clean_text(month_name).casefold())
    months = {
        "styczen": 1,
        "luty": 2,
        "marzec": 3,
        "kwiecien": 4,
        "maj": 5,
        "czerwiec": 6,
        "lipiec": 7,
        "sierpien": 8,
        "wrzesien": 9,
        "pazdziernik": 10,
        "listopad": 11,
        "grudzien": 12,
    }
    return months.get(key)


def _parse_time_hhmm_loose(text: str) -> time | None:
    t = clean_text(text)
    m = re.fullmatch(r"(\d{1,2})\s*[:.]\s*(\d{2})", t)
    if not m:
        return None
    try:
        hh = int(m.group(1))
        mm = int(m.group(2))
    except ValueError:
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return time(hh, mm)


def parse_rkielce_index_html(html: str) -> dict[date, str]:
    soup = BeautifulSoup(html, "lxml")
    current_year, current_month = _parse_mec_current_year_month(html)

    out: dict[date, str] = {}
    for article in soup.select("article.mec-event-article"):
        href_el = article.select_one(".mec-event-title a[href]")
        href_raw = clean_text(href_el.get("href") or "") if href_el else ""
        if not href_raw:
            continue
        href = urljoin(RKIELCE_BASE, href_raw)

        day_el = article.select_one(".mec-event-date .event-d")
        day_s = clean_text(day_el.get_text(" ")) if day_el else ""
        if not day_s.isdigit():
            continue
        day = int(day_s)

        year, month = _parse_article_year_month(article, fallback=(current_year, current_month))
        if not year or not month:
            continue

        try:
            d = date(year, month, day)
        except ValueError:
            continue
        out[d] = href
    return out


def _parse_article_year_month(article, *, fallback: tuple[int | None, int | None]) -> tuple[int | None, int | None]:
    classes = article.get("class") or []
    cls_s = " ".join([c for c in classes if isinstance(c, str)])
    m = re.search(r"\bmec-toggle-(\d{6})\b", cls_s)
    if m:
        yyyymm = m.group(1)
        try:
            return int(yyyymm[:4]), int(yyyymm[4:])
        except ValueError:
            return fallback

    month_name_el = article.select_one(".mec-event-date .event-f")
    month_name = clean_text(month_name_el.get_text(" ")) if month_name_el else ""
    month_num = _parse_month_number(month_name) if month_name else None
    year, month = fallback
    return year, month_num or month


def _parse_mec_current_year_month(html: str) -> tuple[int | None, int | None]:
    m = re.search(r"var\s+mecdata\s*=\s*(\{.*?\});", html, flags=re.S)
    if not m:
        return None, None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None, None
    year_raw = clean_text(str(data.get("current_year") or ""))
    month_raw = clean_text(str(data.get("current_month") or ""))
    try:
        year = int(year_raw) if year_raw.isdigit() else None
        month = int(month_raw) if month_raw.isdigit() else None
    except ValueError:
        return None, None
    return year, month


def parse_rkielce_day_html(html: str) -> list[_RkielceProgramme]:
    soup = BeautifulSoup(html, "lxml")
    desc = soup.select_one(".mec-single-event-description") or soup.select_one(".mec-events-content")
    if not desc:
        return []

    programmes: list[_RkielceProgramme] = []
    for raw_line in desc.get_text("\n").splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        m = re.match(r"^godz\.?\s*(\d{1,2}[:.]\d{2})\b\s*(.*)$", line, flags=re.I)
        if not m:
            continue
        start = _parse_time_hhmm_loose(m.group(1))
        title = clean_text(m.group(2))
        if not title:
            continue
        programmes.append(_RkielceProgramme(start=start, title=title))

    programmes.sort(key=lambda p: p.start or time.min)
    return programmes
