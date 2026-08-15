# programista-providers

Repo z paczkami dostawców treści (TV / Radio / Archiwum) dla aplikacji desktop `programista` (TVGuide).

## Dostawcy (aktualnie)

### TV (`tv_providers.zip`)
- `teleman` — Teleman (`https://www.teleman.pl`)
- `wpolsce24` — wPolsce24 (`https://wpolsce24.tv/ramowka`)
- `kanalzero` — Kanał Zero (`https://telemagazyn.pl/stacje/kanal-zero`)
- `polotv` — Polo TV (`https://www.polotv.pl/program-tv/`)
- `tvp-vod-live` — TVP Muzyka i Koncerty (`https://vod.tvp.pl/live,1/tvp-muzyka-i-koncerty,2999109`)

### Radio (`radio_providers.zip`)
- `polskieradio` — Polskie Radio (`https://www.polskieradio.pl/ramowka`)
- `polskieradio-chopin` — Polskie Radio Chopin (`https://chopin.polskieradio.pl/ramowka`)
- `polskieradio-dzieciom` — Polskie Radio Dzieciom (`https://www.polskieradio.pl/18/5575/`)
- `radiokierowcow` — Radio Kierowców (`https://radiokierowcow.pl/ramowka`)
- `radiokielce` — Radio Kielce (`https://radiokielce.pl/ramowka/`)
- `radiobialystok` — Radio Białystok (`https://www.radio.bialystok.pl/ramowka/index`)
- `nowyswiat` — Radio Nowy Świat (`https://nowyswiat.online/ramowka`)
- `radio357` — Radio 357 (`https://radio357.pl/ramowka/`)
- `radiolublin` — Radio Lublin (`https://radio.lublin.pl/ramowka/`)
- `radioolsztyn` — Radio Olsztyn (`https://radioolsztyn.pl/mvc/ramowka/date/`)
- `radiopoznan` — Radio Poznań (`https://radiopoznan.fm/program/`)
- `radiownet` — Radio Wnet (`https://wnet.fm/ramowka`)
- `radiogdansk` — Radio Gdańsk (`https://radiogdansk.pl/ramowka-radia-gdansk/`)
- `radiokatowice` — Radio Katowice (`https://www.radio.katowice.pl/ramowka.html`)
- `radioszczecin` — Radio Szczecin (`https://radioszczecin.pl/9,0,program-radia-szczecin`)
- `radiozet` — Radio ZET (`https://player.radiozet.pl/Ramowka`)
- `radiozachod` — Radio Zachód (`https://zachod.pl/ramowka/`)
- `radiowroclaw` — Radio Wrocław (`https://www.radiowroclaw.pl/broadcasts/view/`)
- `tokfm` — TOK FM (`https://audycje.tokfm.pl/ramowka`)
- `rmf24` — RMF24 (`https://www.rmf24.pl/radio`)
- `rmffm` — RMF FM (`https://www.rmf.fm/ramowka/`)
- `rmfclassic` — RMF Classic (`https://www.rmfclassic.pl/radio/ramowka`)

### Archiwum (`archive_providers.zip`)
- `fandom-archive` — staratelewizja.fandom.com (`https://staratelewizja.fandom.com/pl/wiki/Strona_g%C5%82%C3%B3wna`)

### TV z udogodnieniami (`tv_accessibility_providers.zip`)
- `tvp` — TVP (`https://www.tvp.pl/program-tv`) (napisy / język migowy / audiodeskrypcja)
- `polsat` — Polsat (`https://www.polsat.pl/tv-html/`) (napisy / język migowy / audiodeskrypcja)
- `fokustv` — Fokus TV (`https://www.fokus.tv/program-tv/`) (napisy / język migowy / audiodeskrypcja)
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
