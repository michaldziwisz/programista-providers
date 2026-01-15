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

from programista_providers_radio.radiozachod import parse_rz_ramowka_html  # noqa: E402


class TestRadioZachodParsing(unittest.TestCase):
    def test_parses_only_newshift_entries_for_given_day(self) -> None:
        html = """
        <html><body>
          <table id="master-program-schedule">
            <tr class="master-program-hour-row hour-row-0">
              <td class="show-info day-3 thursday date-2026-01-15 overflow 1-shifts">
                <div class="show-wrap">
                  <div class="master-show-entry show-id-1 foo overflow newshift">
                    <div class="show-title"><a href="https://zachod.pl/show/foo/">Foo</a></div>
                    <div class="show-time">
                      <span class="rs-time rs-start-time" data-format="H:i">00:00</span>
                      <span class="rs-sep"> - </span>
                      <span class="rs-time rs-end-time" data-format="H:i">02:00</span>
                    </div>
                  </div>
                </div>
              </td>
              <td class="show-info day-4 friday date-2026-01-16 overflow 1-shifts">
                <div class="show-wrap">
                  <div class="master-show-entry show-id-2 bar overflow newshift">
                    <div class="show-title"><a href="https://zachod.pl/show/bar/">Bar</a></div>
                    <div class="show-time">
                      <span class="rs-time rs-start-time" data-format="H:i">00:00</span>
                      <span class="rs-sep"> - </span>
                      <span class="rs-time rs-end-time" data-format="H:i">01:00</span>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
            <tr class="master-program-hour-row hour-row-1">
              <td class="show-info day-3 thursday date-2026-01-15 continued 1-shifts">
                <div class="show-wrap">
                  <div class="master-show-entry show-id-1 foo continued">
                    <span class="rs-time rs-start-time" data="1"></span>
                    <span class="rs-time rs-end-time" data="2"></span>
                  </div>
                </div>
              </td>
            </tr>
          </table>
        </body></html>
        """

        items = parse_rz_ramowka_html(html, datetime.date(2026, 1, 15))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Foo")
        self.assertEqual(items[0].start, datetime.time(0, 0))
        self.assertEqual(items[0].end, datetime.time(2, 0))


if __name__ == "__main__":
    unittest.main()

