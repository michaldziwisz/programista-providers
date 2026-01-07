from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


RO_BASE = "https://radioolsztyn.pl"
RO_SCHEDULE_INDEX_URL = f"{RO_BASE}/mvc/ramowka/date/"


@dataclass(frozen=True)
class _RoProgramme:
    start: time | None
    title: str
    details: str


class RadioOlsztynProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "radioolsztyn"

    @property
    def display_name(self) -> str:
        return "Radio Olsztyn"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("olsztyn"),
                name="Radio Olsztyn",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
        html = self._http.get_text(
            RO_SCHEDULE_INDEX_URL,
            cache_key="ro:ramowka:index",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        days = parse_ro_days_html(html)
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
        if str(source.id) != "olsztyn":
            return []

        url = f"{RO_SCHEDULE_INDEX_URL}{day.isoformat()}"
        html = self._http.get_text(
            url,
            cache_key=f"ro:ramowka:{day.isoformat()}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )

        programmes = parse_ro_ramowka_html(html)
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
                details_summary=p.details or None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title


def parse_ro_days_html(html: str) -> list[date]:
    soup = BeautifulSoup(html, "lxml")
    out: set[date] = set()
    for a in soup.select('a[href*="/mvc/ramowka/date/"]'):
        href = clean_text(a.get("href") or "")
        m = re.search(r"/mvc/ramowka/date/(\\d{4}-\\d{2}-\\d{2})\\b", href)
        if not m:
            continue
        try:
            out.add(date.fromisoformat(m.group(1)))
        except ValueError:
            continue
    return sorted(out)


def parse_ro_ramowka_html(html: str) -> list[_RoProgramme]:
    soup = BeautifulSoup(html, "lxml")
    programmes: list[_RoProgramme] = []

    for inner in soup.select(".ramowkaItemInner"):
        header = inner.select_one(".ramowkaItemHeader")
        if not header:
            continue

        title_el = header.select_one(".ramowkaTitleLink, .ramowkaTitleNoLink")
        if not title_el:
            continue

        time_el = title_el.select_one("b")
        start = parse_time_hhmm(clean_text(time_el.get_text(" "))) if time_el else None
        start_s = start.strftime("%H:%M") if start else ""

        title_text = clean_text(title_el.get_text(" ", strip=True))
        title = clean_text(title_text[len(start_s) :]) if start_s and title_text.startswith(start_s) else title_text
        if not title:
            continue

        opis_el = inner.select_one(".ramowkaItemOpis")
        details = clean_multiline_text(opis_el.get_text("\n")) if opis_el else ""

        programmes.append(_RoProgramme(start=start, title=title, details=details))

    # Remove exact duplicates (the site occasionally repeats identical entries).
    seen: set[tuple[str, str, str]] = set()
    out: list[_RoProgramme] = []
    for p in programmes:
        key = (p.start.strftime("%H:%M") if p.start else "", p.title.casefold(), p.details.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out

