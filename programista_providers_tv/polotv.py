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


POLOTV_MODULE_URL = "https://www.polotv.pl/tv-html/module/page{page}/"
POLOTV_MORE_URL = "https://www.polotv.pl/tv-more/module/page{page}/"

POLOTV_SOURCE_ID = "polotv"
POLOTV_SOURCE_NAME = "Polo TV"
# Nazwa kanału w atrybucie data-channel wiersza ramówki na polotv.pl.
POLOTV_CHANNEL_LABEL = "Polo TV"

# Serwis udostępnia moduły page1..page7 (dzisiaj + 6 kolejnych dni).
POLOTV_PAGE_COUNT = 7

_MODULE_TTL_SECONDS = 6 * 3600
_MORE_TTL_SECONDS = 6 * 3600
_DAY_CACHE_TTL_SECONDS = 6 * 3600


class PoloTvProvider(ScheduleProvider):
    """
    Ramówka Polo TV z modułów programu na polotv.pl.

    Moduł ``page{N}`` to okno od ok. 06:00 dnia ``dzisiaj + N - 1`` do 06:00 dnia
    następnego, więc pełny dzień kalendarzowy powstaje ze złożenia dwóch modułów
    (wczesny ranek pochodzi z modułu poprzedniego dnia).

    Opisy programów leżą w osobnym zasobie JSON ``tv-more/module/page{N}``
    (mapa ``id programu`` -> ``[opis, miniatura, "", lista udogodnień]``) i są
    pobierane dopiero przy podglądzie szczegółów.
    """

    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._day_cache: dict[str, _PoloTvDayCache] = {}

    @property
    def provider_id(self) -> str:
        return "polotv"

    @property
    def display_name(self) -> str:
        return "Telewizja (Polo TV)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId(POLOTV_SOURCE_ID),
                name=POLOTV_SOURCE_NAME,
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
        today = date.today()
        return [today + timedelta(days=i) for i in range(POLOTV_PAGE_COUNT)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        day_key = day.isoformat()
        if not force_refresh:
            with self._lock:
                cached = self._day_cache.get(day_key)
                if cached and cached.expires_at > time_module.time():
                    return _with_source(cached.items, source)

        items = self._build_day_items(day, force_refresh=force_refresh)
        with self._lock:
            self._day_cache[day_key] = _PoloTvDayCache(
                expires_at=time_module.time() + _DAY_CACHE_TTL_SECONDS,
                items=items,
            )
        return _with_source(items, source)

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:
        ref = parse_polotv_details_ref(item.details_ref)
        if ref is None:
            return item.details_summary or item.title

        page, programme_id = ref
        try:
            text = self._fetch_more(page, force_refresh=force_refresh)
        except Exception:  # noqa: BLE001
            return item.details_summary or item.title

        details = parse_polotv_more_entry(text, programme_id)
        if details is None:
            return item.details_summary or item.title

        return _format_details_text(
            title=item.title,
            description=details.description,
            accessibility=details.accessibility,
        )

    def _build_day_items(self, day: date, *, force_refresh: bool) -> list[_PoloTvScheduleItem]:
        today = date.today()
        offset = (day - today).days
        if offset < 0 or offset >= POLOTV_PAGE_COUNT:
            return []

        # Główne okno dnia (od ok. 06:00) plus wczesny ranek z modułu dnia poprzedniego.
        pages = [offset + 1]
        if offset > 0:
            pages.append(offset)

        collected: list[_PoloTvScheduleItem] = []
        for page in pages:
            html = self._fetch_module(page, force_refresh=force_refresh)
            for parsed in parse_polotv_module(html, channel=POLOTV_CHANNEL_LABEL):
                if parsed.start.date() != day:
                    continue
                collected.append(
                    _PoloTvScheduleItem(
                        start_time=parsed.start.time().replace(microsecond=0),
                        end_time=parsed.end.time().replace(microsecond=0) if parsed.end else None,
                        title=parsed.title,
                        details_ref=_format_polotv_details_ref(page, parsed.programme_id),
                        start_ms=parsed.start_ms,
                    )
                )

        collected.sort(key=lambda it: (it.start_ms, it.title.casefold()))
        return _dedupe_by_start_and_title(collected)

    def _fetch_module(self, page: int, *, force_refresh: bool) -> str:
        return self._http.get_text(
            POLOTV_MODULE_URL.format(page=page),
            cache_key=f"polotv:module:{date.today().isoformat()}:{page}",
            ttl_seconds=_MODULE_TTL_SECONDS,
            force_refresh=force_refresh,
            timeout_seconds=25.0,
        )

    def _fetch_more(self, page: int, *, force_refresh: bool) -> str:
        return self._http.get_text(
            POLOTV_MORE_URL.format(page=page),
            cache_key=f"polotv:more:{date.today().isoformat()}:{page}",
            ttl_seconds=_MORE_TTL_SECONDS,
            force_refresh=force_refresh,
            timeout_seconds=25.0,
        )


@dataclass(frozen=True)
class _PoloTvScheduleItem:
    start_time: time
    end_time: time | None
    title: str
    details_ref: str | None
    start_ms: int


@dataclass(frozen=True)
class _PoloTvDayCache:
    expires_at: float
    items: list[_PoloTvScheduleItem]


@dataclass(frozen=True)
class PoloTvModuleItem:
    start: datetime
    end: datetime | None
    title: str
    programme_id: str
    start_ms: int


@dataclass(frozen=True)
class PoloTvDetails:
    description: str
    accessibility: tuple[AccessibilityFeature, ...]


def parse_polotv_module(html: str, *, channel: str) -> list[PoloTvModuleItem]:
    """Wyciąga pozycje jednego kanału (po ``data-channel``) z modułu ramówki."""
    soup = BeautifulSoup(html, "lxml")

    items: list[PoloTvModuleItem] = []
    for row in soup.select("div.tv__row[data-channel]"):
        if clean_text(row.get("data-channel") or "") != channel:
            continue
        items.extend(_parse_polotv_row(row))

    items.sort(key=lambda it: (it.start_ms, it.title.casefold()))

    seen: set[tuple[int, str]] = set()
    out: list[PoloTvModuleItem] = []
    for item in items:
        key = (item.start_ms, item.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _parse_polotv_row(row: Any) -> list[PoloTvModuleItem]:
    out: list[PoloTvModuleItem] = []
    for cast in row.select("div.tvcast[data-start]"):
        start_ms = _parse_epoch_ms(cast.get("data-start"))
        if start_ms is None:
            continue
        end_ms = _parse_epoch_ms(cast.get("data-end"))

        title_el = cast.select_one(".tvcast__title")
        if title_el is None:
            continue
        title = clean_text(title_el.get_text(" ")) or clean_text(title_el.get("title") or "")
        if not title:
            continue

        programme_id = clean_text(title_el.get("data-id") or "")

        out.append(
            PoloTvModuleItem(
                start=datetime.fromtimestamp(start_ms / 1000),
                end=datetime.fromtimestamp(end_ms / 1000) if end_ms is not None else None,
                title=title,
                programme_id=programme_id,
                start_ms=start_ms,
            )
        )
    return out


def parse_polotv_more_entry(text: str, programme_id: str) -> PoloTvDetails | None:
    """Czyta jeden wpis z zasobu ``tv-more`` (mapa id -> [opis, obrazek, "", udogodnienia])."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None

    entry = raw.get(programme_id)
    if not isinstance(entry, list) or not entry:
        return None

    description = _clean_polotv_description(entry[0] if isinstance(entry[0], str) else "")

    accessibility: list[AccessibilityFeature] = []
    features = entry[3] if len(entry) > 3 else None
    if isinstance(features, list):
        for feature in features:
            normalized = _normalize_accessibility_feature(feature)
            if normalized is not None and normalized not in accessibility:
                accessibility.append(normalized)

    if not description and not accessibility:
        return None
    return PoloTvDetails(description=description, accessibility=tuple(accessibility))


def _normalize_accessibility_feature(value: Any) -> AccessibilityFeature | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if normalized in ("AD", "JM", "N"):
        return normalized  # type: ignore[return-value]
    return None


def _clean_polotv_description(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "lxml")
    # <hr> rozdziela nagłówek (np. "Reż.: ...") od właściwego opisu, <br> łamie akapit.
    for br in soup.find_all(["hr", "br"]):
        br.replace_with("\n")
    return clean_multiline_text(soup.get_text(" "))


def _format_details_text(
    *,
    title: str,
    description: str,
    accessibility: tuple[AccessibilityFeature, ...],
) -> str:
    parts: list[str] = []
    if accessibility:
        parts.append("Udogodnienia: " + ", ".join(_ACCESSIBILITY_LABELS[f] for f in accessibility))
    if description:
        parts.append(description)
    if not parts:
        return title
    return "\n".join(parts)


_ACCESSIBILITY_LABELS: dict[AccessibilityFeature, str] = {
    "AD": "audiodeskrypcja",
    "JM": "język migowy",
    "N": "napisy",
}


def _format_polotv_details_ref(page: int, programme_id: str) -> str | None:
    if not programme_id:
        return None
    return f"{page}|{programme_id}"


def parse_polotv_details_ref(details_ref: str | None) -> tuple[int, str] | None:
    if not details_ref:
        return None
    page_raw, _, programme_id = details_ref.partition("|")
    if not page_raw.isdigit() or not programme_id:
        return None
    page = int(page_raw)
    if page < 1 or page > POLOTV_PAGE_COUNT:
        return None
    return page, programme_id


def _parse_epoch_ms(value: Any) -> int | None:
    if not isinstance(value, str) or not value.isdigit():
        return None
    return int(value)


def _dedupe_by_start_and_title(items: list[_PoloTvScheduleItem]) -> list[_PoloTvScheduleItem]:
    seen: set[tuple[int, str]] = set()
    out: list[_PoloTvScheduleItem] = []
    for item in items:
        key = (item.start_ms, item.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _with_source(items: list[_PoloTvScheduleItem], source: Source) -> list[ScheduleItem]:
    return [
        ScheduleItem(
            provider_id=ProviderId("polotv"),
            source=source,
            day=_day_for_item(item),
            start_time=item.start_time,
            end_time=item.end_time,
            title=item.title,
            subtitle=None,
            details_ref=item.details_ref,
            details_summary=None,
        )
        for item in items
    ]


def _day_for_item(item: _PoloTvScheduleItem) -> date:
    return datetime.fromtimestamp(item.start_ms / 1000).date()
