# Bench de latencia con consulta — 2026-10-09

Generado por `scripts/bench_models.py` (R-29, [07](../07-reto-01-especificacion.md) §8: primer
audio útil con consulta p95 ≤ 4,0 s; reconocimiento previo ≤ 1,0 s, se mide aparte).

**Método.** Cada pregunta se sintetiza una vez con OpenAI TTS (`gpt-4o-mini-tts`, voz `ash`,
PCM16 24 kHz; 16 kHz para Gemini por remuestreo lineal) y se envía por el WebSocket del
proveedor en tramas de 20 ms a ritmo de reloj, seguida de silencio (micrófono abierto) hasta que
termina el turno. Credencial, sesión y herramientas pasan por el backend local
(`POST /sessions`, `POST /realtime/session`, `POST /tools/{name}`), como el navegador. Tiempos en
ms con reloj monótono del cliente desde **t0 = envío del último fragmento con voz**. La salida
de la función es `{status, for_model, data, warnings}`. Sin reproducción de audio ni eco: la
latencia de reproducción del navegador no está incluida. p95 por rango más cercano: con n = 10
es el peor caso. Desde un equipo en Colombia, servidor local (no Vercel).

## before · openai · `gpt-realtime-2.1` · 2026-10-09T17:44:23Z

- Commit: `46a8805 test(bench): arnes de latencia con consulta para ambos motores de voz (R-29)` · prompt `reto01-ips-v2` · overrides: `ninguno`
- Turn detection: `{"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 500, "create_response": true, "interrupt_response": true}`
- n = 10 preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: True
- (a) medido con: speech_stopped
- Herramientas `unavailable`: 1

| Métrica (ms desde t0) | p50 | p95 | n |
|---|---|---|---|
| (a) fin de voz detectado | 1048 | 4562 | 10 |
| (b) decisión de herramienta | 6618 | 9699 | 10 |
| (c) POST /tools ida y vuelta (ms) | 945 | 6020 | 10 |
| (c) trace.ms de la fuente | 867 | 1946 | 10 |
| reconocimiento previo: primer audio | 1765 | 5761 | 10 |
| reconocimiento previo: duración | 17550 | 23600 | 10 |
| **(d) primer audio útil** (llegada) | 8973 | 13885 | 10 |
| (d') audible si el reconocimiento suena completo | 21361 | 25095 | 10 |
| turno completo | 11824 | 16665 | 10 |
| emitir credencial (ms) | 1148 | 3185 | 10 |
| abrir WebSocket (ms) | 1286 | 3439 | 10 |

| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |
|---|---|---|---|---|---|---|
| live | 10 | 8973 | 13885 | 21361 | 25095 | 945 |

<details><summary>Por turno</summary>

| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |
|---|---|---|---|---|---|---|---|---|
| q01 | 927 | 6205 | 1562/1558 | 1581 (16850) | 8806 | aggregate_ips(ok,live) | ¿Cuántas IPS hay en Colombia? | [pre] Soy una IA y puedo consultar en vivo el REPS del Ministerio de Salud, corte noviembre de 2022, para contar IPS, sedes y capacidad instalada, además de bus |
| q02 | 1046 | 5306 | 1430/1426 | 1956 (15200) | 8065 | aggregate_ips(ok,live) | ¿Cuántas camas hay en total? | [pre] Soy una IA y puedo consultar en datos.gov.co, corte de noviembre de 2022, el número de IPS, sedes y su capacidad instalada, como camas, salas o consultori |
| q03 | 1131 | 5973 | 1954/1946 | 1953 (17550) | 8973 | aggregate_ips(ok,live) | ¿Cuántas IPS públicas hay en Antioquia? | [pre] Soy una IA y puedo consultar, en el REPS de datos.gov.co con corte a noviembre de 2022, cuántos prestadores hay, cuántas sedes y algunos datos de capacida |
| q04 | 1296 | 6618 | 551/543 | 1927 (20000) | 8447 | aggregate_ips(ok,live) | ¿Qué municipios tienen más camas? | [pre] Soy una IA y puedo consultar en el dataset del REPS en datos.gov.co, corte 5 de noviembre de 2022, cosas como cuántas IPS o sedes hay y su capacidad insta |
| q05 | 1166 | 6668 | 6020/0 | 1748 (23300) | 13885 | aggregate_ips(unavailable,live) | ¿Cuántas IPS privadas hay en Bogotá? | [pre] Soy una IA que consulta en vivo la «Relación de IPS públicas y privadas según el nivel de atención y capacidad instalada» del REPS en datos.gov.co, corte  |
| q06 | 4562 | 9699 | 945/939 | 5761 (15600) | 11827 | aggregate_ips(ok,live) | ¿Cuántos códigos de sede hay en Cali? | [pre] Soy una IA y puedo consultar en datos.gov.co, corte de noviembre de 2022, cuántas IPS hay, cuántos códigos de sede tienen y su capacidad instalada. Déjame |
| q07 | 986 | 7082 | 876/867 | 1495 (23600) | 9348 | aggregate_ips(ok,live) | ¿Cuántas ambulancias hay en Santander? | [pre] Soy una inteligencia artificial y puedo consultar, directamente en datos.gov.co, la Relación de IPS públicas y privadas del REPS, corte del 5 de noviembre |
| q08 | 1048 | 7396 | 1641/1634 | 1765 (21400) | 10037 | aggregate_ips(ok,live) | ¿Cuántas IPS de nivel tres hay? | [pre] Soy una IA que consulta en vivo la base “Relación de IPS públicas y privadas según nivel de atención y capacidad instalada” del REPS, corte de noviembre d |
| q09 | 881 | 6941 | 728/718 | 1492 (20500) | 9000 | aggregate_ips(ok,live) | ¿Cuántas camas de adultos hay en Medellín? | [pre] Soy una IA y puedo consultar en la fuente oficial REPS del Ministerio de Salud, corte de noviembre de 2022, datos sobre IPS, como número de prestadores o  |
| q10 | 1056 | 6564 | 765/758 | 2177 (17450) | 8395 | aggregate_ips(ok,live) | ¿Cuántas IPs mixtas hay? | [pre] Soy una IA y puedo consultar en datos.gov.co, corte de noviembre de 2022, cuántos prestadores hay, cuántas sedes y su capacidad instalada por grupos como  |

</details>

**Fallos (verbatim, R-29):**
- q05: tool aggregate_ips status=unavailable error=TIMEOUT (POST /tools 6020 ms; args {"metric": "provider_count", "filters": {"department": "Bogotá", "nature": "Privada"}}) — el modelo respondió sin cifra, como manda R-25

## before · gemini · `gemini-3.8-live` · 2026-10-09T17:48:53Z

- Commit: `46a8805 test(bench): arnes de latencia con consulta para ambos motores de voz (R-29)` · prompt `reto01-ips-v2` · overrides: `ninguno`
- Turn detection: `{"type": "server"}`
- n = 10 preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: True
- (a) medido con: first_msg:serverContent+inputTranscription, first_msg:usageMetadata
- Herramientas `unavailable`: 0

| Métrica (ms desde t0) | p50 | p95 | n |
|---|---|---|---|
| (a) fin de voz detectado | 1473 | 2458 | 10 |
| (b) decisión de herramienta | 4175 | 5801 | 10 |
| (c) POST /tools ida y vuelta (ms) | 753 | 1869 | 10 |
| (c) trace.ms de la fuente | 744 | 1860 | 10 |
| reconocimiento previo: primer audio | 1761 | 2513 | 10 |
| reconocimiento previo: duración | 10990 | 16500 | 10 |
| **(d) primer audio útil** (llegada) | 13361 | 18821 | 10 |
| (d') audible si el reconocimiento suena completo | 13361 | 18821 | 10 |
| turno completo | 21195 | 28776 | 10 |
| emitir credencial (ms) | 757 | 1461 | 10 |
| abrir WebSocket (ms) | 568 | 1106 | 10 |

| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |
|---|---|---|---|---|---|---|
| live | 10 | 13361 | 18821 | 13361 | 18821 | 753 |

<details><summary>Por turno</summary>

| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |
|---|---|---|---|---|---|---|---|---|
| q01 | 1750 | 4788 | 1869/1860 | 1897 (13530) | 16083 | aggregate_ips(ok,live) | ¿Cuántas IPS hay en Colombia? | [pre] Hola, soy tu asistente de inteligencia artificial. Contamos con los datos del Ministerio de Salud, con corte a noviembre de 2022, sobre la capacidad insta |
| q02 | 2458 | 5449 | 710/701 | 2513 (15530) | 18769 | aggregate_ips(ok,live) | ¿Cuántas camas hay en total? | [pre] Hola, soy tu asistente de inteligencia artificial. Conmigo puedes consultar el total de sedes, prestadores o capacidad instalada de IPS, como camas o sala |
| q03 | 1356 | 5801 | 753/744 | 1816 (16500) | 18821 | aggregate_ips(ok,live) | ¿Cuántas IPS públicas hay en Antioquia? | [pre] Hola. Soy tu asistente de inteligencia artificial. Puedo consultar información sobre la capacidad instalada y características de las IPS públicas y privad |
| q04 | 1244 | 3988 | 951/946 | 1590 (10340) | 12633 | aggregate_ips(ok,live) | ¿Qué municipios tienen más camas? | [pre] Hola, soy tu asistente de IA. Puedo consultar datos sobre capacidad instalada y niveles de atención de las IPS. Déjame verificarlo en datos.gov.co. [post] |
| q05 | 1418 | 1847 | 652/644 | 1430 (2330) | 4322 | aggregate_ips(ok,live) | ¿Cuántas IPS privadas hay en Bogotá? | [pre] Déjame verificarlo en datos.gov.co. [post] En Bogotá hay mil doscientas sesenta IPS privadas registradas, según el corte de noviembre de dos mil veintidós |
| q06 | 1551 | 4241 | 594/588 | 1821 (11150) | 14197 | aggregate_ips(ok,live) | ¿Cuántos códigos de sede hay en Cali? | [pre] Hola. Soy tu asistente de IA y puedo consultarte la cantidad de sedes o la capacidad instalada de las IPS públicas y privadas. Déjame verificarlo en datos |
| q07 | 1473 | 2110 | 1210/1201 | 1480 (2920) | 5187 | aggregate_ips(ok,live) | ¿Cuántas ambulancias hay en Santander? | [pre] Déjame verificarlo en datos.gov.co. [post] Según los datos registrados al cinco de noviembre de dos mil veintidós, en Santander hay trescientas treinta y  |
| q08 | 1506 | 4175 | 912/905 | 1545 (10990) | 13361 | aggregate_ips(ok,live) | ¿Cuántas IPS de nivel 3 hay? | [pre] Hola, soy tu asistente de IA. Puedo consultar información sobre prestadores de salud, sedes y su capacidad instalada. Déjame verificarlo en datos.gov.co.  |
| q09 | 1498 | 5237 | 706/697 | 1936 (14410) | 16924 | aggregate_ips(ok,live) | ¿Cuántas camas de adultos hay en Medellín? | [pre] Hola. Soy tu asistente de IA y puedo consultarte información sobre la capacidad instalada y sedes de IPS públicas y privadas según los datos del Ministeri |
| q10 | 1313 | 2350 | 979/976 | 1761 (3070) | 6163 | aggregate_ips(ok,live) | ¿Cuántas IPS mixtas hay? | [pre] Déjame verificarlo en datos.gov.co. [post] Con corte al 5 de noviembre de 2022, hay 14 prestadores de naturaleza mixta registrados. |

</details>

**Fallos (verbatim, R-29):**
- ninguno
