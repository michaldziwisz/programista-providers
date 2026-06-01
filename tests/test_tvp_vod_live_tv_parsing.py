import re
import sys
import types
import unittest
from datetime import date, time


def _install_tvguide_app_stubs() -> None:
    tvguide_app = sys.modules.get("tvguide_app") or types.ModuleType("tvguide_app")
    core = sys.modules.get("tvguide_app.core") or types.ModuleType("tvguide_app.core")
    util = sys.modules.get("tvguide_app.core.util") or types.ModuleType("tvguide_app.core.util")

    def clean_text(text: str) -> str:
        if text is None:
            return ""
        return re.sub(r"\s+", " ", str(text)).strip()

    def clean_multiline_text(text: str) -> str:
        if text is None:
            return ""
        s = str(text)
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in s.split("\n")]
        out: list[str] = []
        blank = False
        for line in lines:
            if not line:
                if out and not blank:
                    out.append("")
                blank = True
                continue
            out.append(line)
            blank = False
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out).strip()

    def parse_time_hhmm(text: str) -> time | None:
        if not text:
            return None
        match = re.fullmatch(r"(\d{2}):(\d{2})", text.strip())
        if not match:
            return None
        return time(hour=int(match.group(1)), minute=int(match.group(2)))

    util.clean_text = clean_text
    util.clean_multiline_text = clean_multiline_text
    util.parse_time_hhmm = parse_time_hhmm

    http = sys.modules.get("tvguide_app.core.http") or types.ModuleType("tvguide_app.core.http")

    class HttpClient: ...

    http.HttpClient = HttpClient

    models = sys.modules.get("tvguide_app.core.models") or types.ModuleType("tvguide_app.core.models")

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

import programista_providers_tv  # noqa: E402
from programista_providers_tv.tvp_vod_live import (  # noqa: E402
    TvpVodLiveProvider,
    parse_tvp_vod_live_programmes,
)


SAMPLE_JSON = """
[
  {
    "id": 1,
    "title": "Nocny koncert",
    "since": "2026-06-01T22:21:15+02:00",
    "till": "2026-06-02T00:04:25+02:00",
    "webUrl": "https://vod.tvp.pl/live/example,1",
    "lead": "<p>Program zaczęty poprzedniego dnia.</p>"
  },
  {
    "id": 2,
    "title": "Mieczysław Fogg - Siwy włos",
    "since": "2026-06-02T00:04:25+02:00",
    "till": "2026-06-02T00:07:10+02:00",
    "webUrl": "https://vod.tvp.pl/live/example,2"
  },
  {
    "id": 3,
    "title": "Koncert wieczorny",
    "since": "2026-06-02T23:30:00+02:00",
    "till": "2026-06-03T00:30:00+02:00",
    "description": "Pozycja kończąca się następnego dnia."
  },
  {
    "id": 4,
    "title": "Poza zakresem",
    "since": "2026-06-03T01:00:00+02:00",
    "till": "2026-06-03T02:00:00+02:00"
  }
]
"""


class _FakeHttpClient:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def get_text(self, *args, **kwargs) -> str:
        self.calls.append((args, kwargs))
        return self._text


class TestTvpVodLiveTvParsing(unittest.TestCase):
    def test_loader_prioritizes_single_channel_tv_providers_before_tvp_extra(self) -> None:
        providers = programista_providers_tv.load(_FakeHttpClient("{}"))
        provider_ids = [provider.provider_id for provider in providers]

        tvp_extra_idx = provider_ids.index("tvp-extra")
        self.assertLess(provider_ids.index("tvp-vod-live"), tvp_extra_idx)
        self.assertLess(provider_ids.index("wpolsce24"), tvp_extra_idx)
        self.assertLess(provider_ids.index("kanalzero"), tvp_extra_idx)

    def test_parses_programmes_and_clamps_items_to_requested_day(self) -> None:
        parsed = parse_tvp_vod_live_programmes(SAMPLE_JSON, date(2026, 6, 2))

        self.assertEqual([item.title for item in parsed], ["Nocny koncert", "Mieczysław Fogg - Siwy włos", "Koncert wieczorny"])
        self.assertEqual(parsed[0].start_time, time(0, 0))
        self.assertEqual(parsed[0].end_time, time(0, 4, 25))
        self.assertEqual(parsed[0].description, "Program zaczęty poprzedniego dnia.")
        self.assertEqual(parsed[0].details_url, "https://vod.tvp.pl/live/example,1")

        self.assertEqual(parsed[1].start_time, time(0, 4, 25))
        self.assertEqual(parsed[1].end_time, time(0, 7, 10))
        self.assertEqual(parsed[1].description, "")

        self.assertEqual(parsed[2].start_time, time(23, 30))
        self.assertEqual(parsed[2].end_time, time(0, 0))
        self.assertEqual(parsed[2].description, "Pozycja kończąca się następnego dnia.")

    def test_provider_builds_tvp_vod_api_url(self) -> None:
        http = _FakeHttpClient(SAMPLE_JSON)
        provider = TvpVodLiveProvider(http)
        source = provider.list_sources()[0]

        items = provider.get_schedule(source, date(2026, 6, 2))

        self.assertEqual(source.id, "tvp-muzyka-i-koncerty")
        self.assertEqual(source.name, "TVP Muzyka i Koncerty")
        self.assertEqual(items[0].title, "Nocny koncert")
        self.assertEqual(items[0].details_summary, "Program zaczęty poprzedniego dnia.")
        self.assertIn("https://vod.tvp.pl/api/products/lives/programmes?", http.calls[0][0][0])
        self.assertIn("platform=BROWSER", http.calls[0][0][0])
        self.assertIn("since=2026-06-02T00%3A00%2B0200", http.calls[0][0][0])
        self.assertIn("till=2026-06-03T00%3A00%2B0200", http.calls[0][0][0])
        self.assertIn("liveId%5B%5D=2999109", http.calls[0][0][0])
        self.assertEqual(http.calls[0][1]["cache_key"], "tvp-vod-live:2999109:2026-06-02")

    def test_provider_builds_winter_tvp_vod_api_url(self) -> None:
        http = _FakeHttpClient("[]")
        provider = TvpVodLiveProvider(http)
        source = provider.list_sources()[0]

        provider.get_schedule(source, date(2026, 1, 5))

        self.assertIn("since=2026-01-05T00%3A00%2B0100", http.calls[0][0][0])
        self.assertIn("till=2026-01-06T00%3A00%2B0100", http.calls[0][0][0])

    def test_parses_utc_programme_times_as_warsaw_time(self) -> None:
        parsed = parse_tvp_vod_live_programmes(
            """
            [
              {
                "title": "Koncert",
                "since": "2026-01-05T12:00:00+00:00",
                "till": "2026-01-05T13:30:00+00:00"
              }
            ]
            """,
            date(2026, 1, 5),
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].start_time, time(13, 0))
        self.assertEqual(parsed[0].end_time, time(14, 30))


if __name__ == "__main__":
    unittest.main()
