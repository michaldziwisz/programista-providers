from __future__ import annotations

import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


RMFCLASSIC_BASE = "https://www.rmfclassic.pl"
RMFCLASSIC_RAMOWKA_BY_ISO_WEEKDAY: dict[int, str] = {
    1: "/radio/ramowka/dzien/poniedzialek",
    2: "/radio/ramowka/dzien/wtorek",
    3: "/radio/ramowka/dzien/sroda",
    4: "/radio/ramowka/dzien/czwartek",
    5: "/radio/ramowka/dzien/piatek",
    6: "/radio/ramowka/dzien/sobota",
    7: "/radio/ramowka/dzien/niedziela",
}


@dataclass(frozen=True)
class _RmfClassicProgramme:
    start: time | None
    title: str
    details_ref: str | None
    details: str


@dataclass(frozen=True)
class _RmfClassicDayCache:
    expires_at: float
    programmes: list[_RmfClassicProgramme]


class RmfClassicProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._cache_by_weekday: dict[int, _RmfClassicDayCache] = {}

    @property
    def provider_id(self) -> str:
        return "rmfclassic"

    @property
    def display_name(self) -> str:
        return "RMF Classic"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("rmfclassic"),
                name="RMF Classic",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
        today = date.today()
        return [today + timedelta(days=i) for i in range(14)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        if str(source.id) != "rmfclassic":
            return []

        weekday = day.isoweekday()  # Monday=1..Sunday=7
        programmes = self._get_day_programmes(weekday, force_refresh=force_refresh)
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
        if not item.details_ref:
            return item.details_summary or item.title

        url = urljoin(RMFCLASSIC_BASE, str(item.details_ref))
        try:
            html = self._http.get_text(
                url,
                cache_key=f"rmfclassic:details:{item.details_ref}",
                ttl_seconds=30 * 24 * 3600,
                force_refresh=force_refresh,
                timeout_seconds=20.0,
            )
        except Exception:  # noqa: BLE001
            return item.details_summary or item.title

        details = parse_rmfclassic_programme_details_html(html)
        if item.details_summary and details:
            return item.details_summary + "\n\n" + details
        return details or item.details_summary or item.title

    def _get_day_programmes(self, weekday: int, *, force_refresh: bool) -> list[_RmfClassicProgramme]:
        if not force_refresh:
            with self._lock:
                cached = self._cache_by_weekday.get(weekday)
                if cached and cached.expires_at > time_module.time():
                    return cached.programmes

        path = RMFCLASSIC_RAMOWKA_BY_ISO_WEEKDAY.get(weekday)
        if not path:
            return []

        url = urljoin(RMFCLASSIC_BASE, path)
        html = self._http.get_text(
            url,
            cache_key=f"rmfclassic:ramowka:{weekday}",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )

        programmes = parse_rmfclassic_ramowka_html(html)
        with self._lock:
            self._cache_by_weekday[weekday] = _RmfClassicDayCache(
                expires_at=time_module.time() + 6 * 3600,
                programmes=programmes,
            )
        return programmes


def _parse_time(text: str) -> time | None:
    t = clean_text(text)
    if not t:
        return None
    if len(t) == 4 and t[1] == ":":  # e.g. 7:00
        t = "0" + t
    try:
        return parse_time_hhmm(t[:5])
    except Exception:  # noqa: BLE001
        return None


def parse_rmfclassic_ramowka_html(html: str) -> list[_RmfClassicProgramme]:
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("div.row.py-2")

    out: list[_RmfClassicProgramme] = []
    for row in rows:
        time_badge = row.select_one(".col-2 .s-badge")
        start = _parse_time(time_badge.get_text(" ")) if time_badge else None
        if not start:
            continue

        title_a = row.select_one(".col b a[href]") or row.select_one("b a[href]")
        title = clean_text(title_a.get_text(" ")) if title_a else ""
        details_ref = clean_text(title_a.get("href") or "") if title_a else ""
        details_ref = details_ref or None
        if not title:
            continue

        host_names = _extract_hosts(row)
        details = f"Zaprasza: {host_names}" if host_names else ""
        out.append(_RmfClassicProgramme(start=start, title=title, details_ref=details_ref, details=details))

        for li in row.select(".subitems li"):
            sub_time_badge = li.select_one(".s-badge")
            sub_start = _parse_time(sub_time_badge.get_text(" ")) if sub_time_badge else None
            if not sub_start:
                continue
            sub_a = li.select_one("b a[href]") or li.select_one("a[href]")
            sub_title = clean_text(sub_a.get_text(" ")) if sub_a else ""
            sub_ref = clean_text(sub_a.get("href") or "") if sub_a else ""
            sub_ref = sub_ref or None
            if not sub_title:
                continue

            parts: list[str] = []
            if title:
                parts.append(f"W ramach: {title}")
            if host_names:
                parts.append(f"Zaprasza: {host_names}")
            sub_details = "\n\n".join(parts)
            out.append(_RmfClassicProgramme(start=sub_start, title=sub_title, details_ref=sub_ref, details=sub_details))

    seen: set[tuple[str, str]] = set()
    deduped: list[_RmfClassicProgramme] = []
    for it in sorted(out, key=lambda p: p.start or time.min):
        key = (it.start.strftime("%H:%M") if it.start else "", it.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped


def _extract_hosts(row) -> str:
    names = [
        clean_text(a.get_text(" "))
        for a in row.select('a[href^="/radio/ludzie/"]')
        if clean_text(a.get_text(" "))
    ]
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        key = n.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return ", ".join(out)


def parse_rmfclassic_programme_details_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    lead = soup.select_one("p.content-lead")
    container = lead.find_parent("div", class_="content") if lead else None
    if not container:
        container = soup.select_one("div.content") or soup

    parts: list[str] = []
    for p in container.select("p"):
        t = clean_multiline_text(p.get_text("\n"))
        if not t:
            continue
        parts.append(t)

    if parts:
        return "\n\n".join(parts)

    meta = soup.select_one('meta[name="description"]')
    if meta and meta.get("content"):
        return clean_text(str(meta.get("content")))
    return ""
