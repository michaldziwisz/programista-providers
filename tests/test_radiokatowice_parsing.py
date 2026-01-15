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

from programista_providers_radio.radiokatowice import (  # noqa: E402
    parse_rk_audycja_details_html,
    parse_rk_ramowka_html,
)


class TestRadioKatowiceParsing(unittest.TestCase):
    def test_parses_weekday_tabs_and_details(self) -> None:
        html = """
        <html><body>
          <div id="ex1-tabs-1">
            <h2><b>Poniedziałek</b></h2>
            <p class="m-0"><b>00:10</b> &nbsp;<b>Radio Katowice - każdej nocy!</b></p>
            <p class="m-0"><b>00:10</b> &nbsp;<a class="link_art" href="audycje,17,Lwowska-Fala.html">Lwowska Fala</a> - powtórka programu</p>
            <p class="m-0"><b>00:10</b> &nbsp;<a class="link_art" href="audycje,17,Lwowska-Fala.html">Lwowska Fala</a> - powtórka programu</p>
            <p class="m-0"><b>05:35</b> &nbsp;<a class="link_art" href="https://podcasty.radio.katowice.pl/category/u-progu-dnia/">U progu dnia</a></p>
          </div>
          <div id="ex1-tabs-2">
            <h2>Wtorek</h2>
            <p class="m-0"><b>09:00</b> &nbsp;<a class="link_art" href="audycje,1,Test.html">Test</a></p>
          </div>
        </body></html>
        """

        parsed = parse_rk_ramowka_html(html)

        monday = parsed.by_iso_weekday[1]
        self.assertEqual(len(monday), 3)
        self.assertEqual([p.start for p in monday], [datetime.time(0, 10), datetime.time(0, 10), datetime.time(5, 35)])

        self.assertEqual(monday[0].title, "Radio Katowice - każdej nocy!")
        self.assertIsNone(monday[0].details_ref)
        self.assertEqual(monday[0].details, "")

        self.assertEqual(monday[1].title, "Lwowska Fala")
        self.assertEqual(monday[1].details_ref, "audycje,17,Lwowska-Fala.html")
        self.assertEqual(monday[1].details, "powtórka programu")

        self.assertEqual(monday[2].title, "U progu dnia")
        self.assertIsNone(monday[2].details_ref)

        tuesday = parsed.by_iso_weekday[2]
        self.assertEqual(len(tuesday), 1)
        self.assertEqual(tuesday[0].title, "Test")
        self.assertEqual(tuesday[0].details_ref, "audycje,1,Test.html")

    def test_parses_audycja_details_from_first_paragraph(self) -> None:
        html = """
        <html><body>
          <div class="tytul_art">Lwowska Fala</div>
          <p><br></p>
          <p>Opis<br>line</p>
          <p><iframe src="https://example.com"></iframe></p>
        </body></html>
        """
        details = parse_rk_audycja_details_html(html)
        self.assertEqual(details, "Opis line")


if __name__ == "__main__":
    unittest.main()
