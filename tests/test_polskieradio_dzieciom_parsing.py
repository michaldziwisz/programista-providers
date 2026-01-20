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

    util.clean_text = clean_text
    util.clean_multiline_text = clean_multiline_text

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

from programista_providers_radio.polskieradio_dzieciom import (  # noqa: E402
    _build_prd_schedule_url,
    parse_prd_schedule_json,
)


class TestPolskieRadioDzieciomParsing(unittest.TestCase):
    def test_builds_selected_date_url(self) -> None:
        day = datetime.date(2026, 1, 19)
        url = _build_prd_schedule_url(day)
        self.assertIn("Program=11", url)
        self.assertIn("selectedDate=2026-01-19", url)

    def test_parses_schedule_json(self) -> None:
        json_text = """
        {
          "Schedule": [
            {
              "StartHour": "2026-01-20T07:00:00+01:00",
              "StopHour": "2026-01-20T09:00:00+01:00",
              "Title": "Poranek w Polskim Radiu Dzieciom",
              "Description": "Opis audycji",
              "Leaders": [{"Name": "Martyna", "SurName": "Chuderska"}],
              "Id": 10674
            }
          ]
        }
        """
        parsed = parse_prd_schedule_json(json_text)
        self.assertEqual(len(parsed), 1)
        item = parsed[0]
        self.assertEqual(item.start, datetime.time(7, 0))
        self.assertEqual(item.end, datetime.time(9, 0))
        self.assertEqual(item.title, "Poranek w Polskim Radiu Dzieciom")
        self.assertIn("Prowadzący: Martyna Chuderska", item.details)
        self.assertIn("Opis audycji", item.details)
        self.assertEqual(item.details_ref, "https://www.polskieradio.pl/18/Audycja/10674")


if __name__ == "__main__":
    unittest.main()

