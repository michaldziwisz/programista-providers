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

    util.clean_text = clean_text

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

from programista_providers_radio.radiozet import parse_radiozet_schedule_json  # noqa: E402


class TestRadioZetParsing(unittest.TestCase):
    def test_parses_seconds_and_sorts_midnight(self) -> None:
        raw = [
            {
                "program": {"name": "Dzień Dobry Bardzo"},
                "people": [{"name": "Ala"}, {"name": "Olek"}],
                "start": 19800,
                "end": 28920,
            },
            {
                "program": {"name": "Fajna nocka"},
                "people": [{"name": "Jan Kowalski"}],
                "start": 86400,
                "end": 19800,
            },
        ]

        items = parse_radiozet_schedule_json(json.dumps(raw, ensure_ascii=False))
        self.assertEqual([i.start for i in items], [datetime.time(0, 0), datetime.time(5, 30)])
        self.assertEqual([i.end for i in items], [datetime.time(5, 30), datetime.time(8, 2)])
        self.assertEqual(items[0].title, "Fajna nocka")
        self.assertEqual(items[0].details, "Jan Kowalski")
        self.assertEqual(items[1].title, "Dzień Dobry Bardzo")
        self.assertEqual(items[1].details, "Ala, Olek")

    def test_returns_empty_on_invalid_json(self) -> None:
        self.assertEqual(parse_radiozet_schedule_json("{nope"), [])


if __name__ == "__main__":
    unittest.main()

