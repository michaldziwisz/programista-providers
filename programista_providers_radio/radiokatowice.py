from __future__ import annotations

import re
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


RK_BASE = "https://www.radio.katowice.pl"
RK_RAMOWKA_URL = f"{RK_BASE}/ramowka.html"

_RK_TIME_RE = re.compile(r"^\s*(\d{1,2}[:.]\d{2})\b")
_RK_DETAILS_REF_ALLOWED_PREFIXES = ("audycje,",)

_RK_WEEKDAY_TO_ISO: dict[str, int] = {
    "poniedziałek": 1,
    "poniedzialek": 1,
    "wtorek": 2,
    "środa": 3,
    "sroda": 3,
    "czwartek": 4,
    "piątek": 5,
    "piatek": 5,
    "sobota": 6,
    "niedziela": 7,
}


@dataclass(frozen=True)
class _RkProgramme:
    start: time | None
    title: str
    details_ref: str | None
    details: str


@dataclass(frozen=True)
class _RkParsedSchedule:
    by_iso_weekday: dict[int, list[_RkProgramme]]


@dataclass(frozen=True)
class _RkScheduleCache:
    expires_at: float
    parsed: _RkParsedSchedule


class RadioKatowiceProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._cache: _RkScheduleCache | None = None

    @property
    def provider_id(self) -> str:
        return "radiokatowice"

    @property
    def display_name(self) -> str:
        return "Radio Katowice"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("radiokatowice"),
                name="Radio Katowice",
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
        if str(source.id) != "radiokatowice":
            return []

        weekday = day.isoweekday()  # Monday=1..Sunday=7
        parsed = self._get_parsed_schedule(force_refresh=force_refresh)
        programmes = parsed.by_iso_weekday.get(weekday, [])

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

        ref = str(item.details_ref)
        if not _is_allowed_details_ref(ref):
            return item.details_summary or item.title

        url = urljoin(RK_BASE, ref)
        try:
            html = self._http.get_text(
                url,
                cache_key=f"rk:details:{ref}",
                ttl_seconds=30 * 24 * 3600,
                force_refresh=force_refresh,
                timeout_seconds=20.0,
            )
        except Exception:  # noqa: BLE001
            return item.details_summary or item.title

        details = parse_rk_audycja_details_html(html)
        if item.details_summary and details:
            return item.details_summary + "\n\n" + details
        return details or item.details_summary or item.title

    def _get_parsed_schedule(self, *, force_refresh: bool) -> _RkParsedSchedule:
        if not force_refresh:
            with self._lock:
                cached = self._cache
                if cached and cached.expires_at > time_module.time():
                    return cached.parsed

        html = self._http.get_text(
            RK_RAMOWKA_URL,
            cache_key="rk:ramowka:v1",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        parsed = parse_rk_ramowka_html(html)

        with self._lock:
            self._cache = _RkScheduleCache(expires_at=time_module.time() + 6 * 3600, parsed=parsed)
        return parsed


def _is_allowed_details_ref(ref: str) -> bool:
    t = clean_text(ref)
    if not t:
        return False
    if t.startswith(("http://", "https://")):
        if "radio.katowice.pl" not in t:
            return False
        t = t.split("radio.katowice.pl", 1)[1]
    t = t.lstrip("/")
    return t.startswith(_RK_DETAILS_REF_ALLOWED_PREFIXES)


def _parse_time(token: str) -> time | None:
    t = clean_text(token)
    if not t:
        return None
    t = t.replace(".", ":")
    if len(t) == 4 and t[1] == ":":  # e.g. 7:00
        t = "0" + t
    if t.startswith("24:"):
        return None
    try:
        return parse_time_hhmm(t[:5])
    except Exception:  # noqa: BLE001
        return None


def parse_rk_ramowka_html(html: str) -> _RkParsedSchedule:
    soup = BeautifulSoup(html, "lxml")

    by_iso_weekday: dict[int, list[_RkProgramme]] = {i: [] for i in range(1, 8)}
    for tab in soup.select('div[id^="ex1-tabs-"]'):
        h2 = tab.select_one("h2")
        if not h2:
            continue
        weekday_name = clean_text(h2.get_text(" ")).casefold()
        weekday = _RK_WEEKDAY_TO_ISO.get(weekday_name)
        if not weekday:
            continue

        items: list[_RkProgramme] = []
        for p in tab.select("p.m-0"):
            programme = _parse_programme_p(p)
            if programme:
                items.append(programme)

        seen: set[tuple[str, str]] = set()
        deduped: list[_RkProgramme] = []
        for it in items:
            key = (it.start.strftime("%H:%M") if it.start else "", it.title.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(it)

        by_iso_weekday[weekday] = deduped

    return _RkParsedSchedule(by_iso_weekday=by_iso_weekday)


def _parse_programme_p(p) -> _RkProgramme | None:
    text = clean_text(p.get_text(" "))
    if not text:
        return None

    m = _RK_TIME_RE.match(text)
    if not m:
        return None

    start = _parse_time(m.group(1))
    if not start:
        return None

    rest = text[m.end() :].strip()
    if not rest:
        return None

    title = rest
    details = ""

    a = p.select_one("a[href]")
    href = clean_text(a.get("href") or "") if a else ""
    details_ref = href if href and _is_allowed_details_ref(href) else None

    if a:
        a_text = clean_text(a.get_text(" "))
        if a_text:
            title = a_text
            rest_after_title = rest
            if rest_after_title.casefold().startswith(a_text.casefold()):
                rest_after_title = rest_after_title[len(a_text) :].strip()
            rest_after_title = re.sub(r"^[\s\-–—:]+", "", rest_after_title).strip()
            details = rest_after_title

    title = clean_text(title)
    details = clean_text(details)
    if not title:
        return None

    return _RkProgramme(start=start, title=title, details_ref=details_ref, details=details)


def parse_rk_audycja_details_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("div.tytul_art")
    candidates = title_el.find_all_next("p") if title_el else soup.select("p")
    for p in candidates:
        if p.find("iframe"):
            continue
        text = clean_multiline_text(p.get_text("\n"))
        text = clean_text(text)
        if not text:
            continue
        if text in {"\u00a0", "&nbsp;"}:
            continue
        return text

    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return clean_text(meta.get("content"))
    return ""
