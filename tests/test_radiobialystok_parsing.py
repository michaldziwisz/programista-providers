import datetime
import re
import sys
import types
import unittest


def _install_tvguide_app_stubs() -> None:
    tvguide_app = sys.modules.get("tvguide_app") or types.ModuleType("tvguide_app")
    core = sys.modules.get("tvguide_app.core") or types.ModuleType("tvguide_app.core")
    util = sys.modules.get("tvguide_app.core.util") or types.ModuleType("tvguide_app.core.util")

    def clean_text(text: str) -> str:
        if text is None:
            return ""
        return re.sub(r"\s+", " ", str(text)).strip()

    def parse_time_hhmm(value: str) -> datetime.time:
        hh, mm = value.split(":", 1)
        return datetime.time(int(hh), int(mm))

    util.clean_text = clean_text
    util.parse_time_hhmm = parse_time_hhmm

    http = sys.modules.get("tvguide_app.core.http") or types.ModuleType("tvguide_app.core.http")

    class HttpClient: ...

    http.HttpClient = HttpClient

    models = sys.modules.get("tvguide_app.core.models") or types.ModuleType("tvguide_app.core.models")

    class ProviderId(str): ...

    class SourceId(str): ...

    class Source: ...

    class ScheduleItem: ...

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

from programista_providers_radio.radiobialystok import (  # noqa: E402
    RB_INDEX_URL,
    parse_rb_day_html,
    parse_rb_index_html,
)


class TestRadioBialystokParsing(unittest.TestCase):
    def test_parses_index_days(self) -> None:
        html = """
        <html><body>
          <h1 class="ti-blue">RAMÓWKA - 20 stycznia 2026</h1>
          <a href="/ramowka/index/d/19/m/01/y/2026">19</a>
          <a href="/ramowka/index/d/21/m/01/y/2026">21</a>
        </body></html>
        """
        parsed = parse_rb_index_html(html)
        self.assertIn(datetime.date(2026, 1, 19), parsed)
        self.assertIn(datetime.date(2026, 1, 20), parsed)
        self.assertIn(datetime.date(2026, 1, 21), parsed)
        self.assertEqual(parsed[datetime.date(2026, 1, 20)], RB_INDEX_URL)

    def test_parses_day_programmes(self) -> None:
        html = """
        <html><body>
          <div class="ram2f text-center"><span class="ram2data">20</span></div>
          <div class="ram2f"><span class="ram2data">stycznia</span></div>

          <div class="ram2f text-center"><span class="ram2data">00:00</span></div>
          <div class="ram2f">
            <span class="ram2data"><a href="/nocnaorkiestra/index">Nocna Orkiestra Radia Białystok</a></span>
            <button class="rambutton">Graliśmy</button>
          </div>

          <div id="btn123p">
            <span class="ram2data2date">00:04</span><span class="ram2data2"> - Foo</span><br>
          </div>

          <div class="ram2f text-center"><span class="ram2data">01:00</span></div>
          <div class="ram2f"><span class="ram2data">Wiadomości</span></div>
        </body></html>
        """
        parsed = parse_rb_day_html(html)
        self.assertEqual([p.title for p in parsed], ["Nocna Orkiestra Radia Białystok", "Wiadomości"])
        self.assertEqual(parsed[0].start, datetime.time(0, 0))
        self.assertEqual(parsed[1].start, datetime.time(1, 0))


if __name__ == "__main__":
    unittest.main()

