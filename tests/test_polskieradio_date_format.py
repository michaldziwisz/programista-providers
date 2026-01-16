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

from programista_providers_radio.polskieradio import PolskieRadioProvider  # noqa: E402


class _FakeHttp:
    def __init__(self, *, html: str) -> None:
        self._html = html
        self.calls: list[dict[str, object]] = []

    def post_form_text(  # noqa: PLR0913
        self,
        url: str,
        data: dict[str, str],
        cache_key: str,
        ttl_seconds: int,
        force_refresh: bool,
    ) -> str:
        self.calls.append(
            {
                "url": url,
                "data": data,
                "cache_key": cache_key,
                "ttl_seconds": ttl_seconds,
                "force_refresh": force_refresh,
            }
        )
        return self._html


class TestPolskieRadioDateFormat(unittest.TestCase):
    def test_posts_selected_date_as_yyyymmdd(self) -> None:
        day = datetime.date(2026, 1, 17)
        html = f"""
        <div class="scheduleViewContainer">
          <li>
            <a onclick="showProgrammeDetails('1','2','00:00','{day.isoformat()}')">
              <span class="sTime">00:00</span>
              <span class="desc">Test</span>
            </a>
          </li>
        </div>
        """

        http = _FakeHttp(html=html)
        provider = PolskieRadioProvider(http)

        parsed = provider._get_multischedule(day, force_refresh=False)

        self.assertEqual(http.calls[0]["data"], {"selectedDate": "20260117"})
        self.assertEqual(parsed["Jedynka"][0].details_ref, f"1|2|00:00|{day.isoformat()}")


if __name__ == "__main__":
    unittest.main()

