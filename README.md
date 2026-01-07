# programista-providers

Repo z paczkami dostawców treści (TV / Radio / Archiwum) dla aplikacji desktop `programista` (TVGuide).

## Artefakty (GitHub Releases)

Ta aplikacja pobiera z Release (latest):
- `latest.json`
- `tv_providers.zip`
- `radio_providers.zip`
- `archive_providers.zip`

W `latest.json` jest SHA256 każdej paczki (integralność pobrania).

## Budowanie paczek lokalnie

1) Ustaw wersję w `version.txt`
2) Uruchom:
   - `python scripts/build_packs.py`
3) Wynik trafia do `dist/`

