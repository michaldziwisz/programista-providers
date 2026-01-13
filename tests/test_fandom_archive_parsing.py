import datetime
import re
import sys
import types
import unittest


def _install_tvguide_app_stubs() -> None:
    tvguide_app = sys.modules.get("tvguide_app") or types.ModuleType("tvguide_app")
    core = sys.modules.get("tvguide_app.core") or types.ModuleType("tvguide_app.core")
    util = sys.modules.get("tvguide_app.core.util") or types.ModuleType("tvguide_app.core.util")

    util.POLISH_MONTHS_GENITIVE = {
        1: "Stycznia",
        2: "Lutego",
        3: "Marca",
        4: "Kwietnia",
        5: "Maja",
        6: "Czerwca",
        7: "Lipca",
        8: "Sierpnia",
        9: "Września",
        10: "Października",
        11: "Listopada",
        12: "Grudnia",
    }

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

    providers_archive = sys.modules.get("tvguide_app.core.providers.archive_base") or types.ModuleType(
        "tvguide_app.core.providers.archive_base"
    )

    class ArchiveProvider: ...

    providers_archive.ArchiveProvider = ArchiveProvider

    sys.modules["tvguide_app"] = tvguide_app
    sys.modules["tvguide_app.core"] = core
    sys.modules["tvguide_app.core.util"] = util
    sys.modules["tvguide_app.core.http"] = http
    sys.modules["tvguide_app.core.models"] = models
    sys.modules["tvguide_app.core.providers.base"] = providers_base
    sys.modules["tvguide_app.core.providers.archive_base"] = providers_archive


_install_tvguide_app_stubs()

from programista_providers_archive import fandom_archive  # noqa: E402


class TestFandomArchiveParsing(unittest.TestCase):
    def test_misaligned_categories_use_logo_files(self) -> None:
        wikitext = (
            "[[Plik:Tv gdańsk.jpg|thumb|left]]<br />07:00 Program Lokalny Gdańsk<br />08:00 Koniec\n"
            "\n"
            "[[Plik:Polsat-2.png|thumb|left]]<br />07.00 Piosenka na Życzenie<br />08.00 Garfield\n"
            "\n"
            "[[Kategoria:Ramówki Polsat z 1999 roku]]\n"
            "[[Kategoria:Ramówki TV 3 Gdańsk z 1999 roku]]\n"
        )

        polsat = fandom_archive.extract_channel_schedule_from_wikitext(wikitext, "Polsat")
        self.assertIn("Piosenka na Życzenie", polsat)
        self.assertNotIn("Program Lokalny", polsat)

        gdansk = fandom_archive.extract_channel_schedule_from_wikitext(wikitext, "TV 3 Gdańsk")
        self.assertIn("Program Lokalny", gdansk)

    def test_fallback_index_mapping_when_logo_match_unknown(self) -> None:
        wikitext = (
            "[[Plik:Logo-aaa.png]]<br />07.00 Alpha show\n"
            "\n"
            "[[Plik:Logo-bbb.png]]<br />08.00 Beta show\n"
            "\n"
            "[[Kategoria:Ramówki Alpha z 1999 roku]]\n"
            "[[Kategoria:Ramówki Beta z 1999 roku]]\n"
        )

        alpha = fandom_archive.extract_channel_schedule_from_wikitext(wikitext, "Alpha")
        beta = fandom_archive.extract_channel_schedule_from_wikitext(wikitext, "Beta")

        self.assertIn("07.00 Alpha show", alpha)
        self.assertIn("08.00 Beta show", beta)

    def test_heading_sections_take_priority(self) -> None:
        wikitext = (
            "=== TVP 1 ===\n"
            "07.00 A\n"
            "=== TVP 2 ===\n"
            "08.00 B\n"
        )

        tvp2 = fandom_archive.extract_channel_schedule_from_wikitext(wikitext, "TVP 2")
        self.assertIn("08.00 B", tvp2)
        self.assertNotIn("07.00 A", tvp2)

    def test_timeshare_channel_merges_logo_blocks(self) -> None:
        wikitext = (
            "[[Plik:Cartoon Network (01.06.1998-21.04.2006).png]]<br />06:00 Cartoon\n"
            "\n"
            "[[Plik:TCM 1998.gif]]<br />20:00 Film\n"
            "\n"
            "[[Kategoria:Ramówki Cartoon Network/TCM z 1999 roku]]\n"
        )

        merged = fandom_archive.extract_channel_schedule_from_wikitext(wikitext, "Cartoon Network/TCM")
        self.assertIn("06:00 Cartoon", merged)
        self.assertIn("20:00 Film", merged)

    def test_generic_logo_filename_mapping(self) -> None:
        wikitext = (
            "[[Plik:Logo-4.jpg]]<br />07.30 Dwójka\n"
            "\n"
            "[[Kategoria:Ramówki TVP 2 z 1999 roku]]\n"
        )

        tvp2 = fandom_archive.extract_channel_schedule_from_wikitext(wikitext, "TVP 2")
        self.assertIn("07.30 Dwójka", tvp2)

    def test_wot_abbreviation_matches_logo_filename(self) -> None:
        wikitext = (
            "[[Plik:Warszawski_Oddział_Telewizyjny.jpg]]<br />07:00 WOT show\n"
            "\n"
            "[[Kategoria:Ramówki WOT z 1999 roku]]\n"
        )

        wot = fandom_archive.extract_channel_schedule_from_wikitext(wikitext, "WOT")
        self.assertIn("07:00 WOT show", wot)


if __name__ == "__main__":
    unittest.main()
