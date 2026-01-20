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

from programista_providers_radio.radiolublin import parse_rlublin_ramowka_html  # noqa: E402


class TestRadioLublinParsing(unittest.TestCase):
    def test_handles_rowspans_in_week_grid(self) -> None:
        html = """
        <table class="tt_timetable">
          <thead>
            <tr class="row_gray">
              <th></th>
              <th>Poniedziałek</th><th>Wtorek</th><th>Środa</th><th>Czwartek</th><th>Piątek</th><th>Sobota</th><th>Niedziela</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="tt_hours_column">00:00</td>
              <td class="event" rowspan="2">
                <div class="event_container">
                  <a class="event_header" href="/a">PonA</a>
                  <div class="hours_container"><span class="hours">00:00 - 01:00</span></div>
                </div>
              </td>
              <td class="event">
                <div class="event_container">
                  <a class="event_header" href="/b">WtB</a>
                  <div class="hours_container"><span class="hours">00:00 - 00:30</span></div>
                </div>
              </td>
              <td></td><td></td><td></td><td></td><td></td>
            </tr>
            <tr>
              <td class="tt_hours_column">00:30</td>
              <td class="event">
                <div class="event_container">
                  <a class="event_header" href="/c">WtC</a>
                  <div class="hours_container"><span class="hours">00:30 - 01:00</span></div>
                </div>
              </td>
              <td></td><td></td><td></td><td></td><td></td>
            </tr>
          </tbody>
        </table>
        """
        parsed = parse_rlublin_ramowka_html(html)
        monday = parsed[1]
        tuesday = parsed[2]

        self.assertEqual(len(monday), 1)
        self.assertEqual(monday[0].title, "PonA")
        self.assertEqual(monday[0].start, datetime.time(0, 0))
        self.assertEqual(monday[0].end, datetime.time(1, 0))

        self.assertEqual([p.title for p in tuesday], ["WtB", "WtC"])
        self.assertEqual(tuesday[0].start, datetime.time(0, 0))
        self.assertEqual(tuesday[1].start, datetime.time(0, 30))


if __name__ == "__main__":
    unittest.main()

