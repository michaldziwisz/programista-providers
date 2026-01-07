from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


RP_BASE = "https://radiopoznan.fm"


@dataclass(frozen=True)
class _RpProgramme:
    start: time | None
    title: str
    details_ref: str | None


class RadioPoznanProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "radiopoznan"

    @property
    def display_name(self) -> str:
        return "Radio Poznań"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("poznan"),
                name="Radio Poznań",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
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
        if str(source.id) != "poznan":
            return []

        html = self._http.get_text(
            f"{RP_BASE}/program/{day.isoformat()}.html",
            cache_key=f"rp:program:{day.isoformat()}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        programmes = parse_rp_program_html(html)
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
                details_summary=None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:
        if not item.details_ref:
            return item.title

        url = urljoin(RP_BASE, str(item.details_ref))
        try:
            html = self._http.get_text(
                url,
                cache_key=f"rp:details:{item.details_ref}",
                ttl_seconds=24 * 3600,
                force_refresh=force_refresh,
                timeout_seconds=20.0,
            )
        except Exception:  # noqa: BLE001
            return item.title

        details = parse_rp_audycje_details_html(html)
        return details or item.title


def _parse_start_time(range_text: str) -> time | None:
    t = clean_text(range_text)
    m = re.search(r"\b(\d{1,2}:\d{2})\b", t)
    if not m:
        return None
    value = m.group(1)
    if len(value) == 4:  # e.g. 9:00
        value = "0" + value
    return parse_time_hhmm(value)


def parse_rp_program_html(html: str) -> list[_RpProgramme]:
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one("#play_list") or soup

    items: list[_RpProgramme] = []
    for li in container.select("li"):
        time_el = li.select_one("span.time")
        if not time_el:
            continue
        time_text = clean_text(time_el.get_text(" "))
        start = _parse_start_time(time_text)

        a = li.select_one("a[href]")
        details_ref = clean_text(a.get("href") or "") if a else ""
        details_ref = details_ref or None

        if a:
            title = clean_text(a.get_text(" "))
        else:
            raw = clean_text(li.get_text(" ", strip=True))
            if time_text and raw.startswith(time_text):
                raw = raw[len(time_text) :]
            title = clean_text(raw)

        if not title:
            continue

        items.append(_RpProgramme(start=start, title=title, details_ref=details_ref))

    seen: set[tuple[str, str, str]] = set()
    out: list[_RpProgramme] = []
    for it in items:
        key = (it.start.strftime("%H:%M") if it.start else "", it.title.casefold(), (it.details_ref or "").casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def parse_rp_audycje_details_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    article = soup.select_one("article.rm-broadcast") or soup.select_one("article.rm-news-item") or soup.select_one(
        "article"
    )
    if article:
        h2 = article.select_one("h2")
        title = clean_text(h2.get_text(" ")) if h2 else ""

        p = article.select_one("p")
        body = clean_multiline_text(p.get_text("\n")) if p else ""

        parts = [p for p in (title, body) if p]
        if parts:
            return "\n\n".join(parts)

    meta = soup.select_one('meta[name=\"description\"]')
    if meta and meta.get("content"):
        return clean_text(str(meta.get("content")))
    return ""

