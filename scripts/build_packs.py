from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


@dataclass(frozen=True)
class PackDef:
    kind: str
    package: str
    asset: str


PACKS: list[PackDef] = [
    PackDef(kind="tv", package="programista_providers_tv", asset="tv_providers.zip"),
    PackDef(kind="radio", package="programista_providers_radio", asset="radio_providers.zip"),
    PackDef(kind="archive", package="programista_providers_archive", asset="archive_providers.zip"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_dir(src_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src_dir.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(src_dir)
            zf.write(p, rel.as_posix())


def main() -> None:
    version = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit("Brak version.txt")

    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir(parents=True, exist_ok=True)

    latest = {"schema": 1, "provider_api_version": 1, "packs": {}}

    for pack in PACKS:
        tmp = DIST / f".tmp-{pack.kind}"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)

        pack_manifest = {
            "schema": 1,
            "kind": pack.kind,
            "version": version,
            "package": pack.package,
            "entrypoint": f"{pack.package}:load",
            "provider_api_version": 1,
            "min_app_version": "0.1.0",
        }
        (tmp / "pack.json").write_text(json.dumps(pack_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        src_pkg = ROOT / pack.package
        if not src_pkg.is_dir():
            raise SystemExit(f"Brak pakietu: {src_pkg}")
        shutil.copytree(src_pkg, tmp / pack.package)

        out_zip = DIST / pack.asset
        zip_dir(tmp, out_zip)
        sha = sha256_file(out_zip)

        latest["packs"][pack.kind] = {"version": version, "sha256": sha, "asset": pack.asset}

        shutil.rmtree(tmp, ignore_errors=True)

    (DIST / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

