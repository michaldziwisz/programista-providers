from __future__ import annotations

import json
import re
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text


PR_CHANNELS: list[str] = ["Jedynka", "Dwójka", "Trójka", "Czwórka", "Radio Poland", "PR24"]

PR_SCHEDULE_API_URL = "https://apipr.polskieradio.pl/api/schedule"

# Internal schedule JSON used by the new PR websites (contains `categoryId`).
PR_INTERNAL_SCHEDULE_API_URL = "https://jedynka.polskieradio.pl/api/schedule"

PR_AUDYCJE_DETAILS_URL_TEMPLATE = "https://jedynka.polskieradio.pl/audycje/{category_id}"

# Mapping based on the official `apipr.polskieradio.pl` schedule endpoint.
PR_PROGRAM_ID_BY_CHANNEL: dict[str, str] = {
    "Jedynka": "1",
    "Dwójka": "2",
    "Trójka": "3",
    "Czwórka": "4",
    "Radio Poland": "5",
    "PR24": "6",
}


class PolskieRadioProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._internal_cache_by_day: dict[str, _PrInternalDayCache] = {}

    @property
    def provider_id(self) -> str:
        return "polskieradio"

    @property
    def display_name(self) -> str:
        return "Radio (Polskie Radio)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:
        return [
            Source(provider_id=ProviderId(self.provider_id), id=SourceId(name), name=name)
            for name in PR_CHANNELS
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
        today = date.today()
        start = today - timedelta(days=7)
        return [start + timedelta(days=i) for i in range(14)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        programme_id = PR_PROGRAM_ID_BY_CHANNEL.get(source.name)
        if not programme_id:
            return []

        schedule_json = self._http.get_text(
            _build_pr_schedule_url(programme_id, day),
            cache_key=f"pr:schedule:v2:{programme_id}:{day.isoformat()}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        items = parse_pr_schedule_json(schedule_json)
        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=item.start_time,
                end_time=item.end_time,
                title=item.title,
                subtitle=None,
                details_ref=item.details_ref,
                details_summary=item.details_summary or None,
            )
            for item in items
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:
        fallback = item.details_summary or item.title

        category_id = extract_pr_category_id_from_article_link(item.details_ref or "")
        if category_id is None:
            category_id = self._find_category_id_in_internal_schedule(item, force_refresh=force_refresh)
        if category_id is None:
            return fallback

        url = PR_AUDYCJE_DETAILS_URL_TEMPLATE.format(category_id=category_id)
        try:
            html = self._http.get_text(
                url,
                cache_key=f"pr:audycje:{category_id}",
                ttl_seconds=30 * 24 * 3600,
                force_refresh=force_refresh,
                timeout_seconds=20.0,
            )
        except Exception:  # noqa: BLE001
            return fallback

        details = parse_pr_audycje_details_html(html)
        header = item.title
        if item.start_time:
            header = f"{item.start_time.strftime('%H:%M')} {item.title}"

        parts: list[str] = [clean_text(header)]
        if details.hosts:
            parts.append(f"Prowadzący: {', '.join(details.hosts)}")
        if details.lead:
            parts.append(details.lead)
        if details.description:
            parts.append(details.description)

        out = "\n\n".join([p for p in parts if p])
        return out or fallback

    def _find_category_id_in_internal_schedule(
        self,
        item: ScheduleItem,
        *,
        force_refresh: bool,
    ) -> int | None:
        if not item.start_time:
            return None

        start_s = item.start_time.strftime("%H:%M")
        title_key = clean_text(item.title).casefold()
        station_key = clean_text(item.source.name).casefold()

        by_station = self._get_internal_day_schedule(item.day, force_refresh=force_refresh)
        entries = by_station.get(station_key) or []

        for entry in entries:
            if entry.start_time == start_s and entry.title_key == title_key:
                return entry.category_id

        # Sometimes titles differ slightly; if there is exactly one show at that time
        # with a category id, accept it as a fallback.
        candidates = [e.category_id for e in entries if e.start_time == start_s and e.category_id]
        if len(candidates) == 1:
            return candidates[0]

        return None

    def _get_internal_day_schedule(self, day: date, *, force_refresh: bool) -> dict[str, list["_PrInternalEntry"]]:
        day_key = day.isoformat()
        if not force_refresh:
            with self._lock:
                cached = self._internal_cache_by_day.get(day_key)
                if cached and cached.expires_at > time_module.time():
                    return cached.by_station

        url = f"{PR_INTERNAL_SCHEDULE_API_URL}?date={day.isoformat()}"
        json_text = self._http.get_text(
            url,
            cache_key=f"pr:internal_schedule:{day_key}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        parsed = parse_pr_internal_schedule_json(json_text)

        with self._lock:
            self._internal_cache_by_day[day_key] = _PrInternalDayCache(
                expires_at=time_module.time() + 60 * 30,
                by_station=parsed,
            )
        return parsed


@dataclass(frozen=True)
class _PrItem:
    start_time: time | None
    end_time: time | None
    title: str
    details_ref: str | None
    details_summary: str


@dataclass(frozen=True)
class _PrInternalEntry:
    start_time: str
    title_key: str
    category_id: int | None


@dataclass(frozen=True)
class _PrInternalDayCache:
    expires_at: float
    by_station: dict[str, list[_PrInternalEntry]]


@dataclass(frozen=True)
class _PrAudycjeDetails:
    lead: str
    description: str
    hosts: list[str]


def _build_pr_schedule_url(programme_id: str, day: date) -> str:
    return f"{PR_SCHEDULE_API_URL}?Program={programme_id}&selectedDate={day.isoformat()}"


_PR_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_PR_TRIVIAL_TEXT_RE = re.compile(r"^[\s\W_]+$", flags=re.UNICODE)


def _clean_pr_rich_text(value: object) -> str:
    if value is None:
        return ""

    text = str(value)
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")

    if _PR_HTML_TAG_RE.search(text):
        try:
            soup = BeautifulSoup(text, "lxml")
            for el in soup(["script", "style"]):
                el.decompose()
            for br in soup.find_all("br"):
                br.replace_with("\n")
            for block in soup.find_all(["p", "li"]):
                block.append("\n")
            text = soup.get_text(" ")
        except Exception:  # noqa: BLE001
            text = re.sub(r"<[^>]+>", " ", text)

    cleaned = clean_multiline_text(text)
    if not cleaned:
        return ""

    lines = cleaned.split("\n")
    while lines and (not lines[0] or _PR_TRIVIAL_TEXT_RE.fullmatch(lines[0])):
        lines.pop(0)
    while lines and (not lines[-1] or _PR_TRIVIAL_TEXT_RE.fullmatch(lines[-1])):
        lines.pop()

    cleaned = clean_multiline_text("\n".join(lines))
    if not cleaned or _PR_TRIVIAL_TEXT_RE.fullmatch(cleaned):
        return ""

    return cleaned


def parse_pr_schedule_json(text: str) -> list[_PrItem]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    schedule = data.get("Schedule")
    if not isinstance(schedule, list):
        return []

    parsed: list[tuple[datetime | None, _PrItem]] = []
    for raw in schedule:
        if not isinstance(raw, dict):
            continue

        title = clean_text(raw.get("Title") or "")
        if not title:
            continue

        start_dt = _parse_iso_datetime(raw.get("StartHour"))
        end_dt = _parse_iso_datetime(raw.get("StopHour"))

        start = start_dt.timetz().replace(tzinfo=None) if start_dt else None
        end = end_dt.timetz().replace(tzinfo=None) if end_dt else None

        leaders = _format_leaders(raw.get("Leaders"))
        description = _clean_pr_rich_text(raw.get("Description"))
        details_parts = [p for p in (leaders, description) if p]
        details = "\n\n".join(details_parts)

        details_ref = _normalize_url(raw.get("ArticleLink"))

        parsed.append((start_dt, _PrItem(start_time=start, end_time=end, title=title, details_ref=details_ref, details_summary=details)))

    parsed.sort(key=lambda x: x[0] or datetime.min)

    seen: set[tuple[str, str]] = set()
    out: list[_PrItem] = []
    for _, item in parsed:
        key = (item.start_time.strftime("%H:%M") if item.start_time else "", item.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def _parse_iso_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_leaders(value: object) -> str:
    if not isinstance(value, list):
        return ""
    names: list[str] = []
    for leader in value:
        if not isinstance(leader, dict):
            continue
        first = clean_text(leader.get("Name") or "")
        last = clean_text(leader.get("SurName") or "")
        full = clean_text(" ".join([p for p in (first, last) if p]))
        if full:
            names.append(full)
    if not names:
        return ""
    # Keep the original order while removing duplicates case-insensitively.
    seen: set[str] = set()
    uniq: list[str] = []
    for name in names:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(name)
    return f"Prowadzący: {', '.join(uniq)}"


def _normalize_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    url = clean_text(value)
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    return url


_PR_ARTICLE_CATEGORY_ID_RE = re.compile(r"/\d+/(\d+)/Artykul/", flags=re.IGNORECASE)


def extract_pr_category_id_from_article_link(url: str) -> int | None:
    u = clean_text(url)
    if not u:
        return None

    m = _PR_ARTICLE_CATEGORY_ID_RE.search(u)
    if not m:
        return None

    try:
        return int(m.group(1))
    except ValueError:
        return None


def parse_pr_internal_schedule_json(text: str) -> dict[str, list[_PrInternalEntry]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}

    by_station: dict[str, list[_PrInternalEntry]] = {}
    for raw_station in data:
        if not isinstance(raw_station, dict):
            continue

        station = clean_text(raw_station.get("station") or "")
        if not station:
            continue
        station_key = station.casefold()

        schedules = raw_station.get("schedules")
        if not isinstance(schedules, list):
            continue

        entries: list[_PrInternalEntry] = []
        for raw in schedules:
            if not isinstance(raw, dict):
                continue

            start_s = clean_text(raw.get("startTime") or "")
            title = clean_text(raw.get("title") or "")
            if not start_s or not title:
                continue

            raw_category_id = raw.get("categoryId")
            category_id = raw_category_id if isinstance(raw_category_id, int) else None

            entries.append(_PrInternalEntry(start_time=start_s, title_key=title.casefold(), category_id=category_id))

        by_station[station_key] = entries

    return by_station


def parse_pr_audycje_details_html(html: str) -> _PrAudycjeDetails:
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return _PrAudycjeDetails(lead="", description="", hosts=[])

    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return _PrAudycjeDetails(lead="", description="", hosts=[])

    pp = data.get("props", {}).get("pageProps", {})
    if not isinstance(pp, dict):
        return _PrAudycjeDetails(lead="", description="", hosts=[])

    details = pp.get("details", {})
    if not isinstance(details, dict):
        details = {}

    lead = _clean_pr_rich_text(details.get("lead"))
    description = _clean_pr_rich_text(details.get("description"))

    hosts_raw = pp.get("hosts")
    hosts: list[str] = []
    if isinstance(hosts_raw, list):
        for host in hosts_raw:
            if not isinstance(host, dict):
                continue
            first = clean_text(host.get("name") or host.get("firstName") or "")
            last = clean_text(host.get("surname") or host.get("lastName") or "")
            full = clean_text(host.get("fullName") or "") if host.get("fullName") else ""
            if not full:
                full = clean_text(" ".join([p for p in (first, last) if p]))
            if full:
                hosts.append(full)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    uniq_hosts: list[str] = []
    for name in hosts:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        uniq_hosts.append(name)

    return _PrAudycjeDetails(lead=lead, description=description, hosts=uniq_hosts)
