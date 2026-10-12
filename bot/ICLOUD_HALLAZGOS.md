# Enlaces de iCloud: API confirmada (12 oct 2026)

Capturado con un navegador sin interfaz contra un enlace real de Brayhan y reproducido
después con `requests`, sin cookies ni cuenta de Apple. Identificadores, tokens y
correos omitidos a propósito. Lo implementa `scripts/fetch_icloud_album.py`.

## Tipos de enlace

| | Álbum compartido clásico | Enlace de iCloud / colección compartida |
|---|---|---|
| URL | `www.icloud.com/sharedalbum/#B0…` | `photos.icloud.com/shared/album/<id>`, `share.icloud.com/photos/<id>`, `www.icloud.com/photos/#<id>` |
| Backend | `sharedstreams` (`webstream`, `webasseturls`) | CloudKit, contenedor `com.apple.photos.cloud` |
| Sin cuenta | sí, con «Sitio web público» | sí, si es «cualquiera con el enlace» |

**El álbum clásico de Brayhan fue migrado**: sus registros llevan
`migratedFromSharedAlbum = 1` y el enlace `sharedalbum` viejo responde 404 en
`webstream`. El camino vigente es el enlace nuevo.

## Flujo (3 pasos, todo POST con `Content-Type: text/plain`, `Origin: https://photos.icloud.com`)

1. **Resolver** — `https://ckdatabasews.icloud.com/database/1/com.apple.photos.cloud/production/public/records/resolve?sharing_url_key=<id>`
   cuerpo `{"shortGUIDs":[{"value":"<id>"}]}`. Devuelve en `results[0]`:
   `zoneID` (zona `SharedCollection-<uuid>`), `share.fields["cloudkit.title"]`,
   `databaseScope: "SHARED"` y `anonymousPublicAccess` =
   `{token, tokenTTL: 1200000 (20 min), databasePartition: "https://pNNN-ckdatabasews.icloud.com:443"}`.
   Si no se puede leer: `serverErrorCode: "NOT_FOUND"`, `reason: "Share not found"`
   (caducado, dejado de compartir **o solo por invitación**: en ese caso la página
   pide un correo y no hay acceso anónimo).
2. **Listar** — `{partición}/database/1/com.apple.photos.cloud/production/shared/records/query?remapEnums=true&sharing_url_key=<id>&publicAccessAuthToken=<token>`
   - Conteo: `recordType: "HyperionIndexCountLookup"`, filtro `indexCountID IN ["CPLAssetByAddedDate"]`
     → `records[0].fields.itemCount.value`.
   - Fotos: `recordType: "CPLAssetAndMasterByAddedDate"`, filtros `direction = ASCENDING`
     y `startRank = <n>`, más `zoneID` y `resultsLimit` (200 funciona; la web usa 60).
     Devuelve pares `CPLMaster` + `CPLAsset`. **Se pagina sumando a `startRank` el
     número de `CPLAsset` recibidos**; el `continuationMarker` que viene no hace falta.
     Fin: una página sin registros.
3. **Descargar** — en cada `CPLMaster`, `fields.resOriginalRes.value` =
   `{fileChecksum, size, downloadURL}`; el `downloadURL` trae el marcador `${f}`
   (nombre de archivo) y se baja con un GET sin cabeceras especiales.

## Campos

- Imagen: solo `resOriginalRes` y `resJPEGThumbRes` (no hay `resJPEGFullRes` ni
  `resJPEGMedRes` en las colecciones compartidas). `itemType` dice `public.heic` o
  `public.jpeg`, pero lo servido en las capturas fue JPEG; por si acaso, lo que no
  empiece por `FF D8` se convierte con pillow-heif.
- Nombre original: `filenameEnc` (base64). No se usa: las fotos se nombran por checksum.
- Fecha de alta: `created.timestamp` (ms) del registro.
- **`fileChecksum` (base64) decodificado a hex es el mismo checksum del álbum
  clásico**: 632 de 632 coincidieron y los archivos son idénticos byte a byte. Por eso
  ambos caminos nombran `ic_<24 hex>.jpg` y no se duplica nada.

## Lo que no hizo falta

Playwright y httpx (solo se usaron para descubrir la API, fuera del repo). Las
hipótesis del kit original (`shouldFetchRootRecord`, consulta en la base `public`,
`continuationMarker`) no coincidían con la API real.
