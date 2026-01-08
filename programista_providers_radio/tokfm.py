from __future__ import annotations

import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_text, parse_time_hhmm


TOKFM_SCHEDULE_URL = "https://audycje.tokfm.pl/ramowka"


@dataclass(frozen=True)
class _TokProgramme:
    start: time | None
    title: str
    details: str
    details_ref: str | None


@dataclass(frozen=True)
class _TokWeekCache:
    expires_at: float
    by_weekday: dict[int, list[_TokProgramme]]


class TokFmProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._week_cache: _TokWeekCache | None = None

    @property
    def provider_id(self) -> str:
        return "tokfm"

    @property
    def display_name(self) -> str:
        return "TOK FM"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("tokfm"),
                name="TOK FM",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
        today = date.today()
        # The schedule is presented as a weekly grid (Mon..Sun), not tied to specific dates.
        # Expose only the upcoming week to avoid repeating the same pattern.
        return [today + timedelta(days=i) for i in range(7)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        if str(source.id) != "tokfm":
            return []

        weekday = day.isoweekday()  # Monday=1..Sunday=7
        programmes = self._get_week_map(force_refresh=force_refresh).get(weekday) or []
        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=p.start,
                end_time=None,
                title=p.title,
                subtitle=None,
                details_ref=p.details_ref,
                details_summary=p.details or None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:
        fallback = item.details_summary or item.title
        if not item.details_ref:
            return fallback

        try:
            html = self._http.get_text(
                str(item.details_ref),
                cache_key=f"tokfm:details:{item.details_ref}",
                ttl_seconds=24 * 3600,
                force_refresh=force_refresh,
                timeout_seconds=20.0,
            )
        except Exception:  # noqa: BLE001
            return fallback

        details = parse_tokfm_details_html(html)
        return details or fallback

    def _get_week_map(self, *, force_refresh: bool) -> dict[int, list[_TokProgramme]]:
        if not force_refresh:
            with self._lock:
                if self._week_cache and self._week_cache.expires_at > time_module.time():
                    return self._week_cache.by_weekday

        html = self._http.get_text(
            TOKFM_SCHEDULE_URL,
            cache_key="tokfm:ramowka",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        by_weekday = parse_tokfm_ramowka_html(html)
        with self._lock:
            self._week_cache = _TokWeekCache(expires_at=time_module.time() + 6 * 3600, by_weekday=by_weekday)
        return by_weekday


def parse_tokfm_ramowka_html(html: str) -> dict[int, list[_TokProgramme]]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[int, list[_TokProgramme]] = {}

    for weekday in range(1, 8):
        ul = soup.select_one(f"ul.tok-schedule__el_{weekday}")
        if not ul:
            continue

        programmes: list[_TokProgramme] = []
        for entry in ul.select("li.tok-schedule__entry"):
            time_el = entry.select_one(".tok-schedule__time")
            start = parse_time_hhmm(clean_text(time_el.get_text(" "))) if time_el else None

            h3s = entry.select("h3.tok-schedule__program--name")
            show_title = clean_text(h3s[0].get_text(" ")) if len(h3s) >= 1 else ""
            episode_title = clean_text(h3s[1].get_text(" ")) if len(h3s) >= 2 else ""

            show_href = ""
            if len(h3s) >= 1:
                a = h3s[0].select_one("a[href]")
                show_href = clean_text(a.get("href") or "") if a else ""

            episode_href = ""
            if len(h3s) >= 2:
                a = h3s[1].select_one("a[href]")
                episode_href = clean_text(a.get("href") or "") if a else ""

            title = show_title
            if episode_title and episode_title.casefold() != show_title.casefold():
                title = f"{show_title} — {episode_title}" if show_title else episode_title
            title = clean_text(title)
            if not title:
                continue

            leaders: list[str] = []
            for a in entry.select(".tok-schedule__program--leader-name a"):
                name = clean_text(a.get_text(" "))
                if name:
                    leaders.append(name)
            details = ", ".join(_uniq_strings(leaders))

            details_ref = episode_href or show_href
            details_ref = details_ref or None

            programmes.append(_TokProgramme(start=start, title=title, details=details, details_ref=details_ref))

        # Remove exact duplicates (sometimes present due to layout repetition).
        seen: set[tuple[str, str]] = set()
        deduped: list[_TokProgramme] = []
        for p in programmes:
            key = (p.start.strftime("%H:%M") if p.start else "", p.title.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)

        out[weekday] = deduped

    return out


def parse_tokfm_details_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    meta = soup.select_one('meta[name="description"]')
    if meta and meta.get("content"):
        return clean_text(str(meta.get("content")))
    og = soup.select_one('meta[property="og:description"]')
    if og and og.get("content"):
        return clean_text(str(og.get("content")))
    return ""


def _uniq_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = v.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out
