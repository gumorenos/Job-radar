# Job Radar — estado del núcleo personal v1

Este documento define el alcance funcional actualmente integrado en `main` para la primera versión personal de Job Radar. No implica despliegue de producción ni cierre del roadmap completo.

## Principio de producto

**Sources discover. Job Radar decides.**

Las fuentes aportan oportunidades; Job Radar conserva trazabilidad, normaliza, deduplica, aplica reglas, analiza compatibilidad y presenta una explicación auditable para que la decisión humana sea rápida.

## Capacidades integradas

### Ingesta y trazabilidad

- `POST /api/v1/ingestions/jobs` con Bearer token e `Idempotency-Key`.
- Idempotencia protegida también frente a carreras concurrentes.
- Raw payload preservado para trazabilidad y compatibilidad futura.
- Normalización de título, empresa, ubicación, modalidad, seniority, URLs, salario y requisitos estructurados.
- PostgreSQL como única fuente de verdad.
- Worker durable separado de la API.
- Estado de ingesta/cola visible desde Configuración sin exponer payloads ni secretos.
- Fundación provider-neutral para email inbound, adjuntos, extracción y runs de procesamiento; el proveedor real todavía no está conectado en producción.

### Dedupe

- Exact duplicate por source/external id o URL normalizada reutiliza `JobPosting`.
- Cada redescubrimiento conserva un `PostingSighting`.
- Cambios materiales refrescan posting/job y solicitan reanálisis sin multiplicar tareas pendientes.
- Una tarea de análisis ya `PENDING` se reutiliza; si otra está `RUNNING`, se deja un follow-up pendiente para leer el estado más reciente.
- Reapariciones fuera de la ventana de 30 días crean un nuevo `Job` enlazado mediante `parent_job_id`.
- Duplicados inciertos se guardan como `DuplicateCandidate` y se revisan con `Unir` / `Mantener separadas`.
- Un merge consolida fuentes y CRM, pero no reescribe `MatchAnalysis`, feedback ni notificaciones históricas.

### Matching y reglas

Analyzer actual: **`rules-v5`**.

- Las reglas duras tienen precedencia absoluta sobre señales positivas.
- Títulos de prácticas/asistente/junior se descartan.
- Presencial fuera de Lima Metropolitana/Callao se descarta.
- Salario PEN publicado por debajo del mínimo aplicable se descarta.
- Remote LATAM/Global usa el mínimo remoto aunque una plataforma informe `country=Peru`.
- Salario numérico publicado que no puede normalizarse de forma segura a PEN mensual queda en `REVIEW`; no se inventa tipo de cambio.
- Salario desconocido no descarta.
- Industria agrícola/agroindustrial produce warning/Review, no descarte.
- Experiencia, carrera/grado y skills se modelan explícitamente con estados `MEETS`, `PARTIALLY`, `TRANSFERABLE`, `DOES_NOT_MEET`, `POSSIBLE_EXCLUSION` y `UNKNOWN`.
- Una brecha de experiencia —incluido el caso 5 años vs 7 requeridos— produce warning/Review y no un hard discard por sí sola.
- Degree mismatch requerido produce Review, no hard discard por sí solo.
- `HIGH_PRIORITY` exige una combinación suficientemente fuerte de rol HR/People objetivo y área foco; términos genéricos como Manager/Lead no bastan sin contexto HR/People en el título.
- Fortalezas, gaps, reglas, structured fit, salario, movimiento de carrera, CV recomendado y explicación quedan persistidos de forma inmutable en `MatchAnalysis`.
- Un reanálisis con la misma clasificación conserva el nuevo `MatchAnalysis` pero no repite alertas; una transición real de clasificación sí conserva la política de notificación correspondiente.

### Radar y feedback

- Radar real con Alta prioridad, Revisar, Descartadas y Posibles duplicados.
- Detalle lateral orientado a decisión rápida con explicación, fortalezas, gaps, requisitos vs perfil, reglas activadas, salario, movimiento de carrera, CV recomendado y fuentes.
- Clasificación humana auditable sin borrar la clasificación del sistema.
- Feedback append-only con motivo estructurado y comentario opcional.
- `GET /api/v1/feedback/insights` resume patrones usando la decisión humana vigente por vacante mientras conserva el conteo histórico de eventos.
- Configuración muestra `Correcciones del Radar`: overrides, acuerdos, motivos y transiciones.
- Los patrones de feedback son señales para revisión; **no mutan reglas automáticamente**.

### CRM de postulaciones

Etapas independientes del matching:

- `TO_APPLY`
- `APPLIED`
- `INTERVIEW`
- `OFFER`
- `CLOSED`

Se conservan `applied_at`, `closed_at` y notas. Añadir una vacante es idempotente y los totales de etapa son exactos independientemente del límite de listado.

### CVs

- Biblioteca versionada; originales/versiones anteriores no se sobrescriben.
- CV manual puede quedar aprobado.
- CV generado por IA nace `DRAFT` y no puede activarse ni sustituir el Base antes de aprobación explícita.
- Matching recomienda un CV especializado aprobado cuando encaja; en su defecto usa el Base/approved fallback.
- Archivos PDF/DOCX/TXT pueden guardarse de forma inmutable y descargarse desde la versión correspondiente.
- La recomendación de CV no activa ni modifica una versión automáticamente.

### Configuración y reanálisis

- Perfil personal editable desde UI/API.
- Salario local y multiplicador remoto.
- Experiencia, grados/carreras, skills directos y skills transferibles.
- Roles, ubicaciones, áreas foco y adyacentes.
- Hora de revisión y timezone IANA.
- Una sola fuente compartida de defaults para perfil/matching/CVs.
- Guardar el perfil no dispara trabajo masivo automáticamente.
- `POST /api/v1/profile/reanalyze` permite aplicar de forma explícita el perfil guardado a Jobs `ACTIVE`/`UNKNOWN`.
- La UI `Reanalizar oportunidades` queda deshabilitada mientras existen cambios sin guardar.
- El reanálisis reutiliza análisis pendientes y deja un follow-up detrás de uno en ejecución cuando corresponde.

### Notificaciones

- `DISCARD`: sin notificación.
- `HIGH_PRIORITY`: dashboard inmediato + Telegram inmediato.
- `REVIEW`: dashboard inmediato + Telegram daily review.
- Dashboard queda registrado como entregado al estar disponible en Radar.
- Centro de notificaciones del dashboard conserva read/unread.
- Telegram usa tareas durables, retry/backoff y batch diario.
- Telegram está deshabilitado por defecto y no produce tráfico sin configuración explícita.
- Reanálisis que no cambia clasificación no genera notificaciones duplicadas.

### Seguridad y operación

- API y PostgreSQL siguen configurados para loopback en Compose.
- Producción falla al arrancar con API key o password de DB de desarrollo conocidos.
- Telegram habilitado con credenciales incompletas falla al arrancar.
- `.env`, storage, backups y documentos personales están excluidos del repo público.
- Hay scripts de preflight, deploy, backup y smoke, además de Compose de producción y build ARM64-compatible.
- Existe un bridge OpenClaw aislado con instalación/activación por etapas; no está activado en producción.
- El acceso web público sigue bloqueado como decisión de despliegue hasta configurar Cloudflare Access/app auth.

## Validación automatizada

El gate CI actual exige:

- Ruff
- mypy
- sintaxis de JavaScript frontend
- sintaxis de scripts operativos y bridge OpenClaw
- validación del Compose de producción
- build de imagen Docker
- unit tests
- `alembic upgrade head` sobre PostgreSQL 18
- integration tests PostgreSQL

La validación real en Oracle ARM64, navegador, puertos, Cloudflare y canary OpenClaw corresponde al gate operativo separado antes de exposición pública.

## Estado de producción

**Job Radar aún no está desplegado en producción.**

No hay todavía:

- servicios Job Radar productivos confirmados;
- ingesta real OpenClaw → Job Radar;
- hostname público de Job Radar;
- Cloudflare Access configurado para Job Radar;
- entrega Telegram productiva confirmada;
- migraciones Job Radar ejecutadas sobre una base productiva.

El plan actual reserva `127.0.0.1:8010` para la API de Job Radar y mantiene PostgreSQL sin exposición pública. El túnel Docker separado del loan calculator no debe modificarse ni consolidarse con Job Radar.

## Fuera del alcance integrado actual

No bloquean el núcleo personal ya desarrollado:

- conexión real del proveedor de email inbound y extracción avanzada de postings;
- import histórico del MVP/Notion;
- FX enrichment en tiempo real para monedas no PEN;
- extracción AI avanzada de carrera, años y skills desde texto libre;
- generación automática de CVs;
- MCP;
- extensión de navegador;
- Grafana/observabilidad externa;
- backups externos y restauración validada en producción;
- despliegue/canary real, Cloudflare Access y live OpenClaw integration;
- multiusuario/SaaS/billing/RBAC.
