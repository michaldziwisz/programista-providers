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

from programista_providers_radio.rmfclassic import (  # noqa: E402
    parse_rmfclassic_programme_details_html,
    parse_rmfclassic_ramowka_html,
)


class TestRmfClassicParsing(unittest.TestCase):
    def test_parses_schedule_rows_with_subitems(self) -> None:
        html = """
        <html><body>
          <div class="row py-2">
            <div class="col-2 pe-0"><span class="s-badge silver fss">07:00</span></div>
            <div class="col pt-1 ps-4">
              <b><a href="/program/Sniadanie-Mistrzow,589.html">Śniadanie Mistrzów</a></b>
              <div class="mt-0"><span class="text-muted">zaprasza: </span><a href="/radio/ludzie/Lukasz.html">Łukasz</a></div>
              <div class="subitems mt-1">
                <ul class="list-unstyled mb-0">
                  <li class="py-1">
                    <span class="s-badge silver fss me-2">07:10</span>
                    <b><a href="/program/Datownik,592.html">Datownik</a></b>
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <div class="row py-2">
            <div class="col-2 pe-0"><span class="s-badge silver fss">10:00</span></div>
            <div class="col pt-1 ps-4">
              <b><a href="/program/Co-by-bylo-gdyby,943.html">Co by było, gdyby…?</a></b>
            </div>
          </div>
        </body></html>
        """

        items = parse_rmfclassic_ramowka_html(html)
        self.assertEqual([i.start for i in items], [datetime.time(7, 0), datetime.time(7, 10), datetime.time(10, 0)])

        self.assertEqual(items[0].title, "Śniadanie Mistrzów")
        self.assertEqual(items[0].details_ref, "/program/Sniadanie-Mistrzow,589.html")
        self.assertEqual(items[0].details, "Zaprasza: Łukasz")

        self.assertEqual(items[1].title, "Datownik")
        self.assertEqual(items[1].details_ref, "/program/Datownik,592.html")
        self.assertIn("W ramach: Śniadanie Mistrzów", items[1].details)
        self.assertIn("Zaprasza: Łukasz", items[1].details)

        self.assertEqual(items[2].title, "Co by było, gdyby…?")

    def test_parses_programme_details(self) -> None:
        html = """
        <html><head><meta name="description" content="fallback"/></head><body>
          <div class="content">
            <p class="content-lead">Lead\\nline</p>
            <p>Body</p>
            <p> </p>
          </div>
        </body></html>
        """
        details = parse_rmfclassic_programme_details_html(html)
        self.assertEqual(details, "Lead\\nline\n\nBody")


if __name__ == "__main__":
    unittest.main()
