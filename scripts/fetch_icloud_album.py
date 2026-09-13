#!/usr/bin/env python3
"""Descarga todas las fotos de un álbum compartido de iCloud a una carpeta local.

Existe porque Telegram solo deja mandar 30 imágenes por tanda y el bot solo
puede descargar archivos de hasta 20 MB. Con un enlace de álbum compartido el
servidor va directo a iCloud y baja las 500 capturas de una vez.

Cómo se crea el enlace en el iPhone:
    Fotos → selecciona las capturas → Compartir → «Añadir a álbum compartido»
    → crea el álbum → en el álbum, «Personas» → activa «Sitio web público»
    → «Copiar enlace». Queda algo como
    https://www.icloud.com/sharedalbum/#B0X5abcdefghijk

Uso:
    python scripts/fetch_icloud_album.py "<enlace>" --out inbox/lote1
    python scripts/fetch_icloud_album.py "<enlace>" --list        # solo contar
    python scripts/fetch_icloud_album.py "<enlace>" --out D --limit 20

Cómo funciona (API pública que usa la propia web de iCloud):
    POST {base}/webstream      {"streamCtag": null}     → lista de fotos
    POST {base}/webasseturls   {"photoGuids": [...]}    → URL firmada de cada una
`base` es https://p{NN}-sharedstreams.icloud.com/{token}/sharedstreams; si el
álbum vive en otra partición, el primer POST responde 330 con la buena.

Salida: una línea JSON por foto descargada (para que el bot muestre avance) y
un resumen final. Códigos: 0 = todo bien · 2 = enlace no válido · 1 = error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
HEADERS = {"User-Agent": UA, "Origin": "https://www.icloud.com",
           "Referer": "https://www.icloud.com/", "Content-Type": "text/plain"}
CHUNK = 25          # fotos por petición de URLs (las firmas caducan pronto)
TIMEOUT = 60

RE_TOKEN = re.compile(r"(?:sharedalbum/?#|album/?#?|photos/?#|/)([A-Za-z0-9]{10,})\s*$")


def album_token(url: str) -> str | None:
    """Saca el token del enlace: …/sharedalbum/#B0X5abc… → B0X5abc…"""
    url = url.strip().strip("<>\"'")
    if "#" in url:
        tail = url.split("#", 1)[1].strip("/")
        if re.fullmatch(r"[A-Za-z0-9]{10,}", tail):
            return tail
    m = RE_TOKEN.search(url)
    return m.group(1) if m else None


def base_url(token: str, session: requests.Session) -> str:
    """Devuelve la base correcta, siguiendo el redirect 330 de partición."""
    base = f"https://p01-sharedstreams.icloud.com/{token}/sharedstreams"
    r = session.post(f"{base}/webstream", data=json.dumps({"streamCtag": None}),
                     headers=HEADERS, timeout=TIMEOUT)
    if r.status_code == 330:
        host = r.json()["X-Apple-MMe-Host"]
        base = f"https://{host}/{token}/sharedstreams"
    elif r.status_code == 404:
        raise LookupError(
            f"iCloud no reconoce el álbum «{token}». Casi siempre es una de dos cosas:\n"
            "· el álbum no tiene activado «Sitio web público» (Fotos → el álbum → "
            "pestaña «Personas» → activar «Sitio web público»);\n"
            "· el enlace es del botón «Compartir» y no del álbum: el bueno lleva "
            "«sharedalbum» y una almohadilla, así: "
            "https://www.icloud.com/sharedalbum/#B0X5…")
    elif r.status_code != 200:
        raise LookupError(f"iCloud respondió {r.status_code} al abrir el álbum «{token}».")
    return base


def list_photos(base: str, session: requests.Session) -> list[dict]:
    r = session.post(f"{base}/webstream", data=json.dumps({"streamCtag": None}),
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("photos", [])


def best_derivative(photo: dict) -> tuple[str, int] | None:
    """La copia más grande disponible: el OCR agradece la resolución."""
    best, size = None, -1
    for d in photo.get("derivatives", {}).values():
        try:
            s = int(d.get("fileSize") or 0)
        except (TypeError, ValueError):
            s = 0
        if d.get("checksum") and s > size:
            best, size = d["checksum"], s
    return (best, size) if best else None


def asset_urls(base: str, guids: list[str], session: requests.Session) -> dict[str, str]:
    """checksum → URL descargable, para un grupo de fotos."""
    r = session.post(f"{base}/webasseturls", data=json.dumps({"photoGuids": guids}),
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    locations = data.get("locations", {})
    out = {}
    for checksum, item in data.get("items", {}).items():
        loc = locations.get(item.get("url_location"), {})
        hosts = loc.get("hosts") or []
        if not hosts:
            continue
        out[checksum] = f"{loc.get('scheme', 'https')}://{hosts[0]}{item['url_path']}"
    return out


def download_album(url: str, out_dir: Path, limit: int = 0, list_only: bool = False,
                   report=print) -> dict:
    token = album_token(url)
    if not token:
        raise ValueError("No reconozco el enlace. Debe ser un álbum compartido de "
                         "iCloud, del tipo https://www.icloud.com/sharedalbum/#B0…")
    session = requests.Session()
    base = base_url(token, session)
    photos = list_photos(base, session)
    if limit:
        photos = photos[:limit]
    if list_only:
        return {"total": len(photos), "downloaded": 0, "skipped": 0, "dir": str(out_dir)}

    out_dir.mkdir(parents=True, exist_ok=True)
    by_checksum: dict[str, dict] = {}
    for p in photos:
        d = best_derivative(p)
        if d:
            by_checksum[d[0]] = p
    guid_of = {cs: p["photoGuid"] for cs, p in by_checksum.items()}

    downloaded = skipped = failed = 0
    checksums = list(by_checksum)
    for i in range(0, len(checksums), CHUNK):
        group = checksums[i:i + CHUNK]
        urls = asset_urls(base, [guid_of[c] for c in group], session)
        for cs in group:
            # el checksum identifica la foto: si ya está, no se vuelve a bajar
            dest = out_dir / f"ic_{cs[:24]}.jpg"
            if dest.exists() and dest.stat().st_size > 0:
                skipped += 1
                report(json.dumps({"event": "skip", "file": dest.name}))
                continue
            link = urls.get(cs)
            if not link:
                failed += 1
                continue
            for attempt in (1, 2, 3):
                try:
                    with session.get(link, timeout=TIMEOUT, stream=True) as resp:
                        resp.raise_for_status()
                        tmp = dest.with_suffix(".part")
                        with open(tmp, "wb") as fh:
                            for block in resp.iter_content(65536):
                                fh.write(block)
                        tmp.rename(dest)
                    downloaded += 1
                    report(json.dumps({"event": "get", "file": dest.name,
                                       "done": downloaded + skipped,
                                       "total": len(checksums)}))
                    break
                except requests.RequestException as exc:
                    if attempt == 3:
                        failed += 1
                        report(json.dumps({"event": "fail", "file": dest.name,
                                           "error": str(exc)[:120]}))
                    else:
                        time.sleep(2 * attempt)
    return {"total": len(checksums), "downloaded": downloaded, "skipped": skipped,
            "failed": failed, "dir": str(out_dir)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("url", help="enlace del álbum compartido")
    ap.add_argument("--out", type=Path, help="carpeta destino")
    ap.add_argument("--limit", type=int, default=0, help="descargar solo las primeras N")
    ap.add_argument("--list", action="store_true", dest="list_only",
                    help="solo decir cuántas fotos tiene")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    if not args.list_only and not args.out:
        ap.error("hace falta --out (o usa --list)")
    try:
        res = download_album(args.url, args.out or Path("."), args.limit, args.list_only,
                             report=(lambda _l: None) if args.quiet else
                             (lambda l: print(l, flush=True)))
    except (ValueError, LookupError) as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False))
        return 2
    except requests.RequestException as exc:
        print(json.dumps({"ok": False, "reason": f"red: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **res}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
