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

from programista_providers_radio.radioszczecin import parse_rs_program_html  # noqa: E402


class TestRadioSzczecinParsing(unittest.TestCase):
    def test_parses_programme_list(self) -> None:
        html = """
        <html><body>
          <div id="programdzien">
            <div class="audycja past" id="aud1">
              <a class="atytul" href="9,1,foo" name="1">
                <span class="toggle"></span>
                <span class="agodz">0:00</span>
                ROZMOWA POD KRAWATEM
              </a>
              <div class="ainfo"></div>
            </div>
            <div class="audycja" id="aud2">
              <a class="atytul" href="9,2,bar" name="2">
                <span class="agodz">17:30</span>
                ROZMOWY NIEUCZESANE
              </a>
            </div>
          </div>
        </body></html>
        """

        programmes = parse_rs_program_html(html)
        self.assertEqual(len(programmes), 2)
        self.assertEqual(programmes[0].start, datetime.time(0, 0))
        self.assertEqual(programmes[0].title, "ROZMOWA POD KRAWATEM")
        self.assertEqual(programmes[1].start, datetime.time(17, 30))
        self.assertEqual(programmes[1].title, "ROZMOWY NIEUCZESANE")

    def test_dedupes_by_start_and_title(self) -> None:
        html = """
        <html><body>
          <div id="programdzien">
            <div class="audycja"><a class="atytul"><span class="agodz">6:00</span>TEST</a></div>
            <div class="audycja"><a class="atytul"><span class="agodz">6:00</span>TEST</a></div>
          </div>
        </body></html>
        """
        programmes = parse_rs_program_html(html)
        self.assertEqual(len(programmes), 1)
        self.assertEqual(programmes[0].start, datetime.time(6, 0))
        self.assertEqual(programmes[0].title, "TEST")


if __name__ == "__main__":
    unittest.main()

