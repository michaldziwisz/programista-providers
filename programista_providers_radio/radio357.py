from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


R357_URL = "https://radio357.pl/ramowka/"


@dataclass(frozen=True)
class _R357Programme:
    start: time | None
    title: str
    details: str


class Radio357Provider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "radio357"

    @property
    def display_name(self) -> str:
        return "Radio 357"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("r357"),
                name="Radio 357",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
        week = self._fetch_week(force_refresh=force_refresh)
        days = sorted(week.keys())
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
        if str(source.id) != "r357":
            return []

        week = self._fetch_week(force_refresh=force_refresh)
        programmes = week.get(day, [])

        items: list[ScheduleItem] = []
        for programme in programmes:
            items.append(
                ScheduleItem(
                    provider_id=ProviderId(self.provider_id),
                    source=source,
                    day=day,
                    start_time=programme.start,
                    end_time=None,
                    title=programme.title,
                    subtitle=None,
                    details_ref=None,
                    details_summary=programme.details or None,
                )
            )
        return items

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:
        return item.details_summary or item.title

    def _fetch_week(self, *, force_refresh: bool) -> dict[date, list[_R357Programme]]:
        html = self._http.get_text(
            R357_URL,
            cache_key="r357:ramowka",
            ttl_seconds=60 * 20,
            force_refresh=force_refresh,
        )
        return parse_r357_ramowka_html(html)


def parse_r357_ramowka_html(html: str, *, today: date | None = None) -> dict[date, list[_R357Programme]]:
    soup = BeautifulSoup(html, "lxml")
    nav_items = soup.select("#scheduleNav .scheduleWrap")
    slides = soup.select("#scheduleList .swiper-wrapper > .swiper-slide")

    count = min(len(nav_items), len(slides))
    if count == 0:
        return {}

    current_day = today or date.today()
    idx_today = _find_today_index(nav_items[:count], current_day)

    days_by_index: list[date] = []
    for index, nav in enumerate(nav_items[:count]):
        computed = current_day + timedelta(days=index - idx_today)
        date_label_el = nav.select_one(".scheduleDate")
        date_label = clean_text(date_label_el.get_text(" ")) if date_label_el else ""
        ddmm = _parse_ddmm(date_label)
        if ddmm and (computed.day, computed.month) != ddmm:
            computed = _closest_date_with_day_month(computed, ddmm)
        days_by_index.append(computed)

    by_day: dict[date, list[_R357Programme]] = {}
    for index in range(count):
        day = days_by_index[index]
        slide = slides[index]
        programmes: list[_R357Programme] = []
        for el in slide.select(".podcastElement"):
            time_el = el.select_one(".podcastHour span.h2")
            start = parse_time_hhmm(clean_text(time_el.get_text(" "))) if time_el else None

            title_el = el.select_one("h3.podcastSubTitle")
            title = clean_text(title_el.get_text(" ")) if title_el else ""
            if not title:
                continue

            author_el = el.select_one(".podcastAuthor")
            author = _normalize_author_text(
                clean_text(author_el.get_text(" ", strip=True)) if author_el else ""
            )

            desc_el = el.select_one(".podcastDesc")
            description = clean_multiline_text(desc_el.get_text("\n")) if desc_el else ""

            details_parts = [part for part in (author, description) if part]
            details = "\n\n".join(details_parts)

            programmes.append(_R357Programme(start=start, title=title, details=details))

        by_day[day] = programmes
    return by_day


def _find_today_index(nav_items, today: date) -> int:
    for idx, nav in enumerate(nav_items):
        date_label_el = nav.select_one(".scheduleDate")
        date_label = clean_text(date_label_el.get_text(" ")) if date_label_el else ""
        if date_label.casefold() in {"dzisiaj", "dziś", "today"}:
            return idx

    for idx, nav in enumerate(nav_items):
        date_label_el = nav.select_one(".scheduleDate")
        date_label = clean_text(date_label_el.get_text(" ")) if date_label_el else ""
        ddmm = _parse_ddmm(date_label)
        if ddmm and ddmm == (today.day, today.month):
            return idx

    return len(nav_items) // 2


def _parse_ddmm(text: str) -> tuple[int, int] | None:
    t = clean_text(text)
    if not t:
        return None
    m = re.search(r"(\d{1,2})\.(\d{1,2})", t)
    if not m:
        return None
    day = int(m.group(1))
    month = int(m.group(2))
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    return (day, month)


def _closest_date_with_day_month(anchor: date, ddmm: tuple[int, int]) -> date:
    day, month = ddmm
    candidates: list[date] = []
    for year in (anchor.year - 1, anchor.year, anchor.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        return anchor
    return min(candidates, key=lambda d: abs((d - anchor).days))


def _normalize_author_text(text: str) -> str:
    t = clean_text(text)
    if not t:
        return ""
    t = re.sub(r"\s*,\s*", ", ", t)
    t = re.sub(r",\s*$", "", t)
    t = clean_text(t)
    lowered = t.casefold()
    if lowered in {"s", ".", "-", "—", "–"}:
        return ""
    if len(t) <= 2:
        return ""
    return t

