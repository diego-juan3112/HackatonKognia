# Datos en vivo: datos.gov.co (IPS)

Contrato vigente · versión `2026-10-09.3` (aditiva sobre la `.2`: cuatro herramientas nuevas y filtro de capacidad en `search_ips`) · dueño: **carril B** ([12](12-guia-de-trabajo-2-personas.md)).
Decisiones: D-09, D-12 (API en vivo), D-13 (herramientas tipadas y sobre de evidencia).
Reglas: R-22 (evidencia primero), R-23 (herramientas cerradas), R-25 (recuperación acotada).
Base de partida: [sdd_ips/02](sdd_ips/02_tool_contracts.md) y [sdd_ips/04](sdd_ips/04_data_and_retrieval.md), adaptados (ver [07](07-reto-01-especificacion.md) §3).

**El contexto del agente es esta API y nada más.** No hay base de datos, RAG, embeddings ni
espejo: cada cifra sale de una consulta en vivo registrada (R-22). El jurado verifica la
conexión durante la demo, por eso se muestra cada consulta (panel «API en vivo», F-11).

## 1. La fuente

| Dato | Valor (verificado 2026-10-09) |
|---|---|
| Conjunto | `s2ru-bqt6` — *Relación de IPS públicas y privadas según el nivel de atención y capacidad instalada* |
| Origen | Registro Especial de Prestadores de Servicios de Salud (REPS), Ministerio de Salud y Protección Social |
| Licencia | CC BY-SA 4.0 → **atribución visible** en la interfaz (NF-08) |
| Corte | `Fecha corte REPS: Nov  5 2022  1:37PM` (un solo corte para todas las filas); actualización anual |
| Qué **no** contiene | Coordenadas, horarios, disponibilidad de camas ni citas |

### Mapeo de campos

| Campo canónico | Columna de Socrata | Regla |
|---|---|---|
| `department`, `municipality` | `departamento`, `municipio` | Se conserva la grafía; la búsqueda usa forma normalizada aparte |
| `provider_code`, `provider_name` | `c_digo_prestador`, `nombre_prestador` | Texto, no cantidad; nunca redondear ni rellenar ceros |
| `tax_id` | `nit_ips`, `num_digito_verificion` | No va a la voz ni al contexto por defecto |
| `nature`, `level` | `naturaleza`, `num_nivel_atencion` | `nature` ∈ Pública · Privada · Mixta. `level` es **anulable** y no se infiere del nombre |
| `site_code`, `site_number`, `site_name` | `c_digo_sede`, `n_mero_sede`, `nom_sede_ips` | `site_number` conserva el cero a la izquierda |
| `address`, `email`, `phone`, `manager` | `direcci_n`, `email`, `tel_fono`, `gerente` | Solo a petición explícita (§10) |
| `capacity_group`, `capacity_type` | `nom_grupo_capacidad`, `nom_descripcion_capacidad` | Obligatorios para sumar |
| `quantity` | `num_cantidad_capacidad_instalada` | Llega como **texto**; se convierte; nulo ≠ 0 |
| `cutoff`, `source` | `fecha_corte`, `fuente` | Se guarda el texto original junto al valor normalizado |

## 2. Acceso a la API

**Camino principal — SODA3** (verificado: anónimo 200 en 0,57 s; token inválido 403):

```http
POST https://www.datos.gov.co/api/v3/views/s2ru-bqt6/query.json
Content-Type: application/json
X-App-Token: <token del servidor, si existe>

{"query":"SELECT count(DISTINCT c_digo_prestador) AS value","page":{"pageNumber":1,"pageSize":1}}
```

`page.pageNumber` es 1-indexado. La respuesta es un arreglo JSON de objetos con **todo en
texto**. **Respaldo — SODA2:** `GET /resource/s2ru-bqt6.json` con `$select/$where/$group/$order/$limit`.
Una misma consulta lógica se renderiza a ambos formatos.

| Política del cliente (`httpx.AsyncClient`, `integrations/datasets/socrata_client.py` *(planeado)*) | Valor |
|---|---|
| Conexión | Persistente (keep-alive), calentada al pedir el brief |
| Tiempos | **Dos intentos de 3,5 s + 2 s** (con margen dentro del plazo común de 6 s; antes decía 4 s por intento más reintento, que no cabía). Conexión hasta 3,5 s en el primer intento: *G3 midió 0,8–2,7 s en la primera conexión* ([00](00-contexto-y-decisiones.md) §6) |
| Reintentos | **1** ante timeout, 5xx o error de conexión (R-25); 429: se respeta `Retry-After` solo si cabe en el plazo, si no `unavailable` |
| Calentamiento y precarga | La conexión se calienta en `POST /sessions` y `POST /realtime/session` (consulta barata, fuera del camino crítico). Al pedir el brief y al crear la sesión de voz se precargan, **a través de las propias herramientas** (misma SoQL), los agregados más probables: prestadores total y por naturaleza, códigos de sede por naturaleza, camas totales, top 5 departamentos y top 5 municipios por camas. Si se piden en los 60 s siguientes salen `fresh`, nunca `live`. Una sola `httpx.AsyncClient` por proceso con keep-alive; **sin HTTP/2** (exigiría `h2`, dependencia nueva, R-10) |
| Token | `DATOS_GOV_APP_TOKEN`, leído **solo** en `src/config.py` (R-05). Se valida al arrancar: si responde 403 se descarta y se sigue anónimo; **nunca** se envía un token inválido ni se registra |
| Anonimato | El acceso anónimo funcionó hoy, pero la documentación exige token o usuario: **no es una garantía**; se usa el token siempre que exista |
| Codificación | UTF-8 en todo el camino (`Pública`, `BOGOTÁ`) |
| SDK | `sodapy 2.2.0` (SODA2, síncrono, sin mantenimiento desde 2022-08-31) solo en scripts como `build_lexicon.py`; el camino caliente usa `httpx` (cancelar un `await` no detiene un hilo bloqueado) |

**Latencia observada** (desde Colombia, una sola medición por consulta, no p50/p95): consultas
agregadas 0,50–0,80 s, con ≈ 0,3 s de TLS nuevo; **un pico de 21 s en una primera conexión**.
De ahí el calentamiento, el plazo de 4 s y el reconocimiento hablado previo a consultar ([08](08-contrato-voz-en-vivo.md) §5).

## 3. Grano de los datos y cómo se cuenta

| Qué | Cómo |
|---|---|
| Una **fila** | Una categoría de capacidad de una sede; en ambulancias y unidades móviles, **1 fila = 1 unidad** (cantidad 1) |
| Un **prestador (IPS)** | `count(DISTINCT c_digo_prestador)` con los filtros elegidos |
| Una **sede** | `count(DISTINCT c_digo_sede)`; son *códigos de sede*, **no validados como sedes físicas**. **Trampa medida en G3:** `c_digo_sede` se repite entre sedes de un mismo prestador (las 6 sedes de la ESE Bello Salud comparten `c_digo_sede = c_digo_prestador` y solo cambia `n_mero_sede`), así que 10.921 **subcuenta** las sedes listables. `site_count` se rotula «códigos de sede» con `SITE_CODES_NOT_PHYSICAL_SITES`, y una sede concreta siempre se identifica con `site_key` (tres campos) |
| **Capacidad** | `sum(num_cantidad_capacidad_instalada)` de **un grupo** (`capacity_group`) y, si se pide, un tipo; nunca se suman grupos distintos (camas + salas + ambulancias) |
| **Nivel** | Vacío en 8.325 de 9.320 IPS: «sin nivel registrado» ≠ nivel 0 ni «sin nivel» inferido |
| Totales nacionales | Salen de agregados de la fuente, nunca de la primera página ni de un top-k |

## 4. Las herramientas (C-IPS): 5 base + 4 de agente (contrato `.3`)

El modelo envía **JSON, nunca SoQL**. Campos desconocidos se rechazan. Todos los valores se
validan contra el léxico (§7) y contra listas cerradas. Salida acotada (≤ 20 filas) y
consulta con plazo. Un municipio homónimo exige departamento: si no, `status: ambiguous` con
≤ 3 candidatos; **nunca se elige el primero**.

| Herramienta | Entrada | Salida |
|---|---|---|
| `search_ips` | `department?`, `municipality?`, `name?`, `nature?` (Pública/Privada/Mixta), `level?` (1/2/3), `capacity_group?`, `capacity_type?` *(.3)*, `limit=5` (≤ 20), `cursor?` | Hasta `limit` sedes: `site_key`, `provider_name`, `site_name`, `municipality`, `department`, `nature`, `level` (o `null`) + `next_cursor`. Con `capacity_group`: solo sedes que **tienen registrada** esa capacidad, con `quantity`, y `NOT_AVAILABILITY` («no significa que esté abierta ni disponible») |
| `get_ips_details` | `site_key`, `capacity_group?`, `capacity_type?`, `include_contact=false` | La sede y sus capacidades agregadas por grupo/tipo; los campos ausentes salen `null`, nunca inventados |
| `aggregate_ips` | `metric` ∈ `provider_count` · `site_count` · `capacity_sum`; `filters`; `group_by?` ∈ `department` · `municipality` · `nature` · `level`; `order?`, `top_n?` (≤ 10) | `value` o `groups[{key, value}]`, `unit`, `complete`. `capacity_sum` exige `capacity_group`; sin `capacity_type` se suma el grupo completo y se advierte `MIXED_TYPES` |
| `compare_ips` *(Should)* | 2–3 `site_key`, `capacity_group`, `capacity_type?` | Cantidades comparables (mismo tipo y corte); lo nulo o ambiguo queda desconocido; una sola consulta por lote |
| `correct_context` | `target_turn_id`, `expected_state_version`, `field`, `value` | Nuevo `state_version`, evidencia invalidada, filtros confirmados; `invalid`/`STATE_CONFLICT` si la versión no coincide |
| `verify_registration` *(.3)* | **Uno** de: `name` (+ `department?`/`municipality?`), `site_key`, `provider_code` | `registered`, `provider_code`, `provider_name`, `nature`, `levels`/`level_label` («nivel no registrado»), `municipalities` (≤ 5), `site_count` (≤ 20, `site_count_complete`), `site_keys` (≤ 3). Un consulta (`LIMIT 21`). Si no aparece: `empty` «no aparece registrada con ese nombre en el corte de 2022… no prueba que no exista». Homónimos o varias coincidencias: `ambiguous` (≤ 3), nunca el primero |
| `area_profile` *(.3)* | `department` o `municipality` (un solo lugar) | IPS por naturaleza (con `share_pct`) y por nivel (`null` = sin nivel registrado), códigos de sede, `beds` (CAMAS), `ambulances` (AMBULANCIAS), `emergency_rooms` (CONSULTORIOS/Urgencias); `derived`: % con nivel registrado, camas por prestador (1 decimal). 6 consultas **en paralelo**, misma SoQL que `aggregate_ips` (comparten caché). `DERIVED_FROM_SOURCE` |
| `compare_areas` *(.3)* | `areas` (2–3 de `{department?, municipality?}`), `metric` (como `aggregate_ips`), `capacity_group?` (obligatorio en `capacity_sum`), `capacity_type?` | `items[{area, value}]`, `highest`, `comparisons[{higher, lower, difference, ratio, equal}]` calculados en Python. Una consulta por área, en paralelo. Área ambigua: `ambiguous` con `area_index`. `NOT_PER_CAPITA` (cifras absolutas) |
| `dataset_info` *(.3)* | `topic?` ∈ `all` · `contents` · `limits` · `capabilities` | **Sin consulta.** Qué contiene la fuente (campos, grano, corte), qué **no** contiene y qué puede hacer el asistente. Para explicar límites con verdad («no puedo pedir citas porque esta fuente no las trae») |

**Límites contra el abuso:** ninguna lista pasa de 20 filas; comparaciones de 2–3 elementos; el
contacto (dirección, teléfono, correo, gerente) solo sale de `get_ips_details` con
`include_contact=true` y para **una** sede; ninguna herramienta devuelve contactos en bloque.

### Qué puede y qué no puede hacer el agente con esta API

| Puede (siempre con una consulta en vivo registrada) | No puede (la fuente no lo trae) |
|---|---|
| Buscar sedes por lugar, nombre, naturaleza, nivel o capacidad instalada | Pedir o consultar citas, ni decir si hay turno |
| Ver el detalle y la capacidad instalada de una sede | Decir si una cama o servicio está **disponible** hoy, ni si una sede está abierta |
| Verificar si una IPS está registrada en el corte de 2022 | Afirmar que una IPS no existe: solo que no figura en esta fuente |
| Contar IPS o códigos de sede y sumar capacidad, con agrupaciones | Horarios, médicos, servicios habilitados en detalle, calidad, precios, EPS o convenios |
| Perfilar un lugar y comparar 2–3 lugares o sedes, con porcentajes y razones calculadas en Python | Cercanía o rutas (sin coordenadas), cifras por habitante (sin población), datos posteriores a 2022 |

`site_key` = `provider_code:site_code:site_number` (texto). Un `cursor` es opaco (desplazamiento
firmado). Una lista paginada es **incompleta** hasta agotar el cursor; un agregado exacto sí es
completo sin listar filas.

### Plantillas de consulta (SODA3, las arma el servidor con columnas y funciones permitidas)

```sql
-- provider_count / site_count
SELECT count(DISTINCT c_digo_prestador) AS value WHERE naturaleza = 'Pública' AND departamento = 'Antioquia'
SELECT count(DISTINCT c_digo_sede) AS value WHERE municipio = 'MELGAR'
-- capacity_sum
SELECT sum(num_cantidad_capacidad_instalada) AS value
 WHERE nom_grupo_capacidad = 'CAMAS' AND nom_descripcion_capacidad = 'Adultos' AND municipio = 'MEDELLÍN'
-- con group_by y top_n
SELECT municipio, departamento, sum(num_cantidad_capacidad_instalada) AS value
 WHERE nom_grupo_capacidad = 'CAMAS' GROUP BY municipio, departamento ORDER BY value DESC LIMIT 5
-- search_ips (agrupa para no repetir filas de capacidad)
SELECT c_digo_prestador, c_digo_sede, n_mero_sede, nombre_prestador, nom_sede_ips, municipio, departamento, naturaleza, num_nivel_atencion
 WHERE <filtros> GROUP BY <las mismas columnas> ORDER BY nombre_prestador LIMIT 6
-- get_ips_details
SELECT nom_grupo_capacidad, nom_descripcion_capacidad, sum(num_cantidad_capacidad_instalada) AS quantity
 WHERE c_digo_prestador = '564204576' AND c_digo_sede = '564204576' AND n_mero_sede = '01'
 GROUP BY nom_grupo_capacidad, nom_descripcion_capacidad
```

Los literales se escapan duplicando la comilla simple. **Cuidado con el grupo nulo:** en una
agrupación por `level`, la fila sin nivel llega **sin la clave** `num_nivel_atencion`; se
interpreta como `null` («sin nivel registrado»).

## 5. Sobre de resultado (C-EVIDENCE)

Toda herramienta responde este sobre; solo la evidencia validada puede dar cifras al agente (R-22).

```json
{
  "schema_version": "1",
  "tool_call_id": "uuid",
  "turn_id": "uuid",
  "state_version": 3,
  "status": "ok",
  "data": { "value": 9320, "unit": "providers" },
  "evidence": {
    "dataset_id": "s2ru-bqt6",
    "source_url": "https://www.datos.gov.co/resource/s2ru-bqt6.json",
    "query_fingerprint": "sha256:…",
    "cutoff_raw": "Fecha corte REPS: Nov  5 2022  1:37PM",
    "fetched_at": "2026-10-09T15:17:10Z",
    "cache_status": "live",
    "complete": true,
    "unit": "providers",
    "filters": {},
    "warnings": ["CUTOFF_2022"]
  },
  "trace": { "engine": "soda3", "soql": "SELECT count(DISTINCT c_digo_prestador) AS value", "ms": 540, "rows": 1 },
  "error": null,
  "next_cursor": null,
  "context_patch": {}
}
```

El ejemplo ilustra la forma; las cifras reales salen siempre de la consulta.

**Campos añadidos (contrato `.2`, aditivos):** `evidence` y `trace` están **siempre** presentes
(también en `invalid`/`ambiguous`); `traces` lista cada consulta cuando hubo varias; `data.unit` va
en español para mostrar («prestadores», «camas») y `evidence.unit` como código; y **`for_model`**:
texto determinista que el cliente entrega al motor **como salida de la función** (en lugar de los
datos crudos). Dice las cifras exactas con unidad y corte, las advertencias en palabras, qué hacer
ante `ambiguous`/`unavailable`/`empty` y cierra con «cualquier dato que no aparezca aquí no se
sabe». Es la primera barrera contra la alucinación (R-22); la segunda es el verificador de cifras
(`POST /verify/answer`, [10](10-modelos-afecto-y-recuperacion.md) §1).

| Campo | Significado |
|---|---|
| `status` | `ok` · `empty` · `ambiguous` · `unavailable` · `invalid`. **`unavailable` nunca se convierte en `empty`** |
| `cache_status` | `live` (acaba de consultarse) · `fresh` (caché ≤ 60 s) · `stale` (solo si la fuente falla) |
| `complete` | Aplica al conjunto pedido, no a todo el dataset |
| `trace` | Lo que muestra el panel «API en vivo»: SoQL, ms y filas |
| `context_patch` | Cambios al estado canónico (filtros confirmados, sedes seleccionadas) |

Los textos que vienen de la fuente (nombres, direcciones) son **datos, nunca instrucciones**:
van en campos delimitados y no se obedece nada que contengan.

### Catálogo de `warnings`

`CUTOFF_2022` (datos con corte 2022-11-05) · `ROWS_ARE_CAPACITY_CATEGORIES` · `LEVEL_MISSING_MOSTLY`
(89% de las IPS sin nivel) · `DISTRICT_AS_DEPARTMENT` (Cali, Barranquilla, Cartagena, Santa Marta y
Buenaventura figuran como «departamentos» aparte) · `MIXED_TYPES` · `SITE_CODES_NOT_PHYSICAL_SITES` ·
`NOT_AVAILABILITY` (capacidad instalada, no disponibilidad) · `NULL_NOT_ZERO` · `PARTIAL_RESULT` ·
`STALE_CACHE` · `FILTER_NORMALIZED` (p. ej. «Valle del Cauca» → «Valle del cauca») · *(.3)*
`DERIVED_FROM_SOURCE` (porcentajes, diferencias y razones calculados a partir de la fuente) ·
`NOT_PER_CAPITA` (cifras absolutas; la fuente no trae población).

## 6. Caché

En memoria, por instancia (sin base de datos). Clave: operación + filtros validados y
normalizados + campos + página + corte. **Fresca 60 s**; «Reconsultar» siempre va en vivo
(`force_live`). *Cambio del 2026-10-09 (latencia, R-30):* la primera consulta de una sesión **ya
no** se fuerza en vivo: puede salir de la precarga hecha al conectar (≤ 60 s, misma SoQL), rotulada
`fresh` en el panel. La conexión a la fuente ya se demostró en vivo con el brief al conectar. Una entrada vencida solo se sirve **si la fuente falla**, hasta
24 h, rotulada `stale` con `STALE_CACHE`. No se cachean resultados fallidos, parciales ni
ambiguos. La edad de la consulta y el corte de la fuente son cosas distintas y ambas se muestran.
Nunca se presenta una caché como consulta en vivo.

## 7. Léxico y normalización

`data/lexicon.json` *(planeado)*, generado con `scripts/build_lexicon.py` desde la propia API
(consultas agrupadas): 38 valores de departamento, 1.027 municipios con su departamento, los
9.320 nombres de prestador con municipio, y los grupos y tipos de capacidad. Guarda `built_at`
y `source_cutoff`; se reconstruye antes de la demo. **Solo normaliza nombres y propone
candidatos; nunca es fuente de cifras** (R-22).

- Forma normalizada: minúsculas, sin acentos, sin puntuación («E.S.E.» = «ESE» = «empresa social del estado»).
- Coincidencia exacta normalizada → si no, similitud de trigramas con `difflib` de la biblioteca estándar (sin dependencias nuevas, R-10) con umbral a calibrar con las pruebas; **≤ 3 candidatos**.
- Un candidato incierto **se confirma** con el usuario; un homónimo sin departamento se pregunta (A-04, A-19, A-26).
- Un filtro corregido se anota en `warnings` (`FILTER_NORMALIZED`).

## 8. Brief en vivo (`GET /dataset/brief`)

Se pide al conectar y sirve de calentamiento. Tres consultas: (1) `count(*)`, prestadores y códigos de sede en una sola consulta, **primero, para calentar la conexión**; luego (2) prestadores por naturaleza y (3) top departamentos por prestadores **en paralelo** (G3: lanzar las tres a la vez abre tres conexiones en frío y tarda más).

```json
{
  "title": "Relación de IPS públicas y privadas según el nivel de atención y capacidad instalada",
  "source": { "name": "MinSalud — REPS", "license": "CC BY-SA 4.0", "cutoff_raw": "…", "cutoff_date": "2022-11-05", "url": "…" },
  "stats": { "rows": 41427, "providers": 9320, "site_codes": 10921, "fetched_at": "…", "ms": 612 },
  "limits": ["Capacidad instalada, no disponibilidad", "Sin geolocalización", "Nivel vacío en la mayoría de las IPS"],
  "suggested_questions": ["…", "…", "…"],
  "spoken_brief": "…",
  "trace": [ { "soql": "…", "ms": 323, "rows": 1 } ]
}
```

`suggested_questions` (3–5) salen de plantillas sobre las cifras en vivo, y **siempre se pueden
contestar con las herramientas**: «¿Cuántas IPS públicas, privadas y mixtas hay?», «¿Cuántas IPS
públicas hay en {departamento con más IPS}?», «¿Cuántas camas de adultos hay en total?»,
«Busca hospitales San José en {departamento}», «¿Qué municipios tienen más camas?».

`spoken_brief` (≤ 20 s, ≈ 50 palabras): *«Soy un asistente de inteligencia artificial. Consulto en vivo el registro de IPS del
Ministerio de Salud, con corte a noviembre de 2022: {n} prestadores y {m} códigos de sede.
Pregúntame, por ejemplo: {q1}, {q2} o {q3}.»* Incluye el aviso de IA (R-26, A-25).

## 9. Números dorados y trampas (consulta del 2026-10-09 ≈ 10:10, SODA3 anónimo y SODA2)

Sirven de **respuestas esperadas revisadas** para A-05 y compañía. Valen solo para esta versión
de la fuente; si el corte cambia, se vuelven a medir.

| Medida | Valor |
|---|---|
| Filas (categorías de capacidad) | 41.427 |
| Prestadores (IPS) distintos | **9.320** — Privada 8.308 · Pública 998 · Mixta 14 |
| Códigos de sede distintos | **10.921** — Privada 9.632 · Pública 1.274 · Mixta 15 |
| Municipios · valores de `departamento` | 1.027 nombres (1.113 pares municipio–departamento; 67 nombres homónimos) · 38 |
| Filas por naturaleza | Privada 25.067 · Pública 16.174 · Mixta 186 |
| IPS por nivel registrado | sin nivel **8.325** · 1 → 853 · 2 → 113 · 3 → 29 (suman 9.320) · filas sin nivel: 25.266 (61%) |
| Capacidad por grupo (filas / suma) | CONSULTORIOS 16.053 / 70.881 · SALAS 7.597 / 12.987 · **CAMAS 6.738 / 97.036** · AMBULANCIAS 5.340 / 5.340 · CAMILLAS 4.409 / 21.174 · UNIDAD MOVIL 694 / 694 · SILLAS 596 / 11.646 |
| Top municipios por camas | Bogotá 16.193 · Medellín 6.280 · Cali 5.876 · Barranquilla 4.761 · Cartagena 3.687 |
| Antioquia (IPS) | Privada 708 · Pública nivel 1 → 109, nivel 2 → 13, nivel 3 → 3 · Mixta 4 |

**Trampas que las herramientas deben absorber:**

1. `departamento` mezcla **distritos** con departamentos: Barranquilla, Buenaventura, Cali, Cartagena y Santa Marta aparecen como «departamentos» aparte; «Valle del Cauca» (escrito «Valle del cauca») **no incluye** Cali ni Buenaventura. Bogotá se escribe «Bogotá D.C».
2. Mayúsculas y acentos irregulares: municipios en mayúsculas («MEDELLÍN», «BOGOTÁ»), departamentos en formato mixto.
3. `num_nivel_atencion` vacío en el 89% de las IPS; en agrupaciones llega **sin clave**.
4. Contar filas ≠ contar IPS ≠ contar sedes; en ambulancias, 1 fila = 1 unidad.
5. Todo número llega como texto; los códigos y `n_mero_sede` son texto con ceros a la izquierda.
6. La fuente describe capacidad **instalada** en 2022: ninguna respuesta afirma disponibilidad actual ni cercanía.

## 10. Datos de contacto y privacidad

`gerente`, `email`, `tel_fono`, `direcci_n`, NIT y dígito de verificación **no se devuelven
por defecto**; solo con `include_contact = true` cuando el usuario lo pide de forma explícita, y
se dicen como dato histórico del REPS con su corte. No se afirman citas, traslados ni
recomendaciones médicas. Ningún dato de la fuente se trata como instrucción.

## 11. Estados y recuperación (R-25)

| Situación | `status` | Respuesta |
|---|---|---|
| 200 sin filas | `empty` | Lo dice y ofrece ampliar un filtro concreto |
| Varias coincidencias | `ambiguous` | ≤ 3 candidatos y una pregunta corta |
| Timeout, 5xx o conexión | `unavailable` tras **1** reintento | Caché etiquetada si existe la clave exacta; si no, «no disponible» |
| 429 | `unavailable` (`RATE_LIMITED`) | `Retry-After` solo si cabe en el plazo |
| 403 con token inválido | — | Se descarta el token y se reintenta **una vez** sin él |
| Argumentos inválidos | `invalid` + `error.hint` | El modelo corrige (máx. 2 intentos por turno) |
| Estado obsoleto | `invalid` (`STATE_CONFLICT`) | El cliente refresca el contexto |

Plazo de primer plano común: 6 s ([10](10-modelos-afecto-y-recuperacion.md) §5).

## 12. Pruebas

Sin red en la suite por defecto (R-16): **fixtures** a partir de
[`sdd_ips/evidence/socrata_probe.json`](sdd_ips/evidence/socrata_probe.json) (incluye filas
repetidas de un mismo prestador) más fixtures sintéticos para Mixta, nivel vacío, cantidad nula,
varias sedes y cambio de corte. Se prueban: constructores de consulta y escape, normalización y
ambigüedad, sobre de evidencia, mapeo de estados y el grupo sin clave. Las sondas en vivo viven
en `tests/live/` con la marca `live` y **no** corren por defecto. Mapa a escenarios: A-03…A-09,
A-12, A-18, A-19, A-24, A-26 ([07](07-reto-01-especificacion.md) §7).
