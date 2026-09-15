# Job Radar Capture

Extensión personal Manifest V3 para enviar manualmente la vacante de la pestaña activa al pipeline de Job Radar.

## Alcance v1

- Solo lee la pestaña activa después de que el usuario pulsa la extensión.
- Prioriza datos estructurados `JobPosting` JSON-LD y usa un fallback DOM revisable.
- El usuario puede revisar/editar título, empresa, ubicación, modalidad, salario y descripción antes de enviar.
- Usa endpoints exclusivos `/api/v1/extension/*` con `JOB_RADAR_EXTENSION_API_KEY` e `Idempotency-Key`.
- No necesita ni almacena `JOB_RADAR_API_KEY`.
- Consulta el resultado de la misma ingestión y muestra la clasificación cuando el worker termina.
- Puede abrir directamente `#/radar/<job-id>`.
- No hace autofill, auto-apply, scraping en background ni lectura persistente de páginas.

## Autenticación remota recomendada

El dashboard y los endpoints generales permanecen protegidos por la aplicación normal de Cloudflare Access. La extensión usa dos capas separadas:

1. **Cloudflare Access Service Auth**, limitado por una aplicación/política más específica a `jobradar.<dominio>/api/v1/extension/*`.
2. **Job Radar extension key**, configurada en el servidor como `JOB_RADAR_EXTENSION_API_KEY` y aceptada únicamente por `/api/v1/extension/*`.

La extensión envía el Service Token mediante `CF-Access-Client-Id` y `CF-Access-Client-Secret`, y la clave de Job Radar mediante `Authorization: Bearer ...`.

No se debe autorizar el Service Token contra toda la aplicación `jobradar.<dominio>/*`. Debe quedar acotado a `/api/v1/extension/*`, mientras el dashboard sigue requiriendo la identidad humana normal de Cloudflare Access.

## Configuración de la extensión

En Chrome/Edge abrir la página de extensiones, activar **Developer mode**, elegir **Load unpacked / Cargar descomprimida** y seleccionar `browser-extension/`.

En las opciones configurar:

- Origen de Job Radar, por ejemplo `https://jobradar.todoestaaca.com`.
- Clave de extensión: valor de `JOB_RADAR_EXTENSION_API_KEY`.
- Cloudflare Access Service Token Client ID.
- Cloudflare Access Service Token Client Secret.

Para `localhost`/`127.0.0.1`, los campos de Cloudflare pueden quedar vacíos. Para un origen remoto son obligatorios. HTTP remoto se rechaza.

La configuración antigua `apiKey` no se migra: al guardar la nueva conexión se elimina del storage local para evitar seguir conservando la clave general de integraciones.

## Endpoints scoped

- `GET /api/v1/extension/status`: prueba de autenticación de la extensión.
- `POST /api/v1/extension/jobs`: acepta únicamente `ingestion_source=chrome_extension`.
- `GET /api/v1/extension/jobs/{ingestion_id}/result`: solo devuelve ingestas cuyo origen sea `chrome_extension`; otras fuentes responden 404.

Los endpoints generales `/api/v1/ingestions/*` continúan usando `JOB_RADAR_API_KEY` y no aceptan la clave de extensión.

## Seguridad

Las credenciales se almacenan en `chrome.storage.local` de la extensión y nunca se incluyen en el repositorio, documentación, screenshots o logs. Los permisos de host se solicitan explícitamente al guardar la conexión; el manifest no declara `<all_urls>` ni `content_scripts` persistentes.

El Service Token de Cloudflare y `JOB_RADAR_EXTENSION_API_KEY` deben poder revocarse/rotarse de forma independiente. PostgreSQL y el puerto de origen de Job Radar permanecen en loopback; la extensión no requiere abrir puertos del VPS.
