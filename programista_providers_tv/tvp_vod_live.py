from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text


TVP_VOD_API_BASE = "https://vod.tvp.pl/api"
TVP_VOD_LIVE_PAGE = "https://vod.tvp.pl/live,1/tvp-muzyka-i-koncerty,2999109"
TVP_VOD_LIVE_SOURCE_ID = "tvp-muzyka-i-koncerty"
TVP_VOD_LIVE_SOURCE_NAME = "TVP Muzyka i Koncerty"
TVP_VOD_LIVE_ID = 2999109


class TvpVodLiveProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "tvp-vod-live"

    @property
    def display_name(self) -> str:
        return "Telewizja (TVP VOD Live)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId(TVP_VOD_LIVE_SOURCE_ID),
                name=TVP_VOD_LIVE_SOURCE_NAME,
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
        api_url = _tvp_vod_programmes_url(day, TVP_VOD_LIVE_ID)
        text = self._http.get_text(
            api_url,
            cache_key=f"tvp-vod-live:{TVP_VOD_LIVE_ID}:{day.isoformat()}",
            ttl_seconds=60 * 60,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        items = parse_tvp_vod_live_programmes(text, day)

        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=item.start_time,
                end_time=item.end_time,
                title=item.title,
                subtitle=None,
                details_ref=item.details_url,
                details_summary=item.description or None,
            )
            for item in items
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title


@dataclass(frozen=True)
class _TvpVodLiveItem:
    start_time: time | None
    end_time: time | None
    title: str
    description: str
    details_url: str | None


def _tvp_vod_programmes_url(day: date, live_id: int) -> str:
    day_start = _warsaw_datetime(day, time.min)
    day_end = _warsaw_datetime(day + timedelta(days=1), time.min)
    query = urlencode(
        [
            ("platform", "BROWSER"),
            ("since", day_start.strftime("%Y-%m-%dT%H:%M%z")),
            ("till", day_end.strftime("%Y-%m-%dT%H:%M%z")),
            ("liveId[]", str(live_id)),
        ]
    )
    return f"{TVP_VOD_API_BASE}/products/lives/programmes?{query}"


def parse_tvp_vod_live_programmes(text: str, day: date) -> list[_TvpVodLiveItem]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return []

    if isinstance(raw, dict):
        raw_items = raw.get("items")
    else:
        raw_items = raw
    if not isinstance(raw_items, list):
        return []

    day_start = _warsaw_datetime(day, time.min)
    day_end = _warsaw_datetime(day + timedelta(days=1), time.min)

    items: list[_TvpVodLiveItem] = []
    for raw_item in raw_items:
        parsed = _parse_tvp_vod_live_item(raw_item, day_start, day_end)
        if parsed is not None:
            items.append(parsed)
    return items


def _parse_tvp_vod_live_item(raw: Any, day_start: datetime, day_end: datetime) -> _TvpVodLiveItem | None:
    if not isinstance(raw, dict):
        return None

    title = clean_text(raw.get("title") or "")
    if not title:
        return None

    start_dt = _parse_tvp_vod_datetime(raw.get("since"))
    end_dt = _parse_tvp_vod_datetime(raw.get("till"))
    if start_dt is None or end_dt is None:
        return None

    if end_dt <= day_start or start_dt >= day_end:
        return None

    start_dt = max(start_dt, day_start)
    end_dt = min(end_dt, day_end)

    details_url = raw.get("webUrl") if isinstance(raw.get("webUrl"), str) else None
    description = _tvp_vod_description(raw)
    return _TvpVodLiveItem(
        start_time=_local_time(start_dt),
        end_time=_local_time(end_dt),
        title=title,
        description=description,
        details_url=details_url,
    )


def _parse_tvp_vod_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return _localize_warsaw(parsed)
    return _to_warsaw(parsed)


def _local_time(value: datetime) -> time:
    return _to_warsaw(value).time().replace(tzinfo=None, microsecond=0)


def _warsaw_datetime(day: date, value: time) -> datetime:
    naive = datetime.combine(day, value)
    return _localize_warsaw(naive)


def _localize_warsaw(value: datetime) -> datetime:
    offset = timedelta(hours=_warsaw_offset_hours_for_local(value.replace(tzinfo=None)))
    return value.replace(tzinfo=timezone(offset))


def _to_warsaw(value: datetime) -> datetime:
    if value.tzinfo is None:
        return _localize_warsaw(value)
    utc_naive = value.astimezone(timezone.utc).replace(tzinfo=None)
    offset = timedelta(hours=_warsaw_offset_hours_for_utc(utc_naive))
    return (utc_naive + offset).replace(tzinfo=timezone(offset))


def _warsaw_offset_hours_for_local(value: datetime) -> int:
    start = datetime.combine(_last_sunday(value.year, 3), time(2, 0))
    end = datetime.combine(_last_sunday(value.year, 10), time(3, 0))
    return 2 if start <= value < end else 1


def _warsaw_offset_hours_for_utc(value: datetime) -> int:
    start = datetime.combine(_last_sunday(value.year, 3), time(1, 0))
    end = datetime.combine(_last_sunday(value.year, 10), time(1, 0))
    return 2 if start <= value < end else 1


def _last_sunday(year: int, month: int) -> date:
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    days_since_sunday = (last_day.weekday() + 1) % 7
    return last_day - timedelta(days=days_since_sunday)


def _tvp_vod_description(raw: dict[str, Any]) -> str:
    for key in ("lead", "description", "descriptionLong", "description_long"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return _clean_tvp_vod_text(value)
    return ""


def _clean_tvp_vod_text(value: str) -> str:
    soup = BeautifulSoup(value, "lxml")
    return clean_multiline_text(soup.get_text(" ", strip=True))
