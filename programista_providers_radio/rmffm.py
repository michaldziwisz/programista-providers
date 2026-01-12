from __future__ import annotations

import re
import threading
import time as time_module
import urllib.request
from dataclasses import dataclass
from datetime import date, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_text, parse_time_hhmm


RMFFM_BASE = "https://www.rmf.fm"

# RMF FM publishes the schedule per weekday on static pages.
RMFFM_PAGE_BY_ISO_WEEKDAY: dict[int, str] = {
    1: "/ramowka-1.html",  # Monday
    2: "/ramowka-2.html",
    3: "/ramowka-3.html",
    4: "/ramowka-4.html",
    5: "/ramowka-5.html",
    6: "/ramowka-6.html",
    7: "/ramowka-0.html",  # Sunday
}


@dataclass(frozen=True)
class _RmfFmProgramme:
    start: time | None
    title: str
    details: str


@dataclass(frozen=True)
class _RmfFmDayCache:
    expires_at: float
    programmes: list[_RmfFmProgramme]


class RmfFmProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._cache_by_weekday: dict[int, _RmfFmDayCache] = {}

    @property
    def provider_id(self) -> str:
        return "rmffm"

    @property
    def display_name(self) -> str:
        return "RMF FM"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("rmffm"),
                name="RMF FM",
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
        if str(source.id) != "rmffm":
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
                details_ref=None,
                details_summary=p.details or None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title

    def _get_day_programmes(self, weekday: int, *, force_refresh: bool) -> list[_RmfFmProgramme]:
        if not force_refresh:
            with self._lock:
                cached = self._cache_by_weekday.get(weekday)
                if cached and cached.expires_at > time_module.time():
                    return cached.programmes

        path = RMFFM_PAGE_BY_ISO_WEEKDAY.get(weekday)
        if not path:
            return []

        url = f"{RMFFM_BASE}{path}"
        cache_key = f"rmffm:ramowka:v2:{weekday}"

        try:
            html = self._http.get_text(
                url,
                cache_key=cache_key,
                ttl_seconds=6 * 3600,
                force_refresh=force_refresh,
                timeout_seconds=20.0,
            )
        except Exception:  # noqa: BLE001
            html = ""

        programmes = _safe_parse_rmffm_ramowka_html(html)
        if not programmes and not force_refresh:
            try:
                html = self._http.get_text(
                    url,
                    cache_key=cache_key,
                    ttl_seconds=6 * 3600,
                    force_refresh=True,
                    timeout_seconds=20.0,
                )
            except Exception:  # noqa: BLE001
                html = ""
            programmes = _safe_parse_rmffm_ramowka_html(html)

        if not programmes:
            html = _fetch_url_text(url, timeout_seconds=20.0)
            programmes = _safe_parse_rmffm_ramowka_html(html)

        if not programmes:
            return [
                _RmfFmProgramme(
                    start=time(12, 0),
                    title="Brak ramówki RMF FM",
                    details=_format_debug_details(url=url, html=html),
                )
            ]

        with self._lock:
            self._cache_by_weekday[weekday] = _RmfFmDayCache(
                expires_at=time_module.time() + 6 * 3600,
                programmes=programmes,
            )
        return programmes


def parse_rmffm_ramowka_html(html: str) -> list[_RmfFmProgramme]:
    soup = _make_soup(html)
    row = soup.select_one(".xramowka") or soup
    blocks = row.select("div.col-12.xlh")
    if not blocks:
        return []

    programme_block = blocks[0]
    programmes: list[_RmfFmProgramme] = []

    current_start: time | None = None
    current_title = ""
    current_details_lines: list[str] = []

    def flush() -> None:
        nonlocal current_start, current_title, current_details_lines
        title = clean_text(current_title)
        if not title:
            current_start = None
            current_title = ""
            current_details_lines = []
            return

        seen: set[str] = set()
        details_lines: list[str] = []
        for line in current_details_lines:
            t = clean_text(line)
            if not t:
                continue
            key = t.casefold()
            if key in seen:
                continue
            seen.add(key)
            details_lines.append(t)
        programmes.append(_RmfFmProgramme(start=current_start, title=title, details="\n\n".join(details_lines)))

        current_start = None
        current_title = ""
        current_details_lines = []

    for nodes in _split_nodes_by_br(programme_block):
        line_text = _render_nodes_text(nodes)
        if not line_text:
            continue

        if re.match(r"^\\d{1,2}:\\d{2}\\s*-\\s*\\d{1,2}:\\d{2}\\b", line_text):
            if current_title:
                current_details_lines.append(line_text)
            continue

        m = re.match(r"^(\\d{1,2}:\\d{2})\\b\\s*(.*)$", line_text)
        if m:
            flush()
            current_start = _parse_time_hhmm_relaxed(m.group(1))
            rest = clean_text(m.group(2))
            title, details = _split_title_details(rest)
            current_title = title
            if details:
                current_details_lines.append(details)
            continue

        if current_title:
            current_details_lines.append(line_text)

    flush()

    seen: set[tuple[str, str]] = set()
    deduped: list[_RmfFmProgramme] = []
    for p in programmes:
        key = (p.start.strftime("%H:%M") if p.start else "", p.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return _normalize_wraparound_programmes(deduped)


def _split_nodes_by_br(container) -> list[list[object]]:
    out: list[list[object]] = []
    current: list[object] = []
    for node in container.children:
        if getattr(node, "name", None) == "br":
            if current:
                out.append(current)
                current = []
            continue
        current.append(node)
    if current:
        out.append(current)
    return out


def _render_nodes_text(nodes: list[object]) -> str:
    parts: list[str] = []
    for node in nodes:
        if getattr(node, "get_text", None):
            parts.append(node.get_text(" ", strip=True))
        else:
            parts.append(str(node))
    return clean_text(" ".join(parts))


def _parse_time_hhmm_relaxed(value: str) -> time | None:
    t = clean_text(value)
    if re.fullmatch(r"\\d:\\d{2}", t):
        t = "0" + t
    return parse_time_hhmm(t) if t else None


def _split_title_details(rest: str) -> tuple[str, str]:
    t = clean_text(rest)
    if not t:
        return ("", "")

    normalized = t.replace(" – ", " - ").replace(" — ", " - ")
    if " - " not in normalized:
        return (t, "")

    title_part, details_part = normalized.rsplit(" - ", 1)
    return (clean_text(title_part), clean_text(details_part))


def _safe_parse_rmffm_ramowka_html(html: str) -> list[_RmfFmProgramme]:
    try:
        return parse_rmffm_ramowka_html(html)
    except Exception:  # noqa: BLE001
        return []


def _make_soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001
        return BeautifulSoup(html, "html.parser")


def _fetch_url_text(url: str, *, timeout_seconds: float) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "programista-providers/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:  # noqa: S310
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
    except Exception:  # noqa: BLE001
        return ""

    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _normalize_wraparound_programmes(programmes: list[_RmfFmProgramme]) -> list[_RmfFmProgramme]:
    pivot: int | None = None
    last_start: time | None = None
    for idx, p in enumerate(programmes):
        if not p.start:
            continue
        if last_start and p.start < last_start:
            pivot = idx
            break
        last_start = p.start

    if pivot is None:
        return programmes
    return programmes[pivot:] + programmes[:pivot]


def _format_debug_details(*, url: str, html: str) -> str:
    lowered = html.casefold()
    contains = {
        "ramowka": "ramowka" in lowered or "ramówka" in lowered,
        "xramowka": "xramowka" in lowered,
        "salted": "salted" in lowered,
        "cookies": "cookie" in lowered or "rodo" in lowered,
    }

    title = ""
    if html:
        try:
            soup = _make_soup(html)
            title_el = soup.select_one("title")
            title = clean_text(title_el.get_text(" ")) if title_el else ""
        except Exception:  # noqa: BLE001
            title = ""

    lines = [
        "Nie udało się pobrać lub sparsować ramówki.",
        f"URL: {url}",
        f"HTML len: {len(html)}",
        f"HTML title: {title}" if title else "HTML title: (brak)",
        "Flags: " + ", ".join(f"{k}={v}" for k, v in contains.items()),
    ]
    return "\n".join(lines)
