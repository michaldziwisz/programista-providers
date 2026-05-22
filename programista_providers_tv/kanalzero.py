from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


TELEMAGAZYN_BASE_URL = "https://telemagazyn.pl"
KANALZERO_SCHEDULE_URL = f"{TELEMAGAZYN_BASE_URL}/stacje/kanal-zero"
JINA_READER_URL_PREFIX = "https://r.jina.ai/http://"
KANALZERO_SOURCE_ID = "kanalzero"
KANALZERO_SOURCE_NAME = "Kanał Zero"

_JINA_LINK_RE = re.compile(r"## \[(?P<label>.*?)\]\((?P<href>https://telemagazyn\.pl/[^)]+/pr/\d+)\)", re.S)
_JINA_TIME_RE = re.compile(r"^(?P<body>.*?)\s+(?P<time>\d{2}:\d{2})(?P<labels>(?:\s+(?:●\s+)?(?:Na żywo|Trwa))*)$")


class KanalZeroProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "kanalzero"

    @property
    def display_name(self) -> str:
        return "Telewizja (Kanał Zero)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId(KANALZERO_SOURCE_ID),
                name=KANALZERO_SOURCE_NAME,
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
        today = date.today()
        return [today + timedelta(days=i) for i in range(10)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        schedule_url = _kanalzero_schedule_url(day)
        html = self._http.get_text(
            schedule_url,
            cache_key=f"kanalzero:telemagazyn:{day.isoformat()}",
            ttl_seconds=60 * 60,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        items = parse_kanalzero_schedule_page(html)
        if not items and _looks_like_telemagazyn_challenge(html):
            reader_text = self._http.get_text(
                _jina_reader_url(schedule_url),
                cache_key=f"kanalzero:jina:{day.isoformat()}",
                ttl_seconds=60 * 60,
                force_refresh=force_refresh,
                timeout_seconds=30.0,
            )
            items = parse_kanalzero_schedule_page(reader_text)
            if not items:
                raise RuntimeError("Nie udało się pobrać ramówki Kanału Zero z Telemagazynu ani Jina Reader")

        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=item.start_time,
                end_time=item.end_time,
                title=item.title,
                subtitle=item.subtitle or None,
                details_ref=item.details_url,
                details_summary=item.details_summary or None,
            )
            for item in items
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title


@dataclass(frozen=True)
class _KanalZeroItem:
    start_time: time | None
    end_time: time | None
    title: str
    subtitle: str
    details_summary: str
    details_url: str | None


def _kanalzero_schedule_url(day: date) -> str:
    return f"{KANALZERO_SCHEDULE_URL}?dzien={day.isoformat()}"


def _jina_reader_url(url: str) -> str:
    return f"{JINA_READER_URL_PREFIX}{url}"


def parse_kanalzero_schedule_page(html: str) -> list[_KanalZeroItem]:
    soup = BeautifulSoup(html, "lxml")
    items: list[_KanalZeroItem] = []

    for item_el in soup.select("li.componentsTvChannelTvGuide__item"):
        tile = item_el.find("div", class_="atomsTvChannelEmissionTile", recursive=False)
        if tile is None:
            continue

        parsed = _parse_kanalzero_tile(tile)
        if parsed is not None:
            items.append(parsed)

    if items:
        return _fill_kanalzero_end_times(items)

    return _parse_kanalzero_jina_markdown(html)


def _parse_kanalzero_tile(tile: BeautifulSoup) -> _KanalZeroItem | None:
    title_el = tile.select_one(".atomsTvChannelEmissionTile__title")
    time_el = tile.select_one("time.atomsTvChannelEmissionTile__emissionStartDate")
    if title_el is None or time_el is None:
        return None

    title = clean_text(title_el.get_text(" "))
    if not title:
        return None

    start_time = _parse_telemagazyn_time(
        time_el.get("data-time") or time_el.get("datetime") or time_el.get_text(" ")
    )
    end_time = _parse_telemagazyn_time(time_el.get("data-endtime"))

    meta = _parse_kanalzero_meta(tile)
    labels = _parse_kanalzero_labels(tile)
    subtitle = clean_text(" | ".join(labels + ([meta] if meta else [])))

    lead_el = tile.select_one(".atomsTvChannelEmissionTile__lead")
    lead = clean_multiline_text(lead_el.get_text(" ", strip=True) if lead_el else "")
    details_summary = clean_multiline_text("\n".join(part for part in [subtitle, lead] if part))

    link = tile.select_one("a.atomsTvChannelEmissionTile__tileLink")
    href = link.get("href") if link else None
    details_url = urljoin(TELEMAGAZYN_BASE_URL, href) if href else None

    return _KanalZeroItem(
        start_time=start_time,
        end_time=end_time,
        title=title,
        subtitle=subtitle,
        details_summary=details_summary,
        details_url=details_url,
    )


def _parse_kanalzero_meta(tile: BeautifulSoup) -> str:
    meta_el = tile.select_one(".atomsTvChannelEmissionTile__episodeSeasonCategory")
    return clean_text(meta_el.get_text(" ", strip=True) if meta_el else "")


def _parse_kanalzero_labels(tile: BeautifulSoup) -> list[str]:
    labels: list[str] = []
    for label_el in tile.select(".atomsTvChannelEmissionTile__labelContainer .atomsPartialLabelLabelFill"):
        label = clean_text(label_el.get_text(" ", strip=True))
        if label:
            labels.append(label)
    return labels


def _parse_telemagazyn_time(value: str | None) -> time | None:
    value = clean_text(value or "")
    if not value:
        return None
    if "T" not in value:
        return parse_time_hhmm(value)
    try:
        return datetime.fromisoformat(value).time().replace(tzinfo=None)
    except ValueError:
        return None


def _parse_kanalzero_jina_markdown(text: str) -> list[_KanalZeroItem]:
    items: list[_KanalZeroItem] = []
    for match in _JINA_LINK_RE.finditer(text):
        label = clean_text(match.group("label"))
        href = match.group("href")
        parsed = _parse_kanalzero_jina_link(label, href)
        if parsed is not None:
            items.append(parsed)

    return _fill_kanalzero_end_times(items)


def _parse_kanalzero_jina_link(label: str, href: str) -> _KanalZeroItem | None:
    match = _JINA_TIME_RE.match(label)
    if match is None:
        return None

    body = clean_text(match.group("body"))
    start_time = parse_time_hhmm(match.group("time"))
    labels = _parse_jina_labels(match.group("labels") or "")
    title, summary = _split_jina_title_and_summary(body, href)

    if not title:
        return None

    subtitle = clean_text(" | ".join(labels))
    details_summary = clean_multiline_text("\n".join(part for part in [subtitle, summary] if part))

    return _KanalZeroItem(
        start_time=start_time,
        end_time=None,
        title=title,
        subtitle=subtitle,
        details_summary=details_summary,
        details_url=href,
    )


def _parse_jina_labels(value: str) -> list[str]:
    labels: list[str] = []
    normalized = clean_text(value.replace("●", " "))
    for label in ("Trwa", "Na żywo"):
        if label in normalized:
            labels.append(label)
    return labels


def _split_jina_title_and_summary(body: str, href: str) -> tuple[str, str]:
    slug = _telemagazyn_program_slug(href)
    if not slug:
        return _split_jina_title_by_metadata(body)

    words = body.split()
    tokens: list[str] = []
    for idx, word in enumerate(words):
        token = _slug_token(word)
        if not token:
            continue
        tokens.append(token)
        if "-".join(tokens) == slug:
            return clean_text(" ".join(words[: idx + 1])), clean_text(" ".join(words[idx + 1 :]))
        if not slug.startswith("-".join(tokens)):
            break

    return _split_jina_title_by_metadata(body)


def _split_jina_title_by_metadata(body: str) -> tuple[str, str]:
    match = re.search(r"\s+(Odcinek|Sezon)\s+\d+\b", body)
    if match:
        return clean_text(body[: match.start()]), clean_text(body[match.start() :])
    return clean_text(body), ""


def _telemagazyn_program_slug(href: str) -> str:
    path_parts = [part for part in urlparse(href).path.split("/") if part]
    if len(path_parts) < 2 or path_parts[-2] != "pr":
        return ""
    return clean_text(path_parts[-3] if len(path_parts) >= 3 else "")


def _slug_token(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^0-9a-zA-Z]+", "", value).casefold()
    return value


def _fill_kanalzero_end_times(items: list[_KanalZeroItem]) -> list[_KanalZeroItem]:
    out: list[_KanalZeroItem] = []
    for idx, item in enumerate(items):
        end_time = item.end_time
        if end_time is None and idx + 1 < len(items):
            end_time = items[idx + 1].start_time
        out.append(
            _KanalZeroItem(
                start_time=item.start_time,
                end_time=end_time,
                title=item.title,
                subtitle=item.subtitle,
                details_summary=item.details_summary,
                details_url=item.details_url,
            )
        )
    return out


def _looks_like_telemagazyn_challenge(html: str) -> bool:
    return "Just a moment..." in html and "componentsTvChannelTvGuide__item" not in html
