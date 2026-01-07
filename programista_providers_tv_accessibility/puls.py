from __future__ import annotations

import re
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import AccessibilityFeature, ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text


PULS_EPG_BASE_URL = "https://tyflo.eu.org/epg/puls/"


class PulsAccessibilityProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._files_cache: _PulsFilesCache | None = None
        self._schedule_cache: dict[str, _PulsScheduleCache] = {}

    @property
    def provider_id(self) -> str:
        return "puls"

    @property
    def display_name(self) -> str:
        return "Telewizja (TV Puls)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:
        files = self._resolve_files(force_refresh=force_refresh)
        out: list[Source] = []
        if files.tvpuls_url:
            out.append(Source(provider_id=ProviderId(self.provider_id), id=SourceId("tvpuls"), name="TV Puls"))
        if files.puls2_url:
            out.append(Source(provider_id=ProviderId(self.provider_id), id=SourceId("puls2"), name="Puls 2"))
        return out

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
        files = self._resolve_files(force_refresh=force_refresh)
        days: set[date] = set()
        for url in [files.tvpuls_url, files.puls2_url]:
            if not url:
                continue
            schedules = self._get_schedule_map(url, force_refresh=force_refresh)
            days.update(schedules.keys())
        return sorted(days)

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        files = self._resolve_files(force_refresh=force_refresh)
        url = files.tvpuls_url if str(source.id) == "tvpuls" else files.puls2_url
        if not url:
            return []

        items = self._get_schedule_map(url, force_refresh=force_refresh).get(day) or []

        out: list[ScheduleItem] = []
        for it in items:
            out.append(
                ScheduleItem(
                    provider_id=ProviderId(self.provider_id),
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

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title

    def _resolve_files(self, *, force_refresh: bool) -> "_PulsEpgFiles":
        if not force_refresh:
            with self._lock:
                if self._files_cache and self._files_cache.expires_at > time_module.time():
                    return self._files_cache.files

        html = self._http.get_text(
            PULS_EPG_BASE_URL,
            cache_key="puls:epg:index",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        files = parse_puls_epg_index(html, base_url=PULS_EPG_BASE_URL)
        with self._lock:
            self._files_cache = _PulsFilesCache(expires_at=time_module.time() + 60 * 30, files=files)
        return files

    def _get_schedule_map(self, url: str, *, force_refresh: bool) -> dict[date, list["_PulsItem"]]:
        if not force_refresh:
            with self._lock:
                cached = self._schedule_cache.get(url)
                if cached and cached.expires_at > time_module.time():
                    return cached.by_day

        xml = self._http.get_text(
            url,
            cache_key=f"puls:epg:{url}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=30.0,
        )
        by_day = parse_puls_epg_xml_all_days(xml)
        with self._lock:
            self._schedule_cache[url] = _PulsScheduleCache(expires_at=time_module.time() + 60 * 30, by_day=by_day)
        return by_day


@dataclass(frozen=True)
class _PulsEpgFiles:
    tvpuls_url: str | None
    puls2_url: str | None


def parse_puls_epg_index(html: str, *, base_url: str) -> _PulsEpgFiles:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        href = href.strip()
        if not href or href.endswith("/"):
            continue
        if not (href.lower().endswith(".xml") or href.lower().endswith(".xml.gz")):
            continue
        links.append(href)

    tvpuls: list[str] = []
    puls2: list[str] = []
    for href in links:
        name = href.casefold()
        if "puls2" in name:
            puls2.append(href)
        elif "tvpuls" in name or "puls" in name:
            tvpuls.append(href)

    def pick(candidates: list[str]) -> str | None:
        if not candidates:
            return None
        candidates_sorted = sorted(set(candidates))
        return urljoin(base_url, candidates_sorted[-1])

    return _PulsEpgFiles(tvpuls_url=pick(tvpuls), puls2_url=pick(puls2))


@dataclass(frozen=True)
class _PulsItem:
    start_time: time
    end_time: time | None
    title: str
    description: str | None
    accessibility: list[AccessibilityFeature]
    sort_key: str


@dataclass(frozen=True)
class _PulsFilesCache:
    expires_at: float
    files: _PulsEpgFiles


@dataclass(frozen=True)
class _PulsScheduleCache:
    expires_at: float
    by_day: dict[date, list[_PulsItem]]


def parse_puls_epg_xml(xml: str, day: date) -> list[_PulsItem]:
    by_day = parse_puls_epg_xml_all_days(xml)
    return by_day.get(day) or []


def parse_puls_epg_xml_all_days(xml: str) -> dict[date, list[_PulsItem]]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}

    items_by_day: dict[date, list[_PulsItem]] = {}

    for ev in root.findall(".//event"):
        actual = ev.get("actual_time") or ""
        try:
            event_day = date.fromisoformat(actual[:10])
        except ValueError:
            continue

        start_dt = _parse_epg_datetime(actual)
        if not start_dt:
            continue
        end_dt = _parse_epg_datetime(ev.get("end_time") or "")

        desc_el = ev.find("description")
        title = clean_text(desc_el.get("title") if desc_el is not None else "") or clean_text(ev.get("original_title") or "")
        if not title:
            continue
        long_synopsis = desc_el.get("long_synopsis") if desc_el is not None else None
        synopsis = clean_multiline_text(long_synopsis or "") if long_synopsis else ""

        features, synopsis_clean = _extract_accessibility_from_synopsis(synopsis)

        items_by_day.setdefault(event_day, []).append(
            _PulsItem(
                start_time=start_dt.time().replace(microsecond=0),
                end_time=end_dt.time().replace(microsecond=0) if end_dt else None,
                title=title,
                description=synopsis_clean or None,
                accessibility=features,
                sort_key=actual,
            )
        )

    for day_items in items_by_day.values():
        day_items.sort(key=lambda it: it.sort_key)
    return items_by_day


def _parse_epg_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _extract_accessibility_from_synopsis(synopsis: str) -> tuple[list[AccessibilityFeature], str]:
    text = synopsis.strip()
    features: list[AccessibilityFeature] = []

    while True:
        m = re.match(r"^\((AD|JM|N)\)\s*", text)
        if not m:
            break
        token = m.group(1)
        if token == "AD":
            features.append("AD")
        elif token == "JM":
            features.append("JM")
        elif token == "N":
            features.append("N")
        text = text[m.end() :].lstrip()

    features = _uniq(features)
    return features, text


def _uniq(features: list[AccessibilityFeature]) -> list[AccessibilityFeature]:
    seen: set[AccessibilityFeature] = set()
    out: list[AccessibilityFeature] = []
    for f in features:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out
