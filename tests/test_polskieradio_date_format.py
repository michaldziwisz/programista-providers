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

from programista_providers_radio.polskieradio import (  # noqa: E402
    PR_SCHEDULE_API_URL,
    _build_pr_schedule_url,
    parse_pr_schedule_json,
)


class TestPolskieRadioDateFormat(unittest.TestCase):
    def test_builds_selected_date_as_iso(self) -> None:
        day = datetime.date(2026, 1, 17)
        url = _build_pr_schedule_url("1", day)
        self.assertEqual(url, f"{PR_SCHEDULE_API_URL}?Program=1&selectedDate={day.isoformat()}")

    def test_parses_schedule_json_and_normalizes_urls(self) -> None:
        data = {
            "Schedule": [
                {
                    "AntenaId": 1,
                    "StartHour": "2026-01-17T01:00:00+01:00",
                    "StopHour": "2026-01-17T02:00:00+01:00",
                    "Title": "  Test  ",
                    "Description": "Opis\\nDrugia linia",
                    "ArticleLink": "//www.polskieradio.pl/7/5069/Artykul/123,Test",
                    "Leaders": [{"Name": "Jan", "SurName": "Kowalski"}, {"Name": "jan", "SurName": "kowalski"}],
                },
                {
                    "AntenaId": 1,
                    "StartHour": "2026-01-17T00:00:00+01:00",
                    "StopHour": "2026-01-17T01:00:00+01:00",
                    "Title": "First",
                    "Description": "",
                    "ArticleLink": "",
                    "Leaders": None,
                },
            ]
        }

        items = parse_pr_schedule_json(json.dumps(data, ensure_ascii=False))
        self.assertEqual([i.title for i in items], ["First", "Test"])

        self.assertEqual(items[0].start_time, datetime.time(0, 0))
        self.assertEqual(items[0].end_time, datetime.time(1, 0))
        self.assertIsNone(items[0].details_ref)
        self.assertEqual(items[0].details_summary, "")

        self.assertEqual(items[1].start_time, datetime.time(1, 0))
        self.assertEqual(items[1].end_time, datetime.time(2, 0))
        self.assertEqual(items[1].details_ref, "https://www.polskieradio.pl/7/5069/Artykul/123,Test")
        self.assertIn("Prowadzący: Jan Kowalski", items[1].details_summary)
        self.assertIn("Opis", items[1].details_summary)

    def test_returns_empty_on_invalid_json(self) -> None:
        self.assertEqual(parse_pr_schedule_json("{nope"), [])


if __name__ == "__main__":
    unittest.main()
