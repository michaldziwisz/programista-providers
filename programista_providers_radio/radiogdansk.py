from __future__ import annotations

import re
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


RG_URL = "https://radiogdansk.pl/ramowka-radia-gdansk/"

_RG_TIME_TOKEN_RE = re.compile(r"\b(\d{1,2}[.:]\d{2})\b")
_RG_TIME_LINE_RE = re.compile(
    r"^\s*(\d{1,2}[.:]\d{2})\s*(?:[-–—]\s*(\d{1,2}[.:]\d{2}))?\s*(.*)$",
    flags=re.IGNORECASE,
)
_RG_WEEKDAY_TOKEN_RE = re.compile(r"\b(pon|wt|śr|sr|czw|pt)\.\s*", flags=re.IGNORECASE)
_RG_WEEKDAY_LINE_RE = re.compile(r"^\s*(pon|wt|śr|sr|czw|pt)\.\s*(.*)$", flags=re.IGNORECASE)

_RG_ABBR_TO_ISO_WEEKDAY: dict[str, int] = {
    "pon": 1,
    "wt": 2,
    "śr": 3,
    "sr": 3,
    "czw": 4,
    "pt": 5,
}

_RG_SKIP_PREFIXES = [
    "autopilot",
    "wiadomości/pogoda",
    "wiadomosci/pogoda",
    "infopilot",
    "powieść w radiu gdańsk",
    "powiesc w radiu gdansk",
]


@dataclass(frozen=True)
class _RgProgramme:
    start: time | None
    title: str
    details: str


@dataclass(frozen=True)
class _RgParsedSchedule:
    by_iso_weekday: dict[int, list[_RgProgramme]]


@dataclass(frozen=True)
class _RgScheduleCache:
    expires_at: float
    parsed: _RgParsedSchedule


class RadioGdanskProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._cache: _RgScheduleCache | None = None

    @property
    def provider_id(self) -> str:
        return "radiogdansk"

    @property
    def display_name(self) -> str:
        return "Radio Gdańsk"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("radiogdansk"),
                name="Radio Gdańsk",
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
        if str(source.id) != "radiogdansk":
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
                details_ref=None,
                details_summary=p.details or None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        # No separate details endpoint; we embed what we have in details_summary.
        return item.details_summary or item.title

    def _get_parsed_schedule(self, *, force_refresh: bool) -> _RgParsedSchedule:
        if not force_refresh:
            with self._lock:
                cached = self._cache
                if cached and cached.expires_at > time_module.time():
                    return cached.parsed

        html = self._http.get_text(
            RG_URL,
            cache_key="rg:ramowka:v1",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        parsed = parse_rg_ramowka_html(html)

        with self._lock:
            self._cache = _RgScheduleCache(expires_at=time_module.time() + 6 * 3600, parsed=parsed)
        return parsed


def parse_rg_ramowka_html(html: str) -> _RgParsedSchedule:
    soup = BeautifulSoup(html, "lxml")

    weekday_editor = _find_text_editor_after_heading(soup, "PONIEDZIAŁEK") or _find_text_editor_after_heading(
        soup, "PONIEDZIALEK"
    )
    saturday_editor = _find_text_editor_after_heading(soup, "SOBOTA")
    sunday_editor = _find_text_editor_after_heading(soup, "NIEDZIELA")

    by_iso_weekday: dict[int, list[_RgProgramme]] = {i: [] for i in range(1, 8)}

    if weekday_editor:
        lines = _extract_editor_lines(weekday_editor)
        by_iso_weekday.update(_parse_rg_mon_fri_lines(lines))

    if saturday_editor:
        by_iso_weekday[6] = _parse_rg_simple_lines(_extract_editor_lines(saturday_editor))

    if sunday_editor:
        by_iso_weekday[7] = _parse_rg_simple_lines(_extract_editor_lines(sunday_editor))

    return _RgParsedSchedule(by_iso_weekday=by_iso_weekday)


def _find_text_editor_after_heading(soup: BeautifulSoup, needle: str):
    needle_u = needle.upper()
    for heading in soup.select("div.elementor-widget-heading"):
        text = clean_text(heading.get_text(" "))
        if needle_u not in text.upper():
            continue
        editor = heading.find_next("div", class_="elementor-widget-text-editor")
        if editor:
            return editor
    return None


def _extract_editor_lines(editor) -> list[str]:
    lines: list[str] = []
    for p in editor.select("p"):
        if p.find("br"):
            raw = clean_multiline_text(p.get_text("\n"))
            for ln in raw.splitlines():
                t = clean_text(ln)
                if t:
                    lines.append(t)
            continue
        t = clean_text(p.get_text(" "))
        if t:
            lines.append(t)
    return lines


def _looks_like_time_list(line: str) -> bool:
    t = clean_text(line)
    if not t:
        return False
    if re.search(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", t):
        return False
    times = _RG_TIME_TOKEN_RE.findall(t)
    if len(times) < 2:
        return False
    if any(dash in t for dash in ("-", "–", "—")):
        return False
    return "," in t


def _should_skip_line(line: str) -> bool:
    t = clean_text(line)
    if not t:
        return True
    if _looks_like_time_list(t):
        return True
    low = t.casefold()
    return any(low.startswith(prefix) for prefix in _RG_SKIP_PREFIXES)


def _parse_rg_mon_fri_lines(lines: list[str]) -> dict[int, list[_RgProgramme]]:
    by_weekday: dict[int, list[_RgProgramme]] = {i: [] for i in range(1, 6)}

    @dataclass
    class _PendingSlot:
        start: time
        group_title: str
        variants: dict[int, str]
        extras: dict[int, list[_RgProgramme]]

    pending: _PendingSlot | None = None

    def flush() -> None:
        nonlocal pending
        if not pending:
            return

        for wd in range(1, 6):
            title = clean_text(pending.variants.get(wd) or pending.group_title)
            if not title:
                continue
            details = ""
            if pending.variants and pending.group_title and title.casefold() != pending.group_title.casefold():
                details = pending.group_title
            by_weekday[wd].append(_RgProgramme(start=pending.start, title=title, details=details))

            for ex in pending.extras.get(wd, []):
                by_weekday[wd].append(ex)

        pending = None

    for line in lines:
        if _should_skip_line(line):
            continue

        time_match = _RG_TIME_LINE_RE.match(line)
        if time_match:
            flush()

            start = _parse_time_token(time_match.group(1))
            if not start:
                continue

            rest = clean_text(time_match.group(3))
            if not rest:
                continue

            prefix, variants = _parse_inline_weekday_variants(rest)
            if variants:
                extras: dict[int, list[_RgProgramme]] = {}
                adjusted_variants: dict[int, str] = {}
                for wd, v in variants.items():
                    base, embedded = _extract_embedded_time_slots(v)
                    adjusted_variants[wd] = _compose_prefix_title(prefix, base)
                    if embedded:
                        extras[wd] = [
                            _RgProgramme(start=t, title=_compose_prefix_title(prefix, title), details="")
                            for t, title in embedded
                            if title and t
                        ]
                pending = _PendingSlot(start=start, group_title=clean_text(prefix), variants=adjusted_variants, extras=extras)
                flush()
                continue

            pending = _PendingSlot(start=start, group_title=rest, variants={}, extras={})
            continue

        if pending:
            m = _RG_WEEKDAY_LINE_RE.match(line)
            if not m:
                continue
            wd = _RG_ABBR_TO_ISO_WEEKDAY.get(m.group(1).casefold())
            if not wd:
                continue
            title = clean_text(m.group(2))
            if title:
                pending.variants[wd] = title

    flush()

    for wd in range(1, 6):
        by_weekday[wd] = _dedupe_programmes(by_weekday[wd])
    return by_weekday


def _parse_rg_simple_lines(lines: list[str]) -> list[_RgProgramme]:
    out: list[_RgProgramme] = []
    for line in lines:
        if _should_skip_line(line):
            continue
        m = _RG_TIME_LINE_RE.match(line)
        if not m:
            continue
        start = _parse_time_token(m.group(1))
        if not start:
            continue
        title = clean_text(m.group(3))
        if not title:
            continue
        out.append(_RgProgramme(start=start, title=title, details=""))
    return _dedupe_programmes(out)


def _parse_time_token(token: str) -> time | None:
    t = clean_text(token).replace(".", ":")
    if not t:
        return None
    if len(t) == 4 and t[1] == ":":  # e.g. 6:00
        t = "0" + t
    if t.startswith("24:"):
        return None
    try:
        return parse_time_hhmm(t[:5])
    except Exception:  # noqa: BLE001
        return None


def _parse_inline_weekday_variants(text: str) -> tuple[str, dict[int, str]]:
    t = clean_text(text)
    matches = list(_RG_WEEKDAY_TOKEN_RE.finditer(t))
    if not matches:
        return "", {}

    prefix = clean_text(t[: matches[0].start()]).strip(" ,;")
    variants: dict[int, str] = {}
    for i, m in enumerate(matches):
        abbr = m.group(1).casefold()
        wd = _RG_ABBR_TO_ISO_WEEKDAY.get(abbr)
        if not wd:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(t)
        seg = clean_text(t[start:end]).strip(" ,;")
        if seg:
            variants[wd] = seg
    return prefix, variants


def _extract_embedded_time_slots(text: str) -> tuple[str, list[tuple[time | None, str]]]:
    t = clean_text(text)
    matches = list(_RG_TIME_TOKEN_RE.finditer(t))
    if not matches:
        return t, []

    # Ignore a leading time token; callers use this only on per-weekday segments.
    if matches and matches[0].start() == 0:
        return t, []

    main = clean_text(t[: matches[0].start()]).strip(" ,;")
    extras: list[tuple[time | None, str]] = []
    for i, m in enumerate(matches):
        time_token = m.group(1)
        start = _parse_time_token(time_token)
        if not start:
            continue
        seg_start = m.end()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(t)
        title = clean_text(t[seg_start:seg_end]).strip(" ,;")
        if title:
            extras.append((start, title))
    return main, extras


def _compose_prefix_title(prefix: str, title: str) -> str:
    p = clean_text(prefix).strip()
    t = clean_text(title).strip()
    if not p:
        return t
    if not t:
        return p
    if t.casefold().startswith(p.casefold()):
        return t
    sep = " " if p.endswith(("-", "–", "—", ":")) else " — "
    return clean_text(f"{p}{sep}{t}")


def _dedupe_programmes(items: list[_RgProgramme]) -> list[_RgProgramme]:
    seen: set[tuple[str, str]] = set()
    out: list[_RgProgramme] = []
    for it in items:
        start_key = it.start.strftime("%H:%M") if it.start else ""
        key = (start_key, it.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

