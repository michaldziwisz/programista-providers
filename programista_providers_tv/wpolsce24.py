from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


WPOLSCE24_SCHEDULE_URL = "https://wpolsce24.tv/ramowka"
WPOLSCE24_SOURCE_ID = "wpolsce24"
WPOLSCE24_SOURCE_NAME = "wPolsce24"

_WPOLSCE24_WEEKDAY = "weekday"
_WPOLSCE24_SATURDAY = "saturday"
_WPOLSCE24_SUNDAY = "sunday"

_WPOLSCE24_SUMMARY_TO_KEY = {
    "poniedziałek-piątek": _WPOLSCE24_WEEKDAY,
    "sobota": _WPOLSCE24_SATURDAY,
    "niedziela": _WPOLSCE24_SUNDAY,
}


class Wpolsce24Provider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "wpolsce24"

    @property
    def display_name(self) -> str:
        return "Telewizja (wPolsce24)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId(WPOLSCE24_SOURCE_ID),
                name=WPOLSCE24_SOURCE_NAME,
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
        html = self._http.get_text(
            WPOLSCE24_SCHEDULE_URL,
            cache_key="wpolsce24:ramowka",
            ttl_seconds=60 * 60,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        groups = parse_wpolsce24_schedule_page(html)
        items = groups.get(_wpolsce24_schedule_key_for_day(day)) or []

        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=item.start_time,
                end_time=item.end_time,
                title=item.title,
                subtitle=None,
                details_ref=None,
                details_summary=item.description or None,
            )
            for item in items
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title


@dataclass(frozen=True)
class _Wpolsce24Item:
    start_time: time | None
    end_time: time | None
    title: str
    description: str


def _wpolsce24_schedule_key_for_day(day: date) -> str:
    weekday = day.weekday()
    if weekday == 5:
        return _WPOLSCE24_SATURDAY
    if weekday == 6:
        return _WPOLSCE24_SUNDAY
    return _WPOLSCE24_WEEKDAY


def parse_wpolsce24_schedule_page(html: str) -> dict[str, list[_Wpolsce24Item]]:
    soup = BeautifulSoup(html, "lxml")

    out: dict[str, list[_Wpolsce24Item]] = {}
    for details in soup.select("div.description details"):
        summary = details.find("summary")
        key = _map_wpolsce24_summary_to_key(summary.get_text(" ", strip=True) if summary else "")
        if not key or key in out:
            continue

        items: list[_Wpolsce24Item] = []
        for block in details.select("div.pr"):
            parsed = _parse_wpolsce24_block(block)
            if parsed is not None:
                items.append(parsed)

        items = _fill_wpolsce24_end_times(items)
        if items:
            out[key] = items

    return out


def _map_wpolsce24_summary_to_key(value: str) -> str | None:
    summary = clean_text(value).casefold()
    summary = summary.replace("▼", "").replace("▾", "").strip()
    return _WPOLSCE24_SUMMARY_TO_KEY.get(summary)


def _parse_wpolsce24_block(block: BeautifulSoup) -> _Wpolsce24Item | None:
    time_el = block.select_one("div.pt")
    meta_el = block.select_one("div.pi")
    if not time_el or not meta_el:
        return None

    start_time = parse_time_hhmm(clean_text(time_el.get_text(" ")))

    texts = [clean_text(text) for text in meta_el.stripped_strings]
    texts = [text for text in texts if text]
    if not texts:
        return None

    title = _normalize_wpolsce24_title(texts[0])
    if not title:
        return None

    description = clean_multiline_text("\n".join(texts[1:]))
    return _Wpolsce24Item(start_time=start_time, end_time=None, title=title, description=description)


def _normalize_wpolsce24_title(value: str) -> str:
    title = clean_text(value)
    title = re.sub(r"^[^\w]+", "", title, flags=re.UNICODE)
    return clean_text(title)


def _fill_wpolsce24_end_times(items: list[_Wpolsce24Item]) -> list[_Wpolsce24Item]:
    out: list[_Wpolsce24Item] = []
    for idx, item in enumerate(items):
        end_time = items[idx + 1].start_time if idx + 1 < len(items) else None
        out.append(
            _Wpolsce24Item(
                start_time=item.start_time,
                end_time=end_time,
                title=item.title,
                description=item.description,
            )
        )
    return out
