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

from programista_providers_radio.radiogdansk import parse_rg_ramowka_html  # noqa: E402


class TestRadioGdanskParsing(unittest.TestCase):
    def test_parses_weekday_variants_and_embedded_times(self) -> None:
        html = """
        <html><body>
          <div class="elementor-widget-heading"><p>program PONIEDZIAŁEK - PIĄTEK</p></div>
          <div class="elementor-widget-text-editor">
            <div class="elementor-widget-container">
              <p><strong>Autopilot</strong>: 05.59, 06.10</p>
              <p><strong>06.00-10.00 Dzień dobry Radio Gdańsk</strong></p>
              <p>
                07.20 pon. Segment A, wt. Segment B, śr. Segment C, czw. Segment D, pt. Segment E<br/>
                09.10 Strefa Publicystyki
              </p>
              <p>pon. Polityka<br/>wt. Biznes<br/>śr. Biznes<br/>czw. Biznes<br/>pt. Samorząd</p>
              <p>12.10 pon. Co mówią młodzi 12.20 Warto – nie warto, wt. Herbata, śr. Moje Radio, czw. Prawo, pt. Jedzenie</p>
            </div>
          </div>

          <div class="elementor-widget-heading"><p>program SOBOTA</p></div>
          <div class="elementor-widget-text-editor">
            <div class="elementor-widget-container">
              <p><strong>Wiadomości/Pogoda:</strong> 06.00, 06.30, 24.00</p>
              <p>05.30 Jestem z Pomorza</p>
            </div>
          </div>

          <div class="elementor-widget-heading"><p>program NIEDZIELA</p></div>
          <div class="elementor-widget-text-editor">
            <div class="elementor-widget-container">
              <p>06.00-09.00 Dzień dobry</p>
            </div>
          </div>
        </body></html>
        """

        parsed = parse_rg_ramowka_html(html).by_iso_weekday

        monday = parsed[1]
        tuesday = parsed[2]

        self.assertIn("Dzień dobry Radio Gdańsk", [p.title for p in monday])
        self.assertIn("Segment A", [p.title for p in monday])
        self.assertIn("Segment B", [p.title for p in tuesday])

        mon_0910 = next(p for p in monday if p.start == datetime.time(9, 10))
        self.assertEqual(mon_0910.title, "Polityka")
        self.assertEqual(mon_0910.details, "Strefa Publicystyki")

        mon_1210 = next(p for p in monday if p.start == datetime.time(12, 10))
        self.assertEqual(mon_1210.title, "Co mówią młodzi")

        mon_1220 = next(p for p in monday if p.start == datetime.time(12, 20))
        self.assertEqual(mon_1220.title, "Warto – nie warto")

        self.assertFalse(any(p.start == datetime.time(12, 20) for p in tuesday))

        saturday = parsed[6]
        self.assertEqual(next(p for p in saturday if p.start == datetime.time(5, 30)).title, "Jestem z Pomorza")

        sunday = parsed[7]
        self.assertEqual(next(p for p in sunday if p.start == datetime.time(6, 0)).title, "Dzień dobry")


if __name__ == "__main__":
    unittest.main()

