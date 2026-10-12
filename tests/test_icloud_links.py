"""Pruebas offline de los Enlaces de iCloud (no tocan los servidores de Apple).

    .venv/bin/python -m pytest tests/test_icloud_links.py

Las respuestas simuladas tienen la forma real observada el 12 oct 2026
(bot/ICLOUD_HALLAZGOS.md), con identificadores y URLs inventados.
"""
import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_icloud_album as fa  # noqa: E402

GUID = "0aBcDeFgHiJkLmNoPqRsTuVwX"
ZONE = {"zoneName": "SharedCollection-TEST", "ownerRecordName": "_owner",
        "zoneType": "REGULAR_CUSTOM_ZONE"}


def checksum(i):
    return base64.b64encode(bytes([1, i]) + bytes(19)).decode()


def pair(i, item_type="public.heic"):
    master = {"recordName": f"M{i}", "recordType": "CPLMaster",
              "created": {"timestamp": 1_000_000_000_000 + i},
              "fields": {"itemType": {"value": item_type},
                         "resOriginalRes": {"type": "ASSETID", "value": {
                             "fileChecksum": checksum(i), "size": 1000 + i,
                             "downloadURL": f"https://cvws.icloud-content.com/B/x{i}/${{f}}?k=1"}},
                         "resJPEGThumbRes": {"type": "ASSETID", "value": {
                             "fileChecksum": "thumb", "size": 10,
                             "downloadURL": f"https://cvws.icloud-content.com/B/t{i}/${{f}}"}}}}
    asset = {"recordName": f"A{i}", "recordType": "CPLAsset", "fields": {}}
    return [master, asset]


class Resp:
    def __init__(self, status=200, data=None, content=b""):
        self.status_code, self._data, self.content = status, data, content

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise fa.requests.HTTPError(str(self.status_code))

    def iter_content(self, _n):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSession:
    """Simula resolve + query paginado + descarga. `n` fotos; la 2 es un vídeo."""

    def __init__(self, n=5, found=True, expire_once=False):
        self.n, self.found, self.expire = n, found, expire_once
        self.calls, self.tokens = [], 0

    def post(self, url, params=None, data=None, **_kw):
        body = json.loads(data)
        self.calls.append(url)
        if url.endswith("/public/records/resolve"):
            assert body == {"shortGUIDs": [{"value": GUID}]}
            if not self.found:
                return Resp(200, {"results": [{"serverErrorCode": "NOT_FOUND",
                                               "reason": "Share not found"}]})
            self.tokens += 1
            return Resp(200, {"results": [{
                "zoneID": ZONE,
                "share": {"fields": {"cloudkit.title": {"value": "Forms"}}},
                "anonymousPublicAccess": {"token": f"tok{self.tokens}", "tokenTTL": 1200000,
                                          "databasePartition": "https://p99-ckdatabasews.icloud.com:443"}}]})
        assert url.startswith("https://p99-ckdatabasews.icloud.com/")
        assert url.endswith("/shared/records/query") and body["zoneID"] == ZONE
        if self.expire:
            self.expire = False
            return Resp(401, {})
        assert params["publicAccessAuthToken"] == f"tok{self.tokens}"
        q = body["query"]
        if q["recordType"] == "HyperionIndexCountLookup":
            return Resp(200, {"records": [{"recordType": "IndexCountResult",
                                           "fields": {"itemCount": {"value": self.n}}}]})
        rank = q["filterBy"][1]["fieldValue"]["value"]
        records = []
        for i in range(rank, min(rank + 2, self.n)):       # páginas de 2 fotos
            records += pair(i, "com.apple.quicktime-movie" if i == 2 else "public.heic")
        return Resp(200, {"records": records})

    def get(self, url, **_kw):
        self.calls.append(url)
        return Resp(200, content=b"\xff\xd8JPEGDATA")


@pytest.mark.parametrize("url,kind,token", [
    (f"https://photos.icloud.com/shared/album/{GUID}", "link", GUID),
    (f"https://photos.icloud.com/shared/album/{GUID}/", "link", GUID),
    (f"https://share.icloud.com/photos/{GUID}", "link", GUID),
    (f"https://www.icloud.com/photos/#{GUID}", "link", GUID),
    (f"https://www.icloud.com/photos/#/{GUID}", "link", GUID),
    ("https://www.icloud.com/sharedalbum/#B0X5qXGF1Grk1tY", "album", "B0X5qXGF1Grk1tY"),
    ("https://www.icloud.com/sharedalbum/es-es/#B0X5qXGF1Grk1tY", "album", "B0X5qXGF1Grk1tY"),
])
def test_kind_and_token(url, kind, token):
    assert fa.link_kind(url) == kind and fa.album_token(url) == token


def test_ck_photo_takes_original_and_names_by_checksum():
    p = fa.ck_photo(pair(7)[0])
    assert p["checksum"].startswith("0107") and not p["video"]
    assert "/x7/" in p["url"] and "${f}" not in p["url"]
    assert fa.ck_photo(pair(7)[1]) is None            # el CPLAsset no es descargable


def test_listing_paginates_and_refreshes_token():
    s = FakeSession(n=5, expire_once=True)
    album = fa.CloudKitAlbum(GUID, s)
    photos = album.photos()
    assert album.title == "Forms" and album.count() == 5
    assert len(photos) == 5 and sum(p["video"] for p in photos) == 1
    assert s.tokens == 2                               # 401 → volvió a resolver


def test_not_found_message_mentions_expiry(monkeypatch):
    monkeypatch.setattr(fa.requests, "Session", lambda: FakeSession(found=False))
    with pytest.raises(LookupError) as e:
        fa.download_link(f"https://photos.icloud.com/shared/album/{GUID}", Path("."), list_only=True)
    assert "30 días" in str(e.value) and "invitación" in str(e.value)


def test_download_skips_videos_and_photos_already_in_sibling_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(fa.requests, "Session", lambda: FakeSession(n=5))
    other = tmp_path / "album_viejo"
    other.mkdir()
    (other / f"ic_{base64.b64decode(checksum(0)).hex()[:24]}.jpg").write_bytes(b"x")
    out = tmp_path / "album_nuevo"
    events = []
    res = fa.download_link(f"https://photos.icloud.com/shared/album/{GUID}", out,
                           report=events.append, settle=False)
    assert (res["downloaded"], res["skipped"], res["failed"], res["videos"]) == (3, 1, 0, 1)
    files = sorted(out.glob("*.jpg"))
    assert len(files) == 3 and all(f.parent == out and f.name.startswith("ic_01") for f in files)
    assert all(f.read_bytes().startswith(b"\xff\xd8") for f in files)


def test_limit_caps_new_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(fa.requests, "Session", lambda: FakeSession(n=5))
    res = fa.download_link(f"https://photos.icloud.com/shared/album/{GUID}",
                           tmp_path / "album_x", limit=2, settle=False)
    assert res["downloaded"] == 2


def test_settle_waits_when_album_is_still_growing():
    class Album:
        def __init__(self): self.counts = iter([3, 4, 4, 4, 4, 4])
        def count(self): return next(self.counts)
        def photos(self): return ["a", "b", "c", "d"]
    recent = [{"added": fa.time.time() * 1000}, {"added": 0}]
    out = fa.ck_wait_until_settled(Album(), recent, report=lambda _l: None, sleep=lambda _s: None)
    assert out == ["a", "b", "c", "d"]
    old = [{"added": 0}]
    assert fa.ck_wait_until_settled(Album(), old, report=None, sleep=None) is old
