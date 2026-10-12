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

Dos tipos de enlace (desde el 12 oct 2026):
  * álbum compartido público  …icloud.com/sharedalbum/#B0X…   → API `sharedstreams`
  * «Enlace de iCloud»        photos.icloud.com/shared/album/<id>,
                              share.icloud.com/photos/<id>, icloud.com/photos/#<id>
                                                              → CloudKit (ver abajo)
El segundo solo se puede leer si se compartió como «cualquiera con el enlace»; si
pide correo o invitación, Apple responde «Share not found» y no hay nada que hacer
sin cuenta. Los detalles de la API están en bot/ICLOUD_HALLAZGOS.md.

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

RE_TOKEN = re.compile(r"(?:sharedalbum/?#|album/?#?|photos/?#|/)([A-Za-z0-9_-]{10,})\s*$")


def album_token(url: str) -> str | None:
    """Saca el token del enlace: …/sharedalbum/#B0X5abc… → B0X5abc…"""
    url = url.strip().strip("<>\"'").split("?", 1)[0].rstrip("/")
    if "#" in url:
        tail = url.split("#", 1)[1].strip("/")
        if re.fullmatch(r"[A-Za-z0-9_-]{10,}", tail):
            return tail
    m = RE_TOKEN.search(url)
    return m.group(1) if m else None


def link_kind(url: str) -> str:
    """«album» (álbum compartido público, sharedstreams) o «link» (Enlace de iCloud,
    CloudKit). Lo que no se reconoce se trata como álbum, que es lo de siempre."""
    u = url.strip().strip("<>\"'").lower()
    if "sharedalbum" in u:
        return "album"
    if re.search(r"photos\.icloud\.com/shared/album/|share\.icloud\.com/photos/|"
                 r"icloud\.com/photos/?#", u):
        return "link"
    return "album"


# --- Enlace de iCloud (CloudKit) -------------------------------------------------
# Confirmado con tráfico real el 12 oct 2026 (bot/ICLOUD_HALLAZGOS.md):
#   1. POST ckdatabasews…/public/records/resolve  {"shortGUIDs":[{"value":<id>}]}
#      → zoneID, título y un token anónimo (20 min) + la partición de la base.
#   2. POST {partición}/…/shared/records/query?publicAccessAuthToken=<token>
#      recordType CPLAssetAndMasterByAddedDate, paginado por startRank.
#   3. Cada CPLMaster trae resOriginalRes.downloadURL, que se baja con un GET.
# El fileChecksum del original es el mismo checksum que da el álbum compartido
# clásico, así que las fotos se llaman igual y no se duplican entre un enlace y otro.
CK_HOST = "https://ckdatabasews.icloud.com"
CK_PATH = "/database/1/com.apple.photos.cloud/production"
CK_HEADERS = {"User-Agent": UA, "Origin": "https://photos.icloud.com",
              "Referer": "https://photos.icloud.com/", "Content-Type": "text/plain"}
CK_PAGE = 200             # registros por consulta (vienen en pares master + asset)
MSG_LINK_NOT_FOUND = (
    "Apple no reconoce ese enlace de iCloud. Suele ser una de tres cosas:\n"
    "· caducó (los «Enlaces de iCloud» duran 30 días) o se dejó de compartir;\n"
    "· el álbum es solo por invitación: la página pide un correo para entrar. "
    "En el iPhone, abre el álbum → compartir → «Cualquiera con el enlace»;\n"
    "· el enlace llegó cortado.\n"
    "También sirve el álbum compartido con «Sitio web público» "
    "(https://www.icloud.com/sharedalbum/#B0X5…).")


class CloudKitAlbum:
    """Un Enlace de iCloud abierto de forma anónima."""

    def __init__(self, guid: str, session: requests.Session):
        self.guid, self.session = guid, session
        self.title = None
        self._resolve()

    def _resolve(self) -> None:
        r = self.session.post(f"{CK_HOST}{CK_PATH}/public/records/resolve",
                              params={"sharing_url_key": self.guid},
                              data=json.dumps({"shortGUIDs": [{"value": self.guid}]}),
                              headers=CK_HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            raise LookupError(f"iCloud respondió {r.status_code} al abrir el enlace.")
        res = (r.json().get("results") or [{}])[0]
        access = res.get("anonymousPublicAccess") or {}
        if res.get("serverErrorCode") or not access.get("token") or not res.get("zoneID"):
            raise LookupError(MSG_LINK_NOT_FOUND)
        self.zone = res["zoneID"]
        self.token = access["token"]
        self.base = access.get("databasePartition", CK_HOST).replace(":443", "")
        fields = (res.get("share") or {}).get("fields") or {}
        self.title = (fields.get("cloudkit.title") or {}).get("value")

    def _query(self, query: dict, limit: int | None = None) -> dict:
        body = {"query": query, "zoneID": self.zone}
        if limit:
            body["resultsLimit"] = limit
        for attempt in (1, 2):
            r = self.session.post(f"{self.base}{CK_PATH}/shared/records/query",
                                  params={"remapEnums": "true", "sharing_url_key": self.guid,
                                          "publicAccessAuthToken": self.token},
                                  data=json.dumps(body), headers=CK_HEADERS, timeout=TIMEOUT)
            if r.status_code in (401, 403, 421) and attempt == 1:
                self._resolve()                 # el token anónimo dura 20 minutos
                continue
            r.raise_for_status()
            return r.json()
        return {}

    def count(self) -> int:
        data = self._query({"recordType": "HyperionIndexCountLookup", "filterBy": [{
            "fieldName": "indexCountID", "comparator": "IN",
            "fieldValue": {"value": ["CPLAssetByAddedDate"], "type": "STRING_LIST"}}]})
        for rec in data.get("records", []):
            n = ((rec.get("fields") or {}).get("itemCount") or {}).get("value")
            if isinstance(n, int):
                return n
        return 0

    def photos(self) -> list[dict]:
        """Una entrada por foto: {"checksum", "url", "size", "added", "video"}."""
        out, seen, rank = [], set(), 0
        for _ in range(500):                    # tope de páginas (100 000 fotos)
            data = self._query({"recordType": "CPLAssetAndMasterByAddedDate", "filterBy": [
                {"fieldName": "direction", "comparator": "EQUALS",
                 "fieldValue": {"value": "ASCENDING", "type": "STRING"}},
                {"fieldName": "startRank", "comparator": "EQUALS",
                 "fieldValue": {"value": rank, "type": "INT64"}}]}, CK_PAGE)
            records = data.get("records", [])
            assets = sum(1 for r in records if r.get("recordType") == "CPLAsset")
            for rec in records:
                item = ck_photo(rec)
                if item and item["checksum"] not in seen:
                    seen.add(item["checksum"])
                    out.append(item)
            if not assets:
                break
            rank += assets
        return out


def ck_photo(rec: dict) -> dict | None:
    """CPLMaster → foto descargable. Los vídeos se marcan y no se bajan: el bot
    solo procesa capturas. Una Live Photo trae su imagen en resOriginalRes."""
    if rec.get("recordType") != "CPLMaster":
        return None
    f = rec.get("fields") or {}
    val = (f.get("resOriginalRes") or {}).get("value") or {}
    if not val.get("downloadURL") or not val.get("fileChecksum"):
        return None
    try:
        import base64
        checksum = base64.b64decode(val["fileChecksum"]).hex()
    except (ValueError, TypeError):
        return None
    kind = str((f.get("itemType") or {}).get("value", "")).lower()
    return {"checksum": checksum,
            "url": val["downloadURL"].replace("${f}", f"{checksum[:24]}.jpg"),
            "size": val.get("size"),
            "added": (rec.get("created") or {}).get("timestamp"),
            "video": any(t in kind for t in ("movie", "mpeg", "video"))}


def ck_age_minutes(photos: list[dict]) -> float | None:
    stamps = [p["added"] for p in photos if isinstance(p.get("added"), (int, float))]
    return (time.time() - max(stamps) / 1000) / 60 if stamps else None


def ck_wait_until_settled(album: CloudKitAlbum, photos: list[dict],
                          report=print, sleep=time.sleep) -> list[dict]:
    """Igual que wait_until_settled, pero contando con la consulta rápida de CloudKit."""
    age = ck_age_minutes(photos)
    if age is None or age >= RECENT_MINUTES:
        return photos                           # nada reciente: no hay subida en curso
    report(json.dumps({"event": "settling", "count": len(photos), "age_min": round(age, 1)}))
    count, stable, waited = len(photos), 0, 0.0
    while stable < STABLE_POLLS_RECENT and waited < MAX_WAIT_MINUTES * 60:
        sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        now = album.count()
        if now == count:
            stable += 1
        else:
            report(json.dumps({"event": "growing", "before": count, "count": now}))
            count, stable = now, 0
    return album.photos() if count != len(photos) else photos


def to_jpeg(path: Path) -> None:
    """Los originales pueden venir en HEIC; el resto del sistema espera JPEG."""
    with open(path, "rb") as fh:
        if fh.read(2) == b"\xff\xd8":
            return
    from PIL import Image
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    with Image.open(path) as im:
        im.convert("RGB").save(path, "JPEG", quality=92)


def download_link(url: str, out_dir: Path, limit: int = 0, list_only: bool = False,
                  report=print, settle: bool = True) -> dict:
    """Enlace de iCloud → mismas fotos, mismos nombres y mismos eventos que un álbum."""
    token = album_token(url)
    if not token:
        raise ValueError("No reconozco el enlace de iCloud.")
    session = requests.Session()
    album = CloudKitAlbum(token, session)
    if list_only:
        return {"total": album.count(), "downloaded": 0, "skipped": 0, "dir": str(out_dir)}
    photos = album.photos()
    if settle:
        photos = ck_wait_until_settled(album, photos, report)
    videos = sum(1 for p in photos if p["video"])
    photos = [p for p in photos if not p["video"]]
    # La misma foto puede estar ya en la carpeta de otro enlace (el álbum clásico
    # y su Enlace de iCloud comparten checksum): se busca en todas las hermanas.
    known = {f.name for d in out_dir.parent.glob("album_*") for f in d.glob("ic_*.jpg")
             if f.stat().st_size > 0}
    downloaded = skipped = failed = 0
    pending = []
    for p in photos:
        name = f"ic_{p['checksum'][:24]}.jpg"
        if name in known:
            skipped += 1
            report(json.dumps({"event": "skip", "file": name}))
        else:
            pending.append((name, p))
    if limit:
        pending = pending[:limit]
    total = skipped + len(pending)
    if pending:                                 # sin fotos nuevas no se crea la carpeta
        out_dir.mkdir(parents=True, exist_ok=True)
    for name, p in pending:
        dest = out_dir / name
        for attempt in (1, 2, 3):
            try:
                with session.get(p["url"], timeout=TIMEOUT, stream=True,
                                 headers={"User-Agent": UA}) as resp:
                    resp.raise_for_status()
                    tmp = dest.with_suffix(".part")
                    with open(tmp, "wb") as fh:
                        for block in resp.iter_content(65536):
                            fh.write(block)
                    to_jpeg(tmp)
                    tmp.rename(dest)
                downloaded += 1
                report(json.dumps({"event": "get", "file": name,
                                   "done": downloaded + skipped, "total": total}))
                break
            except (requests.RequestException, OSError) as exc:
                dest.with_suffix(".part").unlink(missing_ok=True)
                if attempt == 3:
                    failed += 1
                    report(json.dumps({"event": "fail", "file": name,
                                       "error": str(exc)[:120]}))
                else:
                    time.sleep(2 * attempt)
    return {"total": total, "downloaded": downloaded, "skipped": skipped,
            "failed": failed, "videos": videos, "title": album.title, "dir": str(out_dir)}


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
    if r.status_code == 404:
        # Visto el 12 oct 2026: iOS migró el álbum compartido de Brayhan a una
        # «colección compartida» y el enlace viejo dejó de existir en sharedstreams.
        raise LookupError(
            "Ese álbum compartido ya no existe en iCloud con ese enlace. Si el iPhone "
            "lo migró al formato nuevo, abre el álbum, comparte de nuevo y mándame el "
            "enlace que salga (photos.icloud.com/shared/album/…).")
    r.raise_for_status()
    return r.json().get("photos", [])


# El iPhone sube una tanda de fotos al álbum poco a poco, y webstream solo devuelve
# las que ya terminaron de subir. El 28 sep el bot leyó el álbum un minuto después
# de que Brayhan añadiera 92 capturas: iCloud tenía 30 y las 62 restantes (todo el
# Form 67) llegaron después, sin que nadie las procesara. Por eso, antes de bajar,
# se sondea hasta que el conteo deje de cambiar.
POLL_SECONDS = 45
STABLE_POLLS = 2          # sondeos seguidos sin cambios si la última tanda es vieja
STABLE_POLLS_RECENT = 4   # … y si subió hace menos de RECENT_MINUTES (≈3 min quieto)
RECENT_MINUTES = 30
MAX_WAIT_MINUTES = 25


def latest_batch_age(photos: list[dict]) -> float | None:
    """Minutos desde la tanda más reciente del álbum (batchDateCreated, en UTC)."""
    from datetime import datetime, timezone
    stamps = []
    for p in photos:
        s = p.get("batchDateCreated") or p.get("dateCreated")
        try:
            stamps.append(datetime.fromisoformat(s.replace("Z", "+00:00")))
        except (AttributeError, ValueError):
            continue
    if not stamps:
        return None
    return (datetime.now(timezone.utc) - max(stamps)).total_seconds() / 60


def wait_until_settled(base: str, session: requests.Session, photos: list[dict],
                       report=print, sleep=time.sleep) -> list[dict]:
    """Relee el álbum hasta que el número de fotos se quede quieto."""
    age = latest_batch_age(photos)
    recent = age is not None and age < RECENT_MINUTES
    need = STABLE_POLLS_RECENT if recent else STABLE_POLLS
    stable, waited = 0, 0.0
    if recent:
        report(json.dumps({"event": "settling", "count": len(photos),
                           "age_min": round(age, 1)}))
    while stable < need and waited < MAX_WAIT_MINUTES * 60:
        sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        now = list_photos(base, session)
        if len(now) == len(photos):
            stable += 1
        else:
            report(json.dumps({"event": "growing", "before": len(photos),
                               "count": len(now)}))
            photos, stable = now, 0
            if not recent:                        # sigue subiendo: más paciencia
                recent, need = True, STABLE_POLLS_RECENT
    return photos


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
                   report=print, settle: bool = True) -> dict:
    if link_kind(url) == "link":
        return download_link(url, out_dir, limit, list_only, report, settle)
    token = album_token(url)
    if not token:
        raise ValueError("No reconozco el enlace. Debe ser un álbum compartido de "
                         "iCloud, del tipo https://www.icloud.com/sharedalbum/#B0…")
    session = requests.Session()
    base = base_url(token, session)
    photos = list_photos(base, session)
    if settle and not list_only:
        photos = wait_until_settled(base, session, photos, report)
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

    def have(cs):
        # el checksum identifica la foto: si ya está, no se vuelve a bajar
        dest = out_dir / f"ic_{cs[:24]}.jpg"
        return dest.exists() and dest.stat().st_size > 0

    pending = []
    for cs in checksums:
        if have(cs):
            skipped += 1
            report(json.dumps({"event": "skip", "file": f"ic_{cs[:24]}.jpg"}))
        else:
            pending.append(cs)
    for i in range(0, len(pending), CHUNK):     # solo se piden URLs de lo que falta
        group = pending[i:i + CHUNK]
        urls = asset_urls(base, [guid_of[c] for c in group], session)
        for cs in group:
            dest = out_dir / f"ic_{cs[:24]}.jpg"
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
    ap.add_argument("url", help="álbum compartido o Enlace de iCloud")
    ap.add_argument("--out", type=Path, help="carpeta destino")
    ap.add_argument("--limit", type=int, default=0, help="descargar solo las primeras N")
    ap.add_argument("--list", action="store_true", dest="list_only",
                    help="solo decir cuántas fotos tiene")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-settle", action="store_true",
                    help="no esperar a que el álbum termine de subir")
    args = ap.parse_args()
    if not args.list_only and not args.out:
        ap.error("hace falta --out (o usa --list)")
    try:
        res = download_album(args.url, args.out or Path("."), args.limit, args.list_only,
                             report=(lambda _l: None) if args.quiet else
                             (lambda l: print(l, flush=True)),
                             settle=not args.no_settle)
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
