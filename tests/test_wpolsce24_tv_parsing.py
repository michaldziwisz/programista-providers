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

from programista_providers_tv.wpolsce24 import (  # noqa: E402
    Wpolsce24Provider,
    parse_wpolsce24_schedule_page,
)


SAMPLE_HTML = """
<html><body>
  <div class="description">
    <details>
      <summary>PONIEDZIAŁEK-PIĄTEK ▼</summary>
      <div>
        <div>
          <div class="pr">
            <div class="pt">06:50</div>
            <div class="pi">
              <div>⛅ Pogoda</div>
              <div>Prognoza pogody</div>
            </div>
            <a href="https://wpolsce24.tv/video">NA ŻYWO</a>
          </div>
          <div class="pr">
            <div class="pt">07:00</div>
            <div class="pi">
              <div>Wiadomości</div>
              <div>Program informacyjny</div>
            </div>
          </div>
          <div class="pr">
            <div class="pt">23:20</div>
            <div class="pi">
              <div>Wiadomości</div>
              <div>Program informacyjny</div>
            </div>
          </div>
          <div class="pr">
            <div class="pt">00:00</div>
            <div class="pi">
              <div>Film</div>
              <div>Blok filmowy</div>
            </div>
          </div>
        </div>
      </div>
    </details>
    <details>
      <summary>SOBOTA ▼</summary>
      <div>
        <div class="pr">
          <div class="pt">20:55</div>
          <div class="pi">
            <div>MAGAZYN Anity Gargas</div>
            <div>NOWOŚĆ</div>
            <div>Dziennikarstwo śledcze. Reportaże, analizy, wywiady.</div>
          </div>
        </div>
        <div class="pr">
          <div class="pt">21:45</div>
          <div class="pi">
            <div>Polityka na deser</div>
            <div>Program publicystyczno-satyryczny</div>
          </div>
        </div>
      </div>
    </details>
    <details>
      <summary>NIEDZIELA ▼</summary>
      <div>
        <div class="pr">
          <div class="pt">10:00</div>
          <div class="pi">
            <div>Studio Magdaleny Ogórek</div>
            <div>Dyskusje o najważniejszych wydarzeniach</div>
          </div>
        </div>
      </div>
    </details>
  </div>
</body></html>
"""

SAMPLE_TIMELINE_HTML = """
<html><body>
  <details>
    <summary class="section-title">Poniedziałek – Piątek <span>▼</span></summary>
    <div>
      <div style="display: flex;">
        <div class="time-col"><span>06:00</span></div>
        <div class="dot-col"></div>
        <div class="content-col">
          <div>
            <div class="title-text">Wiadomości Poranne</div>
            <a href="https://wpolsce24.tv/video">na żywo</a>
          </div>
          <div class="desc-text">Program informacyjny</div>
          <span>informacje</span>
        </div>
      </div>
      <div style="display: flex;">
        <div class="time-col"><span>06:15</span></div>
        <div class="dot-col"></div>
        <div class="content-col">
          <div>
            <div class="title-text">Wiadomości Agro</div>
          </div>
          <div class="desc-text">Program informacyjny (N)</div>
        </div>
      </div>
    </div>
  </details>
</body></html>
"""


class _FakeHttpClient:
    def __init__(self, html: str) -> None:
        self._html = html

    def get_text(self, *_args, **_kwargs) -> str:
        return self._html


class TestWpolsce24TvParsing(unittest.TestCase):
    def test_parses_schedule_groups_and_end_times(self) -> None:
        parsed = parse_wpolsce24_schedule_page(SAMPLE_HTML)

        weekday = parsed["weekday"]
        self.assertEqual([item.title for item in weekday], ["Pogoda", "Wiadomości", "Wiadomości", "Film"])
        self.assertEqual(weekday[0].description, "Prognoza pogody")
        self.assertEqual(weekday[0].end_time, time(7, 0))
        self.assertEqual(weekday[2].end_time, time(0, 0))
        self.assertIsNone(weekday[3].end_time)

        saturday = parsed["saturday"]
        self.assertEqual(saturday[0].title, "MAGAZYN Anity Gargas")
        self.assertEqual(
            saturday[0].description,
            "NOWOŚĆ\nDziennikarstwo śledcze. Reportaże, analizy, wywiady.",
        )

        sunday = parsed["sunday"]
        self.assertEqual(sunday[0].title, "Studio Magdaleny Ogórek")

    def test_parses_current_timeline_layout(self) -> None:
        parsed = parse_wpolsce24_schedule_page(SAMPLE_TIMELINE_HTML)

        weekday = parsed["weekday"]
        self.assertEqual([item.title for item in weekday], ["Wiadomości Poranne", "Wiadomości Agro"])
        self.assertEqual(weekday[0].description, "Program informacyjny")
        self.assertEqual(weekday[0].end_time, time(6, 15))
        self.assertIsNone(weekday[1].end_time)

    def test_provider_selects_section_by_day_of_week(self) -> None:
        provider = Wpolsce24Provider(_FakeHttpClient(SAMPLE_HTML))
        source = provider.list_sources()[0]

        saturday_items = provider.get_schedule(source, date(2026, 3, 28))
        self.assertEqual([item.title for item in saturday_items], ["MAGAZYN Anity Gargas", "Polityka na deser"])

        sunday_items = provider.get_schedule(source, date(2026, 3, 29))
        self.assertEqual([item.title for item in sunday_items], ["Studio Magdaleny Ogórek"])

        monday_items = provider.get_schedule(source, date(2026, 3, 30))
        self.assertEqual([item.title for item in monday_items], ["Pogoda", "Wiadomości", "Wiadomości", "Film"])


if __name__ == "__main__":
    unittest.main()
