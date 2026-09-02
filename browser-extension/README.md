# Job Radar Capture

Extensión personal Manifest V3 para enviar manualmente la vacante de la pestaña activa al pipeline oficial de Job Radar.

## Alcance v1

- Solo lee la pestaña activa después de que el usuario pulsa la extensión.
- Prioriza datos estructurados `JobPosting` JSON-LD y usa un fallback DOM revisable.
- El usuario puede revisar/editar título, empresa, ubicación, modalidad, salario y descripción antes de enviar.
- Reutiliza `POST /api/v1/ingestions/jobs` con Bearer API key e `Idempotency-Key`.
- Consulta el resultado de la misma ingestión y muestra la clasificación cuando el worker termina.
- Puede abrir directamente `#/radar/<job-id>`.
- No hace autofill, auto-apply, scraping en background ni lectura persistente de páginas.

## Primera prueba segura contra Oracle

La primera prueba no necesita publicar Job Radar en Internet.

1. Desplegar en Oracle una imagen inmutable de `main` que incluya este feature, después de backup verificado y QA.
2. Mantener API y dashboard ligados a `127.0.0.1:8010` en Oracle.
3. Desde la PC Windows abrir un túnel SSH hacia Oracle:

   ```powershell
   ssh -N -L 8010:127.0.0.1:8010 ubuntu@<ORACLE_HOST>
   ```

4. Verificar en el navegador local:

   ```text
   http://127.0.0.1:8010/app/
   ```

5. En Chrome/Edge abrir la página de extensiones, activar **Developer mode**, elegir **Load unpacked / Cargar descomprimida** y seleccionar la carpeta `browser-extension/` del checkout local de este repositorio.
6. Abrir las opciones de **Job Radar Capture** y configurar:
   - Origen: `http://127.0.0.1:8010`
   - API key: el valor secreto ya configurado en el deployment de Job Radar. No debe copiarse a documentación, commits, screenshots ni logs.
7. Abrir una vacante real, pulsar la extensión, revisar los campos y enviarla.
8. Confirmar que aparece resultado de normalización/matching y que **Abrir en Radar** lleva al detalle correcto.

Al terminar la prueba, cerrar el proceso SSH elimina el acceso local. No se abren puertos públicos adicionales.

## Configuración remota posterior

Para un origen remoto la extensión rechaza HTTP y exige HTTPS. El dashboard no debe publicarse sin Cloudflare Access o autenticación equivalente. La estrategia de exposición permanente del endpoint de integración se decide por separado; no se debe debilitar Access ni exponer PostgreSQL para facilitar la extensión.

## Seguridad

La API key se almacena en `chrome.storage.local` de la extensión. Es un secreto local de integración: no se sincroniza mediante código del proyecto y solo se usa como `Authorization: Bearer ...` hacia el origen configurado. Los permisos de host se solicitan explícitamente al guardar la conexión; el manifest no declara `<all_urls>` ni `content_scripts` persistentes.
