# programista-providers

Repo z paczkami dostawców treści (TV / Radio / Archiwum) dla aplikacji desktop `programista` (TVGuide).

## Dostawcy (aktualnie)

### TV (`tv_providers.zip`)
- `teleman` — Teleman (`https://www.teleman.pl`)

### Radio (`radio_providers.zip`)
- `polskieradio` — Polskie Radio (`https://www.polskieradio.pl/Portal/Schedule/Schedule.aspx`)
- `radiokierowcow` — Radio Kierowców (`https://radiokierowcow.pl/ramowka`)
- `nowyswiat` — Radio Nowy Świat (`https://nowyswiat.online/ramowka`)
- `radio357` — Radio 357 (`https://radio357.pl/ramowka/`)

### Archiwum (`archive_providers.zip`)
- `fandom-archive` — staratelewizja.fandom.com (`https://staratelewizja.fandom.com/pl/wiki/Strona_g%C5%82%C3%B3wna`)

### TV z udogodnieniami (`tv_accessibility_providers.zip`)
- `tvp` — TVP (`https://www.tvp.pl/program-tv`) (napisy / język migowy / audiodeskrypcja)
- `polsat` — Polsat (`https://www.polsat.pl/tv-html/`) (napisy / język migowy / audiodeskrypcja)
- `puls` — TV Puls (`https://tyflo.eu.org/epg/puls/`) (napisy / język migowy / audiodeskrypcja)

## Artefakty (GitHub Releases)

Ta aplikacja pobiera z Release (latest):
- `latest.json`
- `tv_providers.zip`
- `tv_accessibility_providers.zip`
- `radio_providers.zip`
- `archive_providers.zip`

W `latest.json` jest SHA256 każdej paczki (integralność pobrania).

## Budowanie paczek lokalnie

1) Ustaw wersję w `version.txt`
2) Uruchom:
   - `python scripts/build_packs.py`
3) Wynik trafia do `dist/`
