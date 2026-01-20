from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_text, parse_time_hhmm


RB_BASE = "https://www.radio.bialystok.pl"
RB_INDEX_URL = f"{RB_BASE}/ramowka/index"


@dataclass(frozen=True)
class _RbProgramme:
    start: time | None
    title: str


class RadioBialystokProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "radiobialystok"

    @property
    def display_name(self) -> str:
        return "Radio Białystok"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("bialystok"),
                name="Radio Białystok",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
        html = self._http.get_text(
            RB_INDEX_URL,
            cache_key="rbialystok:index",
            ttl_seconds=60 * 20,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        index = parse_rb_index_html(html)
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
        if str(source.id) != "bialystok":
            return []

        index_html = self._http.get_text(
            RB_INDEX_URL,
            cache_key="rbialystok:index",
            ttl_seconds=60 * 20,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        index = parse_rb_index_html(index_html)
        url = index.get(day) or _rb_day_url(day)

        html = self._http.get_text(
            url,
            cache_key=f"rbialystok:day:{day.isoformat()}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        programmes = parse_rb_day_html(html)
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


def _rb_day_url(day: date) -> str:
    return f"{RB_BASE}/ramowka/index/d/{day:%d}/m/{day:%m}/y/{day:%Y}"


def parse_rb_index_html(html: str) -> dict[date, str]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[date, str] = {}

    for a in soup.select('a[href*="/ramowka/index/d/"]'):
        href_raw = clean_text(a.get("href") or "")
        m = re.search(r"/ramowka/index/d/(\d{1,2})/m/(\d{1,2})/y/(\d{4})\b", href_raw)
        if not m:
            continue
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        out[d] = urljoin(RB_BASE, href_raw)

    # Also include the currently displayed day if available in the header.
    h1 = soup.select_one("h1")
    if h1:
        m = re.search(
            r"\bRAMÓWKA\s*-\s*(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})\b",
            clean_text(h1.get_text(" ")),
            flags=re.I,
        )
        if m:
            month = _parse_month_number_pl(m.group(2))
            if month:
                try:
                    d = date(int(m.group(3)), month, int(m.group(1)))
                except ValueError:
                    d = None
                if d:
                    out.setdefault(d, RB_INDEX_URL)

    return out


def parse_rb_day_html(html: str) -> list[_RbProgramme]:
    soup = BeautifulSoup(html, "lxml")
    programmes: list[_RbProgramme] = []

    for time_div in soup.select("div.ram2f.text-center"):
        time_el = time_div.select_one("span.ram2data")
        time_s = clean_text(time_el.get_text(" ")) if time_el else ""
        if not re.fullmatch(r"\d{1,2}:\d{2}", time_s):
            continue
        try:
            start = parse_time_hhmm(time_s)
        except Exception:  # noqa: BLE001
            continue

        title_div = time_div.find_next_sibling("div")
        while title_div and "ram2f" not in (title_div.get("class") or []):
            title_div = title_div.find_next_sibling("div")
        if not title_div:
            continue

        title_el = title_div.select_one("span.ram2data")
        title = clean_text(title_el.get_text(" ")) if title_el else ""
        if not title:
            continue

        programmes.append(_RbProgramme(start=start, title=title))

    # Remove exact duplicates.
    seen: set[tuple[str, str]] = set()
    out: list[_RbProgramme] = []
    for p in programmes:
        key = (p.start.strftime("%H:%M") if p.start else "", p.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)

    out.sort(key=lambda p: p.start or time.min)
    return out


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def _parse_month_number_pl(month_name: str) -> int | None:
    key = _strip_accents(clean_text(month_name).casefold())
    months = {
        "styczen": 1,
        "stycznia": 1,
        "luty": 2,
        "lutego": 2,
        "marzec": 3,
        "marca": 3,
        "kwiecien": 4,
        "kwietnia": 4,
        "maj": 5,
        "maja": 5,
        "czerwiec": 6,
        "czerwca": 6,
        "lipiec": 7,
        "lipca": 7,
        "sierpien": 8,
        "sierpnia": 8,
        "wrzesien": 9,
        "wrzesnia": 9,
        "pazdziernik": 10,
        "pazdziernika": 10,
        "listopad": 11,
        "listopada": 11,
        "grudzien": 12,
        "grudnia": 12,
    }
    return months.get(key)
