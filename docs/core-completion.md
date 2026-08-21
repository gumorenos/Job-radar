# Job Radar — cierre del núcleo personal v1

Este documento define qué significa “núcleo cerrado” para la primera versión personal de Job Radar. No implica despliegue de producción, integraciones futuras ni cierre de todo el roadmap.

## Capacidades incluidas

### Ingesta y trazabilidad

- `POST /api/v1/ingestions/jobs` con Bearer token e `Idempotency-Key`.
- Idempotencia protegida también frente a carreras concurrentes.
- Raw payload preservado para trazabilidad y compatibilidad futura.
- Normalización de título, empresa, ubicación, modalidad, seniority, URLs y salario estructurado.
- PostgreSQL como única fuente de verdad.
- Worker durable separado de la API.

### Dedupe

- Exact duplicate por source/external id o URL normalizada reutiliza `JobPosting`.
- Cada redescubrimiento conserva un `PostingSighting`.
- Cambios materiales refrescan posting/job y solicitan reanálisis sin multiplicar tareas pendientes.
- Reapariciones fuera de ventana crean un nuevo `Job` enlazado mediante `parent_job_id`.
- Duplicados inciertos se guardan como `DuplicateCandidate` y se revisan con `Unir` / `Mantener separadas`.
- Un merge consolida fuentes y CRM, pero no reescribe `MatchAnalysis` histórico.

### Matching y reglas

Analyzer actual: `rules-v3`.

- Las reglas duras tienen precedencia absoluta sobre señales positivas.
- Títulos de prácticas/asistente/junior se descartan.
- Presencial fuera de Lima Metropolitana/Callao se descarta.
- Salario PEN publicado por debajo del mínimo aplicable se descarta.
- Remote LATAM/Global usa el mínimo remoto aunque una plataforma informe `country=Peru`.
- Salario numérico publicado en moneda no convertida a PEN mensual queda en `REVIEW`; nunca se inventa un tipo de cambio.
- Salario desconocido no descarta.
- Industria agroindustrial, degree mismatch y experience gap permanecen modelados como warnings; estos dos últimos requieren hechos enriquecidos antes de activarse automáticamente.
- `HIGH_PRIORITY` exige un rol HR/People objetivo y un área foco; términos genéricos como Manager/Lead no bastan sin contexto HR/People en el título.
- Fortalezas, gaps, reglas y recomendación quedan persistidos en `MatchAnalysis`.

### Radar y feedback

- Radar real con Alta prioridad, Revisar y Descartadas.
- Detalle lateral con explicación, fortalezas, gaps, salario y fuentes.
- Clasificación humana auditable sin borrar la clasificación del sistema.
- Vista de posibles duplicados con comparación y resolución humana.

### CRM de postulaciones

Etapas independientes del matching:

- `TO_APPLY`
- `APPLIED`
- `INTERVIEW`
- `OFFER`
- `CLOSED`

Se conservan `applied_at`, `closed_at` y notas; añadir una vacante es idempotente.

### CVs

- Biblioteca versionada.
- Originales/versiones anteriores no se sobrescriben.
- CV manual puede quedar aprobado.
- CV generado por IA nace `DRAFT` y no puede activarse ni sustituir el Base antes de aprobación explícita.
- Matching recomienda un CV especializado aprobado cuando encaja; en su defecto usa el Base aprobado.

### Configuración

- Perfil personal editable desde UI/API.
- Salario local y multiplicador remoto.
- Roles, ubicaciones, áreas foco y adyacentes.
- Hora de revisión y timezone IANA.
- Una sola fuente compartida de defaults para perfil/matching/CVs.

### Notificaciones

- `DISCARD`: sin notificación.
- `HIGH_PRIORITY`: dashboard inmediato + Telegram inmediato.
- `REVIEW`: dashboard inmediato + Telegram daily review.
- Dashboard queda registrado como entregado al estar disponible en Radar.
- Telegram usa tareas durables, retry/backoff y batch diario.
- Telegram está deshabilitado por defecto y no produce tráfico sin configuración explícita.

### Seguridad operativa

- API y PostgreSQL siguen configurados para loopback en Compose.
- Producción falla al arrancar con API key o password de DB de desarrollo conocidos.
- Telegram habilitado con credenciales incompletas falla al arrancar.
- `.env`, storage, backups y documentos personales están excluidos del repo público.
- El acceso web público sigue bloqueado como decisión de despliegue hasta configurar Cloudflare Access.

## Validación automatizada

El gate CI exige:

- Ruff
- mypy
- unit tests
- `alembic upgrade head` sobre PostgreSQL 18
- integration tests PostgreSQL

La validación Oracle ARM64, navegador real, puertos y Cloudflare corresponde a OpenClaw y es un gate separado antes del merge/despliegue.

## Fuera del núcleo v1

No bloquean este cierre:

- email inbound/webhooks
- import histórico del MVP/Notion
- FX enrichment en tiempo real
- extracción AI avanzada de degree/years/skills
- generación automática de CVs
- MCP
- Grafana
- extensión de navegador
- multiusuario/SaaS/billing/RBAC
- optimización N+1 de Radar para escala mayor
- producción, backups externos y CI/CD de despliegue
