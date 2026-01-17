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

    def parse_time_hhmm(value: str) -> datetime.time:
        hh, mm = value.split(":", 1)
        return datetime.time(int(hh), int(mm))

    util.clean_text = clean_text
    util.clean_multiline_text = clean_multiline_text
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

from programista_providers_radio.radiokielce import parse_rkielce_day_html, parse_rkielce_index_html  # noqa: E402


class TestRadioKielceParsing(unittest.TestCase):
    def test_parses_index_days(self) -> None:
        html = """
        <html><head>
          <script>var mecdata = {"current_year":"2026","current_month":"01"};</script>
        </head><body>
          <article class="mec-event-article mec-toggle-202601-123">
            <div class="mec-event-date"><div class="event-d mec-color">17</div></div>
            <h4 class="mec-event-title"><a href="/events/sobota-17-stycznia/">SOBOTA, 17 STYCZNIA</a></h4>
          </article>
        </body></html>
        """

        parsed = parse_rkielce_index_html(html)
        self.assertEqual(parsed[datetime.date(2026, 1, 17)], "https://radiokielce.pl/events/sobota-17-stycznia/")

    def test_parses_day_schedule(self) -> None:
        html = """
        <div class="mec-event-content">
          <div class="mec-single-event-description mec-events-content">
            <h5>
              godz. 0:00 Wiadomości<br/>
              godz. 6:05 Agroserwis<br/>
              godz. 6:20<br/>
            </h5>
          </div>
        </div>
        """

        programmes = parse_rkielce_day_html(html)
        self.assertEqual(len(programmes), 2)
        self.assertEqual(programmes[0].start, datetime.time(0, 0))
        self.assertEqual(programmes[0].title, "Wiadomości")
        self.assertEqual(programmes[1].start, datetime.time(6, 5))
        self.assertEqual(programmes[1].title, "Agroserwis")


if __name__ == "__main__":
    unittest.main()
