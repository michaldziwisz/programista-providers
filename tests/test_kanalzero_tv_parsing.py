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

from programista_providers_tv.kanalzero import (  # noqa: E402
    KanalZeroProvider,
    parse_kanalzero_schedule_page,
)


SAMPLE_HTML = """
<html><body>
  <main>
    <ul class="componentsTvChannelTvGuide__daytime">
      <li class="componentsTvChannelTvGuide__item componentsTvChannelTvGuide__item--dynamic">
        <div class="atomsTvChannelEmissionTile">
          <a class="atomsTvChannelEmissionTile__tileTag atomsTvChannelEmissionTile__tileLink"
             href="/gospodarcze-zero/pr/1464927">
            <h2 class="atomsTvChannelEmissionTile__title atomsTileTitle__title">
              Gospodarcze Zero
            </h2>
            <p class="atomsTvChannelEmissionTile__episodeSeasonCategory">
              <span>Odcinek <span>4</span></span>
              <span>Magazyn ekonomiczny</span>
            </p>
            <div class="atomsTvChannelEmissionTile__lead">
              Znany <strong>komentator</strong> gospodarczy.
            </div>
            <time class="atomsTvChannelEmissionTile__emissionStartDate"
                  data-time="2026-05-22T00:30:00+02:00"
                  data-endtime="2026-05-22T06:00:00+02:00"
                  datetime="00:30">
              00:30
            </time>
          </a>
        </div>
      </li>
      <li class="componentsTvChannelTvGuide__item componentsTvChannelTvGuide__item--dynamic">
        <div class="atomsTvChannelEmissionTile">
          <a class="atomsTvChannelEmissionTile__tileTag atomsTvChannelEmissionTile__tileLink"
             href="https://telemagazyn.pl/godzina-zero/pr/1464923">
            <h2 class="atomsTvChannelEmissionTile__title atomsTileTitle__title">
              Godzina Zero
            </h2>
            <p class="atomsTvChannelEmissionTile__episodeSeasonCategory">
              <span>Odcinek <span>1</span></span>
              <span>Sezon <span>1</span></span>
              <span>Magazyn</span>
            </p>
            <div class="atomsTvChannelEmissionTile__lead">
              Podczas transmisji na żywo prowadzący omawiają wydarzenia.
            </div>
            <time class="atomsTvChannelEmissionTile__emissionStartDate"
                  data-time="2026-05-22T06:00:00+02:00"
                  datetime="06:00">
              06:00
            </time>
            <div class="atomsTvChannelEmissionTile__labelContainer">
              <div class="atomsPartialLabelLabelFill">Na żywo</div>
            </div>
          </a>
        </div>
      </li>
      <li class="componentsTvChannelTvGuide__item componentsTvChannelTvGuide__item--dynamic">
        <div class="atomsTvChannelEmissionTile">
          <a class="atomsTvChannelEmissionTile__tileTag atomsTvChannelEmissionTile__tileLink"
             href="/poranek-zero/pr/1470089">
            <h2 class="atomsTvChannelEmissionTile__title atomsTileTitle__title">
              Poranek Zero
            </h2>
            <time class="atomsTvChannelEmissionTile__emissionStartDate" datetime="08:05">
              08:05
            </time>
          </a>
        </div>
      </li>
    </ul>
  </main>
</body></html>
"""

CLOUDFLARE_HTML = """
<!DOCTYPE html>
<html lang="en-US">
  <head><title>Just a moment...</title></head>
  <body>Checking your browser before accessing telemagazyn.pl</body>
</html>
"""

SAMPLE_JINA_MARKDOWN = """
Title: Kanał Zero - Program TV na 22.05.2026

URL Source: https://telemagazyn.pl/stacje/kanal-zero?dzien=2026-05-22

Markdown Content:

# Kanał Zero - Program TV na 22.05.2026 | Telemagazyn

[Archiwum](https://telemagazyn.pl/stacje/kanal-zero/archiwum)

*   ## [Gospodarcze Zero Odcinek 4 Magazyn ekonomiczny Znany komentator gospodarczy. 00:30](https://telemagazyn.pl/gospodarcze-zero/pr/1464927)

*   ## [Godzina Zero Odcinek 1 Sezon 1 Magazyn Podczas transmisji na żywo prowadzący omawiają wydarzenia. 06:20 Na żywo](https://telemagazyn.pl/godzina-zero/pr/1464923)

*   ## [Zero ściemy Odcinek 81 Lifestyle Program obala mity i stereotypy. 22:05](https://telemagazyn.pl/zero-sciemy/pr/1464967)

*   ## [Lista stacji](https://telemagazyn.pl/stacje)
"""


class _FakeHttpClient:
    def __init__(self, html: str, reader_text: str | None = None) -> None:
        self._html = html
        self._reader_text = reader_text
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def get_text(self, *args, **kwargs) -> str:
        self.calls.append((args, kwargs))
        if args and str(args[0]).startswith("https://r.jina.ai/http://"):
            return self._reader_text if self._reader_text is not None else self._html
        return self._html


class TestKanalZeroTvParsing(unittest.TestCase):
    def test_parses_schedule_items_and_cleans_html_descriptions(self) -> None:
        parsed = parse_kanalzero_schedule_page(SAMPLE_HTML)

        self.assertEqual([item.title for item in parsed], ["Gospodarcze Zero", "Godzina Zero", "Poranek Zero"])
        self.assertEqual(parsed[0].start_time, time(0, 30))
        self.assertEqual(parsed[0].end_time, time(6, 0))
        self.assertEqual(parsed[0].subtitle, "Odcinek 4 Magazyn ekonomiczny")
        self.assertEqual(
            parsed[0].details_summary,
            "Odcinek 4 Magazyn ekonomiczny\nZnany komentator gospodarczy.",
        )
        self.assertEqual(parsed[0].details_url, "https://telemagazyn.pl/gospodarcze-zero/pr/1464927")

        self.assertEqual(parsed[1].end_time, time(8, 5))
        self.assertEqual(parsed[1].subtitle, "Na żywo | Odcinek 1 Sezon 1 Magazyn")
        self.assertEqual(
            parsed[1].details_summary,
            "Na żywo | Odcinek 1 Sezon 1 Magazyn\n"
            "Podczas transmisji na żywo prowadzący omawiają wydarzenia.",
        )
        self.assertIsNone(parsed[2].end_time)

    def test_parses_jina_reader_markdown_when_telemagazyn_html_is_unavailable(self) -> None:
        parsed = parse_kanalzero_schedule_page(SAMPLE_JINA_MARKDOWN)

        self.assertEqual([item.title for item in parsed], ["Gospodarcze Zero", "Godzina Zero", "Zero ściemy"])
        self.assertEqual(parsed[0].start_time, time(0, 30))
        self.assertEqual(parsed[0].end_time, time(6, 20))
        self.assertEqual(parsed[0].subtitle, "")
        self.assertEqual(parsed[0].details_summary, "Odcinek 4 Magazyn ekonomiczny Znany komentator gospodarczy.")

        self.assertEqual(parsed[1].subtitle, "Na żywo")
        self.assertEqual(
            parsed[1].details_summary,
            "Na żywo\nOdcinek 1 Sezon 1 Magazyn Podczas transmisji na żywo prowadzący omawiają wydarzenia.",
        )
        self.assertEqual(parsed[1].end_time, time(22, 5))
        self.assertEqual(parsed[2].details_url, "https://telemagazyn.pl/zero-sciemy/pr/1464967")

    def test_provider_uses_telemagazyn_day_url(self) -> None:
        http = _FakeHttpClient(SAMPLE_HTML)
        provider = KanalZeroProvider(http)
        source = provider.list_sources()[0]

        items = provider.get_schedule(source, date(2026, 5, 22))

        self.assertEqual(items[0].title, "Gospodarcze Zero")
        self.assertEqual(items[0].details_ref, "https://telemagazyn.pl/gospodarcze-zero/pr/1464927")
        self.assertEqual(items[0].details_summary, "Odcinek 4 Magazyn ekonomiczny\nZnany komentator gospodarczy.")
        self.assertEqual(http.calls[0][0][0], "https://telemagazyn.pl/stacje/kanal-zero?dzien=2026-05-22")
        self.assertEqual(http.calls[0][1]["cache_key"], "kanalzero:telemagazyn:2026-05-22")

    def test_provider_falls_back_to_jina_reader_after_cloudflare_challenge(self) -> None:
        http = _FakeHttpClient(CLOUDFLARE_HTML, SAMPLE_JINA_MARKDOWN)
        provider = KanalZeroProvider(http)
        source = provider.list_sources()[0]

        items = provider.get_schedule(source, date(2026, 5, 22))

        self.assertEqual([item.title for item in items], ["Gospodarcze Zero", "Godzina Zero", "Zero ściemy"])
        self.assertEqual(
            http.calls[1][0][0],
            "https://r.jina.ai/http://https://telemagazyn.pl/stacje/kanal-zero?dzien=2026-05-22",
        )
        self.assertEqual(http.calls[1][1]["cache_key"], "kanalzero:jina:2026-05-22")


if __name__ == "__main__":
    unittest.main()
