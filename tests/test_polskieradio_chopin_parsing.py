import datetime
import json
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

from programista_providers_radio.polskieradio_chopin import parse_pr_chopin_ramowka_html  # noqa: E402


class TestPolskieRadioChopinParsing(unittest.TestCase):
    def test_parses_next_data_schedule(self) -> None:
        next_data = {
            "props": {
                "pageProps": {
                    "scheduleData": [
                        {
                            "title": "Laureaci\nChopina",
                            "startTime": "08:00:00",
                            "stopTime": "09:30:00",
                            "lead": "Lead",
                            "description": "Desc",
                            "currentDescription": "",
                            "hosts": [{"name": "Jan", "surname": "Kowalski"}],
                        },
                        {
                            "title": "Koncert",
                            "startTime": "09:30:00",
                            "stopTime": "10:00:00",
                            "lead": None,
                            "description": "Opis\\n\\n  z  \\t tabami",
                            "currentDescription": "Opis",
                            "hosts": [],
                        },
                    ]
                }
            }
        }
        html = (
            "<html><head></head><body>"
            f'<script id=\"__NEXT_DATA__\" type=\"application/json\">{json.dumps(next_data)}</script>'
            "</body></html>"
        )

        items = parse_pr_chopin_ramowka_html(html)
        self.assertEqual(len(items), 2)

        self.assertEqual(items[0].start, datetime.time(8, 0))
        self.assertEqual(items[0].end, datetime.time(9, 30))
        self.assertEqual(items[0].title, "Laureaci Chopina")
        self.assertIn("Prowadzą: Jan Kowalski", items[0].details)
        self.assertIn("Lead", items[0].details)
        self.assertIn("Desc", items[0].details)

        self.assertEqual(items[1].start, datetime.time(9, 30))
        self.assertEqual(items[1].end, datetime.time(10, 0))
        self.assertEqual(items[1].title, "Koncert")
        self.assertEqual(items[1].details, "Opis")


if __name__ == "__main__":
    unittest.main()
