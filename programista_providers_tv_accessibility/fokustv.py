from __future__ import annotations

import json
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import AccessibilityFeature, ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text


FOKUSTV_MODULE_URL = "https://www.fokus.tv/tv-html/module/page{page}/"
FOKUSTV_MORE_URL = "https://www.fokus.tv/tv-more/module/page{page}/"
FOKUSTV_CHANNEL_NAME = "Fokus TV"


class FokusTvAccessibilityProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._day_cache: dict[str, _FokusTvDayCache] = {}

    @property
    def provider_id(self) -> str:
        return "fokustv"

    @property
    def display_name(self) -> str:
        return "Telewizja (Fokus TV)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("fokustv"),
                name="Fokus TV",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
        today = date.today()
        return [today + timedelta(days=i) for i in range(7)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        if str(source.id) != "fokustv":
            return []

        day_key = day.isoformat()

        if not force_refresh:
            with self._lock:
                cached = self._day_cache.get(day_key)
                if cached and cached.expires_at > time_module.time():
                    return cached.items

        built = self._build_day_cache(day, force_refresh=force_refresh)
        with self._lock:
            self._day_cache[day_key] = built
        return built.items

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title

    def _build_day_cache(self, day: date, *, force_refresh: bool) -> "_FokusTvDayCache":
        offset = (day - date.today()).days
        if offset < 0 or offset > 6:
            return _FokusTvDayCache(expires_at=time_module.time() + 6 * 3600, items=[])

        pages: list[int] = [offset + 1]
        if offset > 0:
            pages.append(offset)

        source = Source(provider_id=ProviderId(self.provider_id), id=SourceId("fokustv"), name="Fokus TV")

        merged: list[ScheduleItem] = []
        for page in pages:
            html = self._fetch_module(page, force_refresh=force_refresh)
            more = parse_fokustv_more_json(self._fetch_more(page, force_refresh=force_refresh))
            merged.extend(parse_fokustv_day_from_module(html, day=day, source=source, more=more))

        merged.sort(key=lambda it: ((it.start_time or time.min), it.title.casefold()))
        deduped: list[ScheduleItem] = []
        seen: set[tuple[str, str]] = set()
        for it in merged:
            key = ((it.start_time.strftime("%H:%M") if it.start_time else ""), it.title.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(it)

        return _FokusTvDayCache(expires_at=time_module.time() + 6 * 3600, items=deduped)

    def _fetch_module(self, page: int, *, force_refresh: bool) -> str:
        url = FOKUSTV_MODULE_URL.format(page=page)
        return self._http.get_text(
            url,
            cache_key=f"fokustv:module:{page}",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )

    def _fetch_more(self, page: int, *, force_refresh: bool) -> str:
        url = FOKUSTV_MORE_URL.format(page=page)
        return self._http.get_text(
            url,
            cache_key=f"fokustv:more:{page}",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )


@dataclass(frozen=True)
class _FokusTvItem:
    start_time: time
    end_time: time | None
    title: str
    description: str | None
    accessibility: list[AccessibilityFeature]
    start_ms: int


@dataclass(frozen=True)
class _FokusTvMoreEntry:
    description: str | None
    accessibility: list[AccessibilityFeature]


def parse_fokustv_more_json(text: str) -> dict[str, _FokusTvMoreEntry]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}

    out: dict[str, _FokusTvMoreEntry] = {}
    for pid_raw, value in raw.items():
        pid = clean_text(str(pid_raw))
        if not pid:
            continue
        if not isinstance(value, list):
            continue

        description_raw = value[2] if len(value) >= 3 else None
        description = _clean_fokustv_description(description_raw) if isinstance(description_raw, str) else None
        accessibility = _parse_accessibility_tokens(value[-1] if value else None)
        out[pid] = _FokusTvMoreEntry(description=description, accessibility=accessibility)

    return out


def _clean_fokustv_description(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    soup = BeautifulSoup(value, "lxml")
    text = clean_multiline_text(soup.get_text("\n"))
    return text or None


def _parse_accessibility_tokens(value: Any) -> list[AccessibilityFeature]:
    if not isinstance(value, list):
        return []
    out: list[AccessibilityFeature] = []
    for token in value:
        if token == "AD":
            out.append("AD")
        elif token == "JM":
            out.append("JM")
        elif token == "N":
            out.append("N")
    return _uniq(out)


def parse_fokustv_day_from_module(
    html: str,
    *,
    day: date,
    source: Source,
    more: dict[str, _FokusTvMoreEntry] | None = None,
) -> list[ScheduleItem]:
    soup = BeautifulSoup(html, "lxml")
    row = soup.find("div", {"class": "tv__row", "data-channel": FOKUSTV_CHANNEL_NAME})
    if not row:
        return []

    items = _parse_tv_html_row_items(row, more=more)
    if not items:
        return []

    out: list[ScheduleItem] = []
    for it in items:
        try:
            start_dt = datetime.fromtimestamp(it.start_ms / 1000)
        except Exception:  # noqa: BLE001
            continue
        if start_dt.date() != day:
            continue

        out.append(
            ScheduleItem(
                provider_id=ProviderId("fokustv"),
                source=source,
                day=day,
                start_time=it.start_time,
                end_time=it.end_time,
                title=it.title,
                subtitle=None,
                details_ref=None,
                details_summary=it.description,
                accessibility=tuple(it.accessibility),
            )
        )
    return out


def _parse_tv_html_row_items(row: BeautifulSoup, *, more: dict[str, _FokusTvMoreEntry] | None) -> list[_FokusTvItem]:
    items: list[_FokusTvItem] = []
    for cast in row.select("div.tvcast[data-start][data-end]"):
        start_ms_s = cast.get("data-start") or ""
        end_ms_s = cast.get("data-end") or ""
        if not start_ms_s.isdigit() or not end_ms_s.isdigit():
            continue
        start_ms = int(start_ms_s)
        end_ms = int(end_ms_s)
        title_el = cast.select_one(".tvcast__title")
        title = clean_text(title_el.get_text(" ")) if title_el else ""
        if not title:
            continue

        accessibility: list[AccessibilityFeature] = []
        for icon in cast.select(".tvcast__accesibility-icon"):
            text = clean_text(icon.get_text(" ")).upper()
            title_attr = clean_text(icon.get("title") or "").casefold()
            if text == "AD" or "audiodeskrypcja" in title_attr:
                accessibility.append("AD")
            elif text == "JM" or "język migowy" in title_attr or "jezyk migowy" in title_attr:
                accessibility.append("JM")
            elif text == "N" or "napisy" in title_attr:
                accessibility.append("N")

        description = None
        if more and title_el:
            pid = clean_text(title_el.get("data-id") or "")
            entry = more.get(pid) if pid else None
            if entry:
                description = entry.description
                accessibility.extend(entry.accessibility)

        start_time = datetime.fromtimestamp(start_ms / 1000).time().replace(microsecond=0)
        end_time = datetime.fromtimestamp(end_ms / 1000).time().replace(microsecond=0)

        items.append(
            _FokusTvItem(
                start_time=start_time,
                end_time=end_time,
                title=title,
                description=description,
                accessibility=_uniq(accessibility),
                start_ms=start_ms,
            )
        )

    items.sort(key=lambda it: it.start_ms)
    seen: set[tuple[int, str]] = set()
    out: list[_FokusTvItem] = []
    for it in items:
        key = (it.start_ms, it.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _uniq(features: list[AccessibilityFeature]) -> list[AccessibilityFeature]:
    seen: set[AccessibilityFeature] = set()
    out: list[AccessibilityFeature] = []
    for f in features:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


@dataclass(frozen=True)
class _FokusTvDayCache:
    expires_at: float
    items: list[ScheduleItem]
