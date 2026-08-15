import json
import re
import sys
import types
import unittest
from datetime import date, datetime, time, timedelta


def _install_tvguide_app_stubs() -> None:
    tvguide_app = sys.modules.get("tvguide_app") or types.ModuleType("tvguide_app")
    core = sys.modules.get("tvguide_app.core") or types.ModuleType("tvguide_app.core")
    util = sys.modules.get("tvguide_app.core.util") or types.ModuleType("tvguide_app.core.util")

    import html as html_module

    def clean_text(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", html_module.unescape(str(text))).strip()

    def clean_multiline_text(text: str) -> str:
        if not text:
            return ""
        text = html_module.unescape(str(text))
        lines: list[str] = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line:
                lines.append(line)
        return "\n".join(lines)

    def parse_time_hhmm(text: str) -> time | None:
        match = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*$", text or "")
        if not match:
            return None
        return time(hour=int(match.group(1)), minute=int(match.group(2)))

    util.clean_text = clean_text
    util.clean_multiline_text = clean_multiline_text
    util.parse_time_hhmm = parse_time_hhmm

    http = sys.modules.get("tvguide_app.core.http") or types.ModuleType("tvguide_app.core.http")

    class HttpClient: ...

    http.HttpClient = HttpClient

    models = sys.modules.get("tvguide_app.core.models") or types.ModuleType(
        "tvguide_app.core.models"
    )

    class AccessibilityFeature(str): ...

    class ProviderId(str): ...

    class SourceId(str): ...

    class Source:
        def __init__(self, provider_id: ProviderId, id: SourceId, name: str) -> None:
            self.provider_id = provider_id
            self.id = id
            self.name = name

    class ScheduleItem:
        def __init__(
            self,
            provider_id: ProviderId,
            source: Source,
            day: date,
            start_time: time | None,
            end_time: time | None,
            title: str,
            subtitle: str | None,
            details_ref: str | None,
            details_summary: str | None,
            accessibility: tuple = (),
        ) -> None:
            self.provider_id = provider_id
            self.source = source
            self.day = day
            self.start_time = start_time
            self.end_time = end_time
            self.title = title
            self.subtitle = subtitle
            self.details_ref = details_ref
            self.details_summary = details_summary
            self.accessibility = accessibility

    models.AccessibilityFeature = AccessibilityFeature
    models.ProviderId = ProviderId
    models.SourceId = SourceId
    models.Source = Source
    models.ScheduleItem = ScheduleItem

    providers_base = sys.modules.get("tvguide_app.core.providers.base") or types.ModuleType(
        "tvguide_app.core.providers.base"
    )

    class ScheduleProvider: ...

    providers_base.ScheduleProvider = ScheduleProvider

    sys.modules["tvguide_app"] = tvguide_app
    sys.modules["tvguide_app.core"] = core
    sys.modules["tvguide_app.core.util"] = util
    sys.modules["tvguide_app.core.http"] = http
    sys.modules["tvguide_app.core.models"] = models
    sys.modules["tvguide_app.core.providers.base"] = providers_base


_install_tvguide_app_stubs()

from programista_providers_tv.polotv import (  # noqa: E402
    POLOTV_CHANNEL_LABEL,
    PoloTvProvider,
    parse_polotv_details_ref,
    parse_polotv_module,
    parse_polotv_more_entry,
)


def _ms(day: date, hour: int, minute: int = 0) -> int:
    return int(datetime.combine(day, time(hour=hour, minute=minute)).timestamp() * 1000)


def _cast(start_ms: int, end_ms: int, title: str, programme_id: str) -> str:
    return (
        '<li class="tv__cell tv__cell--2"><div class="tv__cellin">'
        f'<div class="tvcast tvcast--more" data-start="{start_ms}" data-end="{end_ms}"'
        ' data-category="0">'
        f'<span class="tvcast__title" title="{title}" data-id="{programme_id}">{title}</span>'
        '<div class="tvcast__labels">'
        '<span class="tvcast__label tvcast__label--hour">6:00</span>'
        '<div class="tvcast__progress"></div>'
        '</div></div></div></li>'
    )


def _module_html(
    day: date,
    *,
    channel: str = POLOTV_CHANNEL_LABEL,
    casts: list[str] | None = None,
) -> str:
    if casts is None:
        casts = [
            _cast(_ms(day, 6), _ms(day, 7), "Hit za hitem", "1001"),
            _cast(_ms(day, 7), _ms(day, 8), "Disco Gramy", "1002"),
            _cast(_ms(day, 23), _ms(day + timedelta(days=1), 1), "Disco Star", "1003"),
            _cast(
                _ms(day + timedelta(days=1), 1),
                _ms(day + timedelta(days=1), 6),
                "Disco i relax z Tomkiem Samborskim&nbsp;(88)",
                "1004",
            ),
        ]
    other_channel_cast = _cast(_ms(day, 6), _ms(day, 8), "Wydarzenia", "9001")
    return (
        "<html><body>"
        '<div class="tv__logo-wrap" id="tv_logo">'
        '<div class="tv__row tv__row--hours"></div>'
        f'<div class="tv__row" data-channel="{channel}"><ul class="tv__cells">'
        + "".join(casts)
        + "</ul></div>"
        '<div class="tv__row tv__row--bg" data-channel="Polsat"><ul class="tv__cells">'
        + other_channel_cast
        + "</ul></div>"
        "</div></body></html>"
    )


MORE_JSON = json.dumps(
    {
        "1001": [
            "Prow.: Tomasz Samborski.<hr>Największe hity disco polo,<br>"
            "które emitowane są w radiu.",
            "https://www.polotv.pl/image/mini/2409633.jpg",
            "",
            [],
        ],
        "1003": [
            "Reż.: Jan Kowalski.<hr>Muzyczne show.",
            "https://www.polotv.pl/image/mini/1.jpg",
            "",
            ["N", "JM", "N"],
        ],
        "1004": ["", "https://www.polotv.pl/image/mini/2.jpg", "", []],
    },
    ensure_ascii=False,
)


class _FakeHttpClient:
    def __init__(self, modules: dict[int, str], more: dict[int, str] | None = None) -> None:
        self._modules = modules
        self._more = more or {}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_text(self, url: str, **kwargs) -> str:
        self.calls.append((url, kwargs))
        match = re.search(r"/module/page(\d+)/", url)
        page = int(match.group(1)) if match else 0
        if "/tv-more/" in url:
            if page not in self._more:
                raise RuntimeError(f"brak zasobu more dla page{page}")
            return self._more[page]
        if page not in self._modules:
            raise RuntimeError(f"brak modułu page{page}")
        return self._modules[page]


class TestPoloTvParsing(unittest.TestCase):
    def test_parses_only_requested_channel_row(self) -> None:
        day = date(2026, 8, 15)
        parsed = parse_polotv_module(_module_html(day), channel=POLOTV_CHANNEL_LABEL)

        self.assertEqual(
            [item.title for item in parsed],
            [
                "Hit za hitem",
                "Disco Gramy",
                "Disco Star",
                "Disco i relax z Tomkiem Samborskim (88)",
            ],
        )
        self.assertNotIn("Wydarzenia", [item.title for item in parsed])
        self.assertEqual(parsed[0].start, datetime(2026, 8, 15, 6, 0))
        self.assertEqual(parsed[0].end, datetime(2026, 8, 15, 7, 0))
        self.assertEqual(parsed[0].programme_id, "1001")
        # Program przez północ ma datę startu poprzedniego dnia.
        self.assertEqual(parsed[2].start, datetime(2026, 8, 15, 23, 0))
        self.assertEqual(parsed[2].end, datetime(2026, 8, 16, 1, 0))

    def test_module_parser_deduplicates_repeated_cells(self) -> None:
        day = date(2026, 8, 15)
        cast = _cast(_ms(day, 6), _ms(day, 7), "Hit za hitem", "1001")
        parsed = parse_polotv_module(
            _module_html(day, casts=[cast, cast]), channel=POLOTV_CHANNEL_LABEL
        )
        self.assertEqual(len(parsed), 1)

    def test_provider_merges_previous_module_for_early_morning(self) -> None:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        http = _FakeHttpClient({1: _module_html(today), 2: _module_html(tomorrow)})
        provider = PoloTvProvider(http)
        source = provider.list_sources()[0]

        items = provider.get_schedule(source, tomorrow)

        titles = [item.title for item in items]
        # 01:00 pochodzi z modułu page1 (dzień poprzedni), reszta z page2.
        self.assertEqual(titles[0], "Disco i relax z Tomkiem Samborskim (88)")
        self.assertEqual(items[0].start_time, time(1, 0))
        self.assertEqual(items[0].end_time, time(6, 0))
        self.assertIn("Hit za hitem", titles)
        self.assertTrue(all(item.day == tomorrow for item in items))
        requested = [url for url, _ in http.calls]
        self.assertEqual(
            requested,
            [
                "https://www.polotv.pl/tv-html/module/page2/",
                "https://www.polotv.pl/tv-html/module/page1/",
            ],
        )

    def test_provider_deduplicates_overlap_between_two_modules(self) -> None:
        # Moduły sąsiednich dni mogą zwrócić ten sam program (inne data-id,
        # ta sama godzina i tytuł) w strefie nakładania się okien.
        today = date.today()
        tomorrow = today + timedelta(days=1)
        overlap_early = _cast(_ms(tomorrow, 1), _ms(tomorrow, 6), "Nocne disco", "1111")
        overlap_late = _cast(_ms(tomorrow, 1), _ms(tomorrow, 6), "Nocne disco", "2222")
        http = _FakeHttpClient(
            {
                1: _module_html(
                    today,
                    casts=[_cast(_ms(today, 6), _ms(today, 7), "Hit", "1"), overlap_early],
                ),
                2: _module_html(tomorrow, casts=[overlap_late]),
            }
        )
        provider = PoloTvProvider(http)
        source = provider.list_sources()[0]

        items = provider.get_schedule(source, tomorrow)

        self.assertEqual([item.title for item in items], ["Nocne disco"])
        self.assertEqual(items[0].start_time, time(1, 0))

    def test_provider_returns_only_requested_day(self) -> None:
        today = date.today()
        http = _FakeHttpClient({1: _module_html(today)})
        provider = PoloTvProvider(http)
        source = provider.list_sources()[0]

        items = provider.get_schedule(source, today)

        self.assertEqual(
            [item.title for item in items],
            ["Hit za hitem", "Disco Gramy", "Disco Star"],
        )
        self.assertTrue(all(item.day == today for item in items))
        self.assertEqual(items[-1].start_time, time(23, 0))
        self.assertEqual(items[-1].end_time, time(1, 0))

    def test_provider_lists_seven_days_and_single_source(self) -> None:
        http = _FakeHttpClient({})
        provider = PoloTvProvider(http)

        sources = provider.list_sources()
        self.assertEqual([str(s.id) for s in sources], ["polotv"])
        self.assertEqual([s.name for s in sources], ["Polo TV"])

        days = provider.list_days()
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0], date.today())
        self.assertEqual(days[-1], date.today() + timedelta(days=6))

    def test_provider_returns_empty_list_outside_available_window(self) -> None:
        http = _FakeHttpClient({})
        provider = PoloTvProvider(http)
        source = provider.list_sources()[0]

        self.assertEqual(provider.get_schedule(source, date.today() - timedelta(days=1)), [])
        self.assertEqual(provider.get_schedule(source, date.today() + timedelta(days=7)), [])
        self.assertEqual(http.calls, [])

    def test_provider_caches_day_between_calls(self) -> None:
        today = date.today()
        http = _FakeHttpClient({1: _module_html(today)})
        provider = PoloTvProvider(http)
        source = provider.list_sources()[0]

        provider.get_schedule(source, today)
        calls_after_first = len(http.calls)
        provider.get_schedule(source, today)

        self.assertEqual(len(http.calls), calls_after_first)

    def test_details_are_fetched_lazily_from_more_resource(self) -> None:
        today = date.today()
        http = _FakeHttpClient({1: _module_html(today)}, {1: MORE_JSON})
        provider = PoloTvProvider(http)
        source = provider.list_sources()[0]

        items = provider.get_schedule(source, today)
        # Ramówka nie pobiera opisów.
        self.assertTrue(all("/tv-more/" not in url for url, _ in http.calls))
        self.assertEqual(items[0].details_ref, "1|1001")
        self.assertIsNone(items[0].details_summary)

        text = provider.get_item_details(items[0])
        self.assertEqual(
            text,
            "Prow.: Tomasz Samborski.\nNajwiększe hity disco polo,\nktóre emitowane są w radiu.",
        )
        self.assertTrue(any("/tv-more/module/page1/" in url for url, _ in http.calls))

    def test_details_include_accessibility_features_deduplicated(self) -> None:
        today = date.today()
        http = _FakeHttpClient({1: _module_html(today)}, {1: MORE_JSON})
        provider = PoloTvProvider(http)
        source = provider.list_sources()[0]

        items = provider.get_schedule(source, today)
        disco_star = next(item for item in items if item.title == "Disco Star")

        text = provider.get_item_details(disco_star)
        self.assertEqual(
            text,
            "Udogodnienia: napisy, język migowy\nReż.: Jan Kowalski.\nMuzyczne show.",
        )

    def test_details_fall_back_to_title_when_description_missing_or_http_fails(self) -> None:
        today = date.today()
        http = _FakeHttpClient({1: _module_html(today)}, {1: MORE_JSON})
        provider = PoloTvProvider(http)
        source = provider.list_sources()[0]
        items = provider.get_schedule(source, today)

        # "Disco Gramy" nie ma wpisu w zasobie more -> zwracamy sam tytuł.
        missing = next(item for item in items if item.title == "Disco Gramy")
        self.assertEqual(provider.get_item_details(missing), "Disco Gramy")

        broken = _FakeHttpClient({1: _module_html(today)}, {})
        broken_provider = PoloTvProvider(broken)
        broken_items = broken_provider.get_schedule(source, today)
        self.assertEqual(broken_provider.get_item_details(broken_items[0]), "Hit za hitem")

    def test_details_ref_roundtrip_and_validation(self) -> None:
        self.assertEqual(parse_polotv_details_ref("3|123456"), (3, "123456"))
        self.assertIsNone(parse_polotv_details_ref(None))
        self.assertIsNone(parse_polotv_details_ref(""))
        self.assertIsNone(parse_polotv_details_ref("123456"))
        self.assertIsNone(parse_polotv_details_ref("0|123456"))
        self.assertIsNone(parse_polotv_details_ref("8|123456"))
        self.assertIsNone(parse_polotv_details_ref("x|123456"))
        self.assertIsNone(parse_polotv_details_ref("1|"))

    def test_more_entry_parser_handles_broken_payloads(self) -> None:
        self.assertIsNone(parse_polotv_more_entry("to nie json", "1001"))
        self.assertIsNone(parse_polotv_more_entry("[]", "1001"))
        self.assertIsNone(parse_polotv_more_entry(MORE_JSON, "brak-id"))
        self.assertIsNone(parse_polotv_more_entry(MORE_JSON, "1004"))
        parsed = parse_polotv_more_entry(MORE_JSON, "1003")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.accessibility, ("N", "JM"))

    def test_module_without_requested_channel_yields_nothing(self) -> None:
        day = date(2026, 8, 15)
        parsed = parse_polotv_module(
            _module_html(day, channel="Polsat Music HD"), channel=POLOTV_CHANNEL_LABEL
        )
        self.assertEqual(parsed, [])


if __name__ == "__main__":
    unittest.main()
