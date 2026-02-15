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

from programista_providers_radio.polskieradio import (  # noqa: E402
    extract_pr_category_id_from_article_link,
    parse_pr_audycje_details_html,
    parse_pr_internal_schedule_json,
)


class TestPolskieRadioAudycjeDetailsParsing(unittest.TestCase):
    def test_extracts_category_id_from_article_link(self) -> None:
        self.assertEqual(
            extract_pr_category_id_from_article_link("https://www.polskieradio.pl/7/3730/Artykul/1,test"),
            3730,
        )
        self.assertEqual(
            extract_pr_category_id_from_article_link("//www.polskieradio.pl/9/322/Artykul/2,test"),
            322,
        )
        self.assertIsNone(extract_pr_category_id_from_article_link("https://www.polskieradio.pl/ramowka"))

    def test_parses_internal_schedule_json(self) -> None:
        raw = [
            {
                "station": "Jedynka",
                "schedules": [
                    {"startTime": "00:00", "title": "Test", "categoryId": 123},
                    {"startTime": "12:00", "title": "Hejnał", "categoryId": None},
                ],
            },
            {"station": "PR24", "schedules": [{"startTime": "00:00", "title": "Informacje", "categoryId": None}]},
        ]

        parsed = parse_pr_internal_schedule_json(json.dumps(raw, ensure_ascii=False))
        self.assertIn("jedynka", parsed)
        self.assertIn("pr24", parsed)

        jed = parsed["jedynka"]
        self.assertEqual(jed[0].start_time, "00:00")
        self.assertEqual(jed[0].title_key, "test")
        self.assertEqual(jed[0].category_id, 123)
        self.assertEqual(jed[1].category_id, None)

    def test_parses_audycje_details_html_and_dedupes_hosts(self) -> None:
        payload = {
            "props": {
                "pageProps": {
                    "details": {
                        "name": "Test Show",
                        "lead": "Linia 1\nLinia 2",
                        "description": "Opis",
                        "station": "Dwójka",
                    },
                    "hosts": [
                        {"name": "Agnieszka", "surname": "Trzeciakiewicz"},
                        {"name": "agnieszka", "surname": "trzeciakiewicz"},
                    ],
                }
            }
        }

        html = (
            "<html><body>"
            f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload, ensure_ascii=False)}</script>'
            "</body></html>"
        )
        details = parse_pr_audycje_details_html(html)
        self.assertEqual(details.hosts, ["Agnieszka Trzeciakiewicz"])
        self.assertEqual(details.lead, "Linia 1\nLinia 2")
        self.assertEqual(details.description, "Opis")

    def test_strips_html_tags_and_trims_trivial_paragraphs(self) -> None:
        payload = {
            "props": {
                "pageProps": {
                    "details": {
                        "name": "Test Show",
                        "lead": "<p>Linia <strong>1</strong></p><p>Linia 2</p>",
                        "description": "<p>Opis <strong>pełny</strong></p><p>.</p>",
                        "station": "Jedynka",
                    },
                    "hosts": [],
                }
            }
        }

        html = (
            "<html><body>"
            f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload, ensure_ascii=False)}</script>'
            "</body></html>"
        )
        details = parse_pr_audycje_details_html(html)
        self.assertEqual(details.lead, "Linia 1\nLinia 2")
        self.assertEqual(details.description, "Opis pełny")


if __name__ == "__main__":
    unittest.main()
