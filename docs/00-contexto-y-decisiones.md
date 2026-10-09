# Contexto, stack y decisiones

Qué estamos construyendo, con qué, y qué ya quedó decidido. Las decisiones
llevan código `D-xx` para poder citarlas desde código, commits y PR. Una
decisión no se revierte en silencio: se agrega una nueva que la reemplace y se
marca la anterior como **Reemplazada por D-yy**.

## 1. Contexto del reto

**Reto 01 — Agente Vocal Cognitivo (conocido desde el 2026-10-09).** Un agente
conversacional por voz, en una URL pública, que habla en vivo con la «Relación de
IPS públicas y privadas según el nivel de atención y capacidad instalada» de
datos.gov.co **consumida por API**, con transcripción diarizada y análisis de
sentimiento y emociones. Entrega: **2026-10-09 16:00**. Qué se construye y cómo se
acepta: [07-reto-01-especificacion.md](07-reto-01-especificacion.md). Cómo
trabajamos de a dos: [12-guia-de-trabajo-2-personas.md](12-guia-de-trabajo-2-personas.md).

Hasta el 2026-10-08 el reto era **desconocido** y la fase consistía en una base
genérica adaptable (reglas R-06 y R-07). **Esa premisa terminó (D-09):** el reto se
sirve como *domain pack* (configuración y periferia) y **el núcleo genérico sigue
sin editarse** (R-02). Reto 01 prescinde de base de datos, RAG, embeddings y
cédula: su contexto es **la API en vivo**. `docs/04-rag.md` describe la base
genérica y **no aplica a Reto 01**.

El paquete [sdd_ips](sdd_ips/README.md) (generado por GPT el 2026-10-09) es
**insumo**: los contratos vigentes son `docs/07–13`; ante conflicto mandan estos
([07](07-reto-01-especificacion.md) §3).

### Dominio de juguete

El repo trae un dominio trivial (un FAQ: `config/domains/faq_demo.yaml` y
`docs/faq_demo/`) que valida que el núcleo corre de punta a punta. No es el
producto (regla R-07). El dominio de Reto 01 es `config/domains/reto01_ips.yaml`
*(planeado)*; `faq_demo` se borra cuando el dominio real pase la aceptación.

## 2. Stack

| Capa | Tecnología | Estado |
|---|---|---|
| Orquestación | LangGraph (grafo escrito a mano; en Reto 01, el analista de afecto) | Fijo |
| API | FastAPI (Reto 01: `api/app_voice.py`, solo HTTP, sin base de datos) | Fijo |
| LLM | Perfiles `fast` (Gemini) y `deep` (OpenAI); Grok y Claude opcionales; cadena de respaldo | D-10 (reemplaza D-03) |
| Voz | Tiempo real desde el navegador: OpenAI Realtime y Gemini Live (`VoiceEngine`) | D-11 |
| Datos | datos.gov.co **en vivo** por SODA3 con `httpx` | D-12 |
| Avatar 3D | Fuera de Reto 01 — ver §4 | Aplazado (D-17) |
| Base de datos, RAG, embeddings | PostgreSQL + pgvector + E5: **base genérica; no se usan en Reto 01** | D-02 y D-05 no aplican a Reto 01 (D-09) |
| Frontend | Astro + TypeScript sin framework | D-17 |
| Infraestructura como código | Terraform | Fijo (Azure Container Apps queda como alternativa, no es la ruta de Reto 01) |
| Despliegue | Vercel (Astro estático + FastAPI solo HTTP), Dockerfile de respaldo | D-15 |
| Observabilidad | LangSmith (trazas y feedback) + HUD de latencia | Fijo |
| Testing | pytest (+ Playwright para el navegador) | Fijo |

No se agregan dependencias fuera de esta lista sin discutirlo (regla R-10). Las
de Reto 01 se anotan aquí **al implementarlas**, con su motivo: `httpx` como
dependencia de ejecución (cliente SODA; D-12), `langchain-openai` para el perfil
`deep` (D-10), y `langchain-xai` / `langchain-anthropic` solo si se activan los
perfiles opcionales.

## 3. Voz — decisión y evidencia

**Decidida (D-11):** voz en tiempo real desde el navegador con **OpenAI Realtime** y
**Gemini Live** detrás del contrato `VoiceEngine` ([08](08-contrato-voz-en-vivo.md)).
El motor ganador y los IDs de modelo se fijan en el spike G2
([12](12-guia-de-trabajo-2-personas.md) §8) y se anotan aquí; **se verifican
llamando al servicio**, no por catálogo. La cascada STT→LLM→TTS queda como motor 3
(fase 2).

**Candidatos evaluados antes de D-11 (plan B).** Evidencia completa en
[anexos/us1-modelos-voz.md](anexos/us1-modelos-voz.md).

| Candidato | A favor | En contra / a verificar |
|---|---|---|
| Cartesia | Latencia de TTS muy baja, voces clonables | Costo; sin clave medida |
| Deepgram | STT fuerte, diarización en streaming | TTS menos maduro |
| Azure AI Speech (estándar) | Visemas en `es-CO`; TTFA en caliente 214–551 ms (medido 2026-10-06) | Frío 791–1514 ms; F0 permite 1 STT concurrente |
| Gemini (TTS + transcribe) | Misma clave que el LLM | TTS ~2.5–3 s por frase: lejos de tiempo real |

**Mediciones con la key del proyecto (2026-10-06, llamadas reales):**

| Capacidad | Modelo | Resultado |
|---|---|---|
| TTS | `gemini-3.8-flash-lite-tts`, `gemini-3.8-flash-tts`, `gemini-3.1-flash-tts-preview` | OK, ~2.5–3 s para ~3.7 s de audio en español |
| TTS | `gemini-2.5-flash-preview-tts` | OK pero 47 s: inservible en tiempo real |
| STT | `gemini-3.5-transcribe` | OK, 2.0 s, transcripción correcta |
| Visión | `gemini-3.5-flash-lite` | OK, 2.0 s |
| Tool calling | `gemini-3.5-flash-lite` | OK, 0.9 s |
| Embeddings | `gemini-embedding-001`, `gemini-embedding-2` | OK, 3072 dims (la base genérica usa `vector(768)`) |
| Texto | `gemini-3.5-pro`, `gemini-2.5-flash`, `text-embedding-004` | 404 |

Sin probar hasta el spike G2: los modelos de tiempo real (`gemini-3.8-live`,
`native-audio`, OpenAI Realtime).

## 4. Avatar 3D — aplazado

**Fuera de Reto 01 (D-17).** Queda para la fase 2; la evidencia vive en
[anexos/us2-avatar-3d.md](anexos/us2-avatar-3d.md). **Corrección:** Ready Player Me
ya no existe (cerrado el 2026-01-31); los candidatos vigentes son Microsoft
RocketBox (MIT) o MetaPerson, con Three.js plano y `wawa-lipsync`.

## 5. Decisiones tomadas

| Código | Decisión | Motivo | Fecha |
|---|---|---|---|
| D-01 | **Azure AI Voice Live descartado.** La skill `.claude/skills/azure-voice-live/` queda como material histórico: su patrón puerto/adaptador sigue siendo la base de `VoicePort`, sus detalles de protocolo (eventos WebSocket, `session.update`) ya no aplican | Costo | Antes de 0.4.0 |
| D-02 | **PostgreSQL + pgvector** (`pgvector/pgvector:pg17`, puerto 5433) como base relacional y vector store. Chroma descartado. *La base genérica lo conserva; **no aplica a la app de Reto 01** (D-09).* | Un chat agéntico necesita datos relacionales junto a los vectores; dos almacenes son dos almacenes que sincronizar | 2026-09-22 (0.3.0) |
| D-03 | **LLM: Gemini `gemini-3.5-flash-lite`** con `thinking_level=minimal`. Sin proveedores de respaldo en el factory. **Reemplazada por D-10.** | Medido con nuestro factory: ~1 s por llamada y 15/15 correctas en las tres formas de prompt del grafo. NVIDIA tardaba 9-20 s por turno | 2026-09-28 (0.4.0) |
| D-04 | **LangChain/LangGraph línea 1.x** (`langchain-core` 1.6, `langgraph` 1.2) | La integración actual de Gemini lo exige | 2026-09-28 (0.4.0) |
| D-05 | **Embeddings `intfloat/multilingual-e5-base`**, local, 768 dims. Descartados los modelos en inglés y LaBSE. *La base genérica lo conserva; **no aplica a Reto 01** (D-09).* | El corpus es en español: los modelos en inglés fallarían en silencio; LaBSE está optimizado para emparejar traducciones, no para recuperación | 2026-09-22 (0.3.0) |
| D-06 | **Identificación por cédula sin contraseña.** **No es autenticación real** ([01-arquitectura.md](01-arquitectura.md) §8). *La base genérica lo conserva; **Reto 01 no usa cédula** (D-09, sesión anónima firmada: R-28).* | Alcance de la demo | 2026-09-22 (0.3.0) |
| D-07 | **Grafo escrito a mano** (`StateGraph`) en vez de `create_react_agent`. *En el bucle de voz de Reto 01 rige la excepción acotada D-14.* | En un agente ReAct el LLM controla el bucle vía tool-calls, lo que incumple R-04 | 2026-09-17 (0.2.0) |
| D-08 | **Migraciones en SQL plano**, sin ORM ni Alembic *(base; Reto 01 no usa base de datos)* | Seis tablas: cualquiera debe poder leer el archivo y saber cómo es la base | 2026-09-22 (0.3.0) |
| D-09 | **Reto 01 conocido: se sirve como domain pack** (`config/domains/reto01_ips.yaml` + `services/ips`); el núcleo genérico no se edita (R-02). Reto 01 **prescinde de base de datos, RAG, embeddings y cédula**: el contexto es la API en vivo | El reto dejó de ser desconocido; la lógica del dominio entra por configuración y periferia. Reformula R-06 y R-07 | 2026-10-09 |
| D-10 | **LLM multi-proveedor con perfiles** para el analista y las tareas de texto: `fast` = Gemini, `deep` = OpenAI; Grok y Claude opcionales por configuración; cadena de respaldo. Los IDs de modelo se fijan tras una prueba autenticada. *Reemplaza a D-03.* | Se quiere comparar fortalezas (velocidad vs razonamiento) y tener respaldo ante cuota o caída | 2026-10-09 |
| D-11 | **Voz en tiempo real desde el navegador**: contrato `VoiceEngine` con adaptadores **OpenAI Realtime** y **Gemini Live**, credenciales efímeras emitidas por el backend. La cascada STT→LLM→TTS es el motor 3 (fase 2). *Retira R-08.* | Es lo realista para 2 personas en ~6 h, con la mejor latencia e interrupciones; usa las APIs pagas del equipo | 2026-10-09 |
| D-12 | **datos.gov.co en vivo** por SODA3 con `httpx` (token si existe; el acceso anónimo funcionó hoy pero no es garantía); SODA2 de respaldo; **sin espejo**. `sodapy` solo en scripts | El jurado verifica la conexión durante la demo; `sodapy` es SODA2, síncrono y sin mantenimiento desde 2022-08-31 | 2026-10-09 |
| D-13 | **Herramientas tipadas y sobre de evidencia** ([09](09-datos-en-vivo-datos-gov-co.md)): el modelo envía JSON, nunca SoQL; el servidor arma la consulta con columnas y funciones permitidas | Exactitud (grano: IPS ≠ sedes ≠ filas) y seguridad | 2026-10-09 |
| D-14 | **Excepción acotada a R-04** en el bucle de voz: el motor de voz decide los turnos y qué herramienta llamar; el backend valida cada llamada contra una lista cerrada y es **determinista** en estilo, límites y honestidad. Cualquier otra transición sigue siendo del grafo | Un motor de voz nativo controla el turno; es el costo de la latencia. *Confirmada por el equipo* | 2026-10-09 |
| D-15 | **Despliegue en Vercel** (Astro estático + FastAPI solo HTTP; el audio va navegador ↔ proveedor) con **Dockerfile de respaldo**; tope de 20 min para decidir el empaquetado. *Reemplaza «Azure Container Apps (fijo)».* | Despliegue rápido; Vercel limita la conexión a 300 s (Hobby) y el cuerpo a 4,5 MB, y sin WebSocket propio no importa | 2026-10-09 (pendiente de cerrar con G1) |
| D-16 | **Afecto multimodal (texto + voz) y política de estilo** («psicología»): estimaciones inciertas, preferencia explícita por encima, sin diagnóstico, con aviso, consentimiento y opción de apagarlo ([10](10-modelos-afecto-y-recuperacion.md) §6) | Decisión del equipo: es Must. Conserva las salvaguardas de sdd_ips | 2026-10-09 |
| D-17 | **Frontend Astro + TypeScript sin framework**; **sin avatar 3D** en el MVP | Tiempo; Three.js plano ya se midió y queda para la fase 2 | 2026-10-09 |
| D-18 | **Estado canónico en el navegador**, recuperación acotada (≤ 2 intentos de motor y ≤ 2 de fuente, plazo de 6 s) y **conmutación de motor** con un sobre de contexto neutral ([10](10-modelos-afecto-y-recuperacion.md) §3–§5) | Sin base de datos y con sesiones de proveedor que caducan (Gemini ≈ 10 min) | 2026-10-09 |
| D-19 | **`main` es la rama de integración y de producción**: los docs se fusionan a `main` en la Puerta 0 y ambas personas parten de ahí ([12](12-guia-de-trabajo-2-personas.md)) | Simplicidad para dos personas; Vercel despliega producción desde `main` | 2026-10-09 |

## 6. Mediciones del 2026-10-09 (consultas reales)

Detalle y números dorados en [09](09-datos-en-vivo-datos-gov-co.md) §9.

| Qué | Resultado |
|---|---|
| SODA3 `POST /api/v3/views/s2ru-bqt6/query.json` sin token | 200 en 0,57 s (`41427`); con token inválido, 403 `permission_denied` |
| SODA2 con SoQL (`count(distinct)`, `group by`, `like`) | 200; `pageSize` 5000 → 200 |
| Latencia de consultas agregadas (desde Colombia) | 0,50–0,80 s por consulta (≈ 0,3 s de TLS nuevo); **un pico de 21 s** en una primera conexión |
| Tamaño y grano de la fuente | 41.427 filas; 9.320 IPS; 10.921 códigos de sede; nivel vacío en el 89% de las IPS; `departamento` mezcla distritos |
| Vercel | WebSocket en beta (Python/FastAPI), 300 s por conexión en Hobby, cuerpo de 4,5 MB, paquete Python de 500 MB |
| Azure Speech F0 | 1 solicitud STT concurrente, no ajustable (S0: 100; activarlo tarda horas) |
| Gemini Live | Conexión ≈ 10 min con `goAway`; token efímero ≈ 30 min (**verificar en G2**) |
