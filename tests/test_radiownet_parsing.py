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

    class Source:
        def __init__(self, provider_id: ProviderId, id: SourceId, name: str) -> None:
            self.provider_id = provider_id
            self.id = id
            self.name = name

    class ScheduleItem:
        def __init__(
            self,
            provider_id: ProviderId,
            source: Source,
            day: datetime.date,
            start_time: datetime.time | None,
            end_time: datetime.time | None,
            title: str,
            subtitle: str | None,
            details_ref: str | None,
            details_summary: str | None,
        ) -> None:
            self.provider_id = provider_id
            self.source = source
            self.day = day
            self.start_time = start_time
            self.end_time = end_time
            self.title = title
            self.subtitle = subtitle
            self.details_ref = details_ref
            self.details_summary = details_summary

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

sys.modules.pop("programista_providers_radio.radiownet", None)
sys.modules.pop("programista_providers_radio", None)

from programista_providers_radio.radiownet import (  # noqa: E402
    RadioWnetProvider,
    extract_radiownet_all_slots_json,
    parse_radiownet_schedule_html,
)


def _build_radiownet_html(slots: list[dict]) -> str:
    slots_json = json.dumps(slots, ensure_ascii=False).replace("\\", "\\\\").replace('"', '\\"')
    return f'<script>self.__next_f.push([1,"abc \\"allSlots\\":{slots_json}"])</script>'


class _FakeHttpClient:
    def __init__(self, html: str) -> None:
        self._html = html

    def get_text(self, *_args, **_kwargs) -> str:
        return self._html


class TestRadioWnetParsing(unittest.TestCase):
    def test_extracts_slots_json_and_parses_details(self) -> None:
        html = _build_radiownet_html(
            [
                {
                    "day_of_week": "monday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "time_range": "06:00 - 07:00",
                    "audycja": {
                        "title": "MiŚ",
                        "excerpt": "Krótki zajawkowy opis...",
                        "hosts": [{"name": "MiŚ"}, {"name": "MiŚ"}],
                        "content": "Miś &#8211; czyli miłość i śpiew\n\n&nbsp;Pełny opis.",
                    },
                },
                {
                    "day_of_week": "monday",
                    "start_time": "07:07",
                    "end_time": "09:00",
                    "time_range": "07:07 - 09:00",
                    "audycja": {
                        "title": "Poranek Wnet",
                        "excerpt": "Codzienne pasmo...",
                        "hosts": [{"name": "Krzysztof Skowroński"}, {"name": "Jaśmina Nowak"}],
                        "content": "Pełny opis poranka.",
                    },
                },
                {
                    "day_of_week": "saturday",
                    "start_time": "10:07",
                    "end_time": "11:00",
                    "time_range": "10:07 - 11:00",
                    "audycja": {
                        "title": "Program Wschodni",
                        "excerpt": "Cotygodniowy audycja publicystyczna...",
                        "hosts": [{"name": "Wojciech Jankowski"}, {"name": "Paweł Bobołowicz"}],
                        "content": "",
                    },
                },
            ]
        )

        raw_json = extract_radiownet_all_slots_json(html)
        decoded_raw = json.loads(raw_json)
        self.assertEqual(decoded_raw[0]["day_of_week"], "monday")

        parsed = parse_radiownet_schedule_html(html)
        monday = parsed[0]
        self.assertEqual(monday[0].start, datetime.time(6, 0))
        self.assertEqual(monday[0].end, datetime.time(7, 0))
        self.assertEqual(monday[0].title, "MiŚ")
        self.assertEqual(
            monday[0].details,
            "Prowadzący: MiŚ\n\nMiś – czyli miłość i śpiew\n\nPełny opis.",
        )
        self.assertEqual(
            monday[1].details,
            "Prowadzący: Krzysztof Skowroński, Jaśmina Nowak\n\nPełny opis poranka.",
        )

        saturday = parsed[5]
        self.assertEqual(saturday[0].title, "Program Wschodni")
        self.assertEqual(
            saturday[0].details,
            "Prowadzący: Wojciech Jankowski, Paweł Bobołowicz\n\nCotygodniowy audycja publicystyczna...",
        )

    def test_provider_maps_calendar_day_to_weekday_schedule(self) -> None:
        html = _build_radiownet_html(
            [
                {
                    "day_of_week": "saturday",
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "time_range": "08:00 - 10:00",
                    "audycja": {
                        "title": "Sobotni program",
                        "excerpt": "",
                        "hosts": [{"name": "Konrad Mędrzecki"}],
                        "content": "Opis sobotni.",
                    },
                },
                {
                    "day_of_week": "sunday",
                    "start_time": "09:00",
                    "end_time": "11:00",
                    "time_range": "09:00 - 11:00",
                    "audycja": {
                        "title": "Niedzielny program",
                        "excerpt": "",
                        "hosts": [{"name": "Iza Smolarek i Alex Sławiński"}],
                        "content": "Opis niedzielny.",
                    },
                },
            ]
        )

        provider = RadioWnetProvider(_FakeHttpClient(html))
        source = provider.list_sources()[0]

        saturday_items = provider.get_schedule(source, datetime.date(2026, 3, 28))
        self.assertEqual([item.title for item in saturday_items], ["Sobotni program"])
        self.assertEqual(saturday_items[0].start_time, datetime.time(8, 0))

        sunday_items = provider.get_schedule(source, datetime.date(2026, 3, 29))
        self.assertEqual([item.title for item in sunday_items], ["Niedzielny program"])
        self.assertEqual(sunday_items[0].start_time, datetime.time(9, 0))


if __name__ == "__main__":
    unittest.main()
