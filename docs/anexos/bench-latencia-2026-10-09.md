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

## Resumen (n = 10 por fila, ms desde el fin de la voz, p50 / p95)

BEFORE = código `b8dd8aa` (prompt `reto01-ips-v2`). AFTER = merge hasta `19b8261` (prompt
`reto01-ips-v5`, conexión caliente, precarga, VAD y modelo configurables). «force_live» = como el
navegador de hoy (`controller.ts:63`, 1.ª consulta en vivo); «sin force_live» = contrato acordado
(docs/09 §6), **la fila que cuenta**, con 2 s entre `/realtime/session` y la voz.

| Corrida | (a) fin de voz | (b) herramienta | (c) /tools | reconoc. inicio · duración | **(d) útil** | (d') audible | fresh | fallos |
|---|---|---|---|---|---|---|---|---|
| BEFORE OpenAI 2.1 | 1048 / 4562 | 6618 / 9699 | 945 / 6020 | 1765 · 17550 | 8973 / 13885 | 21361 / 25095 | 0/10 | 1 TIMEOUT |
| BEFORE Gemini 3.8 | 1473 / 2458 | 4175 / 5801 | 753 / 1869 | 1761 · 10990 | 13361 / 18821 | 13361 / 18821 | 0/10 | 0 |
| AFTER OpenAI 2.1 force_live | 940 / 1483 | 2011 / 2689 | 710 / 1370 | 1594 · 950 | 3616 / 4818 | 3616 / 4818 | 0/10 | 0 (1 ambiguous) |
| AFTER Gemini force_live | 979 / 1359 | 1722 / 2284 | 634 / 5538 | 1419 · 770 | 3427 / 15619 | 3427 / 15619 | 0/10 (1 stale) | 0 |
| **AFTER OpenAI 2.1** | 948 / 1228 | 1885 / 2556 | 644 / 1178 | 1627 · 1050 | **3935 / 4709** | 3935 / 4709 | 2/10 | 0 |
| **AFTER Gemini 3.8** | 1061 / 4075 | 1921 / 4353 | 732 / 1467 | 1615 · 780 | **4175 / 6933** | 4175 / 6933 | 2/10 | 0 (1 ambiguous) |
| AFTER OpenAI `gpt-realtime` | 966 / 1334 | 2343 / 2881 | 806 / 1527 | 1374 · 2450 | 3951 / 4483 | 4315 / 4935 | 2/10 | 0 (1 invalid) |
| AFTER OpenAI 2.1 silencio 300 | 757 / 1145 | 1814 / 1937 | 707 / 1614 | 1508 · 1000 | 3685 / 4554 | 3685 / 4554 | 2/10 | 0 |
| AFTER OpenAI 2.1 semantic_vad high | 1224 / 2882 | 2245 / 4220 | 754 / 1620 | 1943 · 1000 | 4481 / 6493 | 4481 / 6493 | 2/10 | 0 |

Con consulta «fresh» (precargada, `/tools` ≈ 3–9 ms) el primer audio útil queda en 2,3–3,7 s; con
«live» la fuente suma 0,5–1,6 s. **Ninguna corrida cumple p95 ≤ 4,0 s con n = 10**; las mejores
quedan a ~0,5 s. El reconocimiento previo («Un momento.», ~1 s de audio) empieza a ~1,4–1,9 s: no
cumple ≤ 1,0 s. Las variantes de OpenAI corrieron 3 en paralelo y las AFTER base 2 en paralelo
(OpenAI y Gemini a la vez).

**Lectura.** (1) La mejora grande (d p50 9,0 → 3,9 s en OpenAI; 13,4 → 4,2 s en Gemini) viene del
prompt v5: el aviso de IA largo antes de la herramienta (11–24 s de audio) desaparece. (2)
`gpt-realtime` no mejora a `2.1` (d p50 igual, p95 −0,2 s dentro del ruido) y su «Un momento.»
trae 2,5–3,3 s de audio, lo que retrasa el audible; además respondió a un `invalid` con «la fuente
no respondió», lo que no es cierto. (3) Silencio 300 ms adelanta el fin de voz ~190 ms (p50) y el
útil ~250 ms; **el bench no mide cortes**: el audio de TTS no tiene pausas a mitad de frase. (4)
`semantic_vad` con `high` es más lento y más variable (fin de voz p95 2,9 s): se descarta.

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

## after-forcelive · openai · `gpt-realtime-2.1` · 2026-10-09T17:53:04Z

- Commit: `8df29b7 Merge commit '19b8261' into feat/reto-01-api-bench` · prompt `reto01-ips-v5` · overrides: `ninguno`
- Turn detection: `{"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 500, "create_response": true, "interrupt_response": true}`
- n = 10 preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: True; espera tras /realtime/session antes de hablar: 2.0 s
- (a) medido con: speech_stopped
- Herramientas `unavailable`: 0

| Métrica (ms desde t0) | p50 | p95 | n |
|---|---|---|---|
| (a) fin de voz detectado | 940 | 1483 | 10 |
| (b) decisión de herramienta | 2011 | 2689 | 10 |
| (c) POST /tools ida y vuelta (ms) | 710 | 1370 | 10 |
| (c) trace.ms de la fuente | 701 | 1365 | 10 |
| reconocimiento previo: primer audio | 1594 | 2213 | 10 |
| reconocimiento previo: duración | 950 | 1150 | 10 |
| **(d) primer audio útil** (llegada) | 3616 | 4818 | 10 |
| (d') audible si el reconocimiento suena completo | 3616 | 4818 | 10 |
| turno completo | 5047 | 15139 | 10 |
| emitir credencial (ms) | 997 | 2320 | 10 |
| abrir WebSocket (ms) | 1197 | 2473 | 10 |

| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |
|---|---|---|---|---|---|---|
| live | 10 | 3616 | 4818 | 3616 | 4818 | 710 |

<details><summary>Por turno</summary>

| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |
|---|---|---|---|---|---|---|---|---|
| q01 | 1483 | 2205 | 604/591 | 1890 (950) | 3616 | aggregate_ips(ok,live) | ¿Cuántas IPS hay en Colombia? | [pre] Un momento. [post] 9.320 prestadores, según el REPS de 2022; soy un asistente de IA. |
| q02 | 911 | 2011 | 1370/1365 | 1639 (900) | 4818 | aggregate_ips(ok,live) | ¿Cuántas camas hay en total? | [pre] Un momento. [post] 97.036 camas, según el REPS de 2022. |
| q03 | 917 | 1901 | 742/732 | 1628 (1000) | 3761 | aggregate_ips(ok,live) | ¿Cuántas IPS públicas hay en Antioquia? | [pre] Un momento. [post] 125 prestadores, según el REPS de 2022. |
| q04 | 969 | 2198 | 803/795 | 1594 (950) | 4206 | aggregate_ips(ok,live) | ¿Qué municipios tienen más camas? | [pre] Un momento. [post] 16.193 camas en Bogotá, 6.280 en Medellín y 5.876 en Cali, según el REPS de 2022; soy un asistente de IA. |
| q05 | 1188 | 2649 | 4/0 | 2143 (1100) | 3607 | aggregate_ips(ambiguous,live) | ¿Cuántas IPS privadas hay en Bogotá? | [pre] Un momento. [post] ¿De qué departamento es ese municipio? La opción que aparece es Bogotá, Bogotá D.C. |
| q06 | 940 | 1762 | 710/701 | 1525 (1050) | 3433 | aggregate_ips(ok,live) | ¿Cuántos códigos de sede hay en Cali? | [pre] Un momento. [post] 491 códigos de sede, según el REPS de 2022. Soy un asistente de IA. |
| q07 | 941 | 2014 | 575/570 | 1566 (900) | 3804 | aggregate_ips(ok,live) | ¿Cuántas ambulancias hay en Santander? | [pre] Un momento. [post] 337 ambulancias, según el REPS de 2022. Soy un asistente de IA. |
| q08 | 897 | 1637 | 1153/1138 | 1307 (1050) | 3500 | aggregate_ips(ok,live) | ¿Cuántas IPS de nivel tres hay? | [pre] Un momento. [post] 29 prestadores, según el REPS de 2022. Soy un asistente de IA. |
| q09 | 934 | 2689 | 560/556 | 2213 (1150) | 4388 | aggregate_ips(ok,live) | ¿Cuántas camas de adultos hay en Medellín? | [pre] Un momento. [post] 3.853 camas según el REPS de 2022. |
| q10 | 1125 | 1759 | 713/708 | 1478 (950) | 3448 | aggregate_ips(ok,live) | ¿Cuántas IPSes mixtas hay? | [pre] Un momento. [post] 14 prestadores, según el REPS de 2022; soy un asistente de IA. |

</details>

**Fallos (verbatim, R-29):**
- ninguno

## after-forcelive · gemini · `gemini-3.8-live` · 2026-10-09T17:53:49Z

- Commit: `8df29b7 Merge commit '19b8261' into feat/reto-01-api-bench` · prompt `reto01-ips-v5` · overrides: `ninguno`
- Turn detection: `{"type": "server"}`
- n = 10 preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: True; espera tras /realtime/session antes de hablar: 2.0 s
- (a) medido con: first_msg:serverContent+inputTranscription
- Herramientas `unavailable`: 0

| Métrica (ms desde t0) | p50 | p95 | n |
|---|---|---|---|
| (a) fin de voz detectado | 979 | 1359 | 10 |
| (b) decisión de herramienta | 1722 | 2284 | 10 |
| (c) POST /tools ida y vuelta (ms) | 634 | 5538 | 10 |
| (c) trace.ms de la fuente | 618 | 820 | 10 |
| reconocimiento previo: primer audio | 1419 | 1881 | 10 |
| reconocimiento previo: duración | 770 | 1030 | 10 |
| **(d) primer audio útil** (llegada) | 3427 | 15619 | 10 |
| (d') audible si el reconocimiento suena completo | 3427 | 15619 | 10 |
| turno completo | 10745 | 21907 | 10 |
| emitir credencial (ms) | 971 | 2711 | 10 |
| abrir WebSocket (ms) | 579 | 1576 | 10 |

| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |
|---|---|---|---|---|---|---|
| live | 9 | 3427 | 3808 | 3427 | 3808 | 634 |
| stale | 1 | 15619 | 15619 | 15619 | 15619 | 5538 |

<details><summary>Por turno</summary>

| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |
|---|---|---|---|---|---|---|---|---|
| q01 | 1359 | 2284 | 826/820 | 1881 (870) | 3808 | aggregate_ips(ok,live) | ¿Cuántas IPS hay en Colombia? | [pre] Un momento. [post] 9.320 IPS hay en Colombia, según el REPS de 2022, y soy un asistente de IA. |
| q02 | 1027 | 1969 | 5538/0 | 1485 (680) | 15619 | aggregate_ips(ok,stale) | ¿Cuántas camas hay en total? | [pre] Un momento. [post] 97.036 camas hay en total, según el REPS de 2022, y soy un asistente de IA. |
| q03 | 864 | 1689 | 629/618 | 1265 (1000) | 3201 | aggregate_ips(ok,live) | ¿Cuántas IPS públicas hay en Antioquia? | [pre] Un momento. [post] 125 prestadores son IPS públicas en Antioquia, según el REPS de 2022. Como soy un asistente de IA, me baso exclusivamente en esta fuent |
| q04 | 893 | 1622 | 638/631 | 1419 (980) | 3217 | aggregate_ips(ok,live) | ¿Qué municipios tienen más camas? | [pre] Un momento. [post] Bogotá tiene 16.193 camas, Medellín tiene 6.280 y Cali tiene 5.876, según el REPS de 2022. Soy un asistente de IA. |
| q05 | 979 | 1607 | 662/655 | 1397 (770) | 3171 | aggregate_ips(ok,live) | ¿Cuántas IPS privadas hay en Bogotá? | [pre] Un momento. [post] 1.260 prestadores privados hay en Bogotá, según el REPS de 2022, y soy un asistente de IA. |
| q06 | 1141 | 1974 | 568/558 | 1846 (770) | 3544 | aggregate_ips(ok,live) | ¿Cuántos códigos de sede hay en Cali? | [pre] Un momento. [post] 491 códigos de sede hay en Cali, según el REPS de 2022, y soy un asistente de IA. |
| q07 | 1035 | 1843 | 657/649 | 1668 (1030) | 3471 | aggregate_ips(ok,live) | ¿Cuántas ambulancias hay en Santander? | [pre] Un momento. [post] 337 ambulancias hay en Santander, según el REPS de 2022. Como soy un asistente de IA, te informo que esta información proviene de la ba |
| q08 | 925 | 1789 | 212/204 | 1605 (750) | 3596 | aggregate_ips(ok,live) | ¿Cuántas IPS de nivel 3 hay? | [pre] Un momento. [post] 29 prestadores de nivel tres hay, según el REPS de 2022, y soy un asistente de IA. |
| q09 | 1040 | 1722 | 634/621 | 1293 (760) | 3427 | aggregate_ips(ok,live) | ¿Cuántas camas de adultos hay en Medellín? | [pre] Un momento. [post] Como asistente de IA, te informo que hay 3.853 camas de adultos en Medellín según el REPS de 2022. |
| q10 | 912 | 1380 | 602/593 | 1068 (760) | 3002 | aggregate_ips(ok,live) | ¿Cuántas IPS mixtas hay? | [pre] Un momento. [post] 14 prestadores hay en total, según el REPS de 2022, y soy un asistente de IA. |

</details>

**Fallos (verbatim, R-29):**
- ninguno

## after · openai · `gpt-realtime-2.1` · 2026-10-09T17:56:00Z

- Commit: `8df29b7 Merge commit '19b8261' into feat/reto-01-api-bench` · prompt `reto01-ips-v5` · overrides: `ninguno`
- Turn detection: `{"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 500, "create_response": true, "interrupt_response": true}`
- n = 10 preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: False; espera tras /realtime/session antes de hablar: 2.0 s
- (a) medido con: speech_stopped
- Herramientas `unavailable`: 0

| Métrica (ms desde t0) | p50 | p95 | n |
|---|---|---|---|
| (a) fin de voz detectado | 948 | 1228 | 10 |
| (b) decisión de herramienta | 1885 | 2556 | 10 |
| (c) POST /tools ida y vuelta (ms) | 644 | 1178 | 10 |
| (c) trace.ms de la fuente | 636 | 1174 | 10 |
| reconocimiento previo: primer audio | 1627 | 2129 | 10 |
| reconocimiento previo: duración | 1050 | 1100 | 10 |
| **(d) primer audio útil** (llegada) | 3935 | 4709 | 10 |
| (d') audible si el reconocimiento suena completo | 3935 | 4709 | 10 |
| turno completo | 4663 | 7053 | 10 |
| emitir credencial (ms) | 1065 | 2671 | 10 |
| abrir WebSocket (ms) | 1050 | 4344 | 10 |

| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |
|---|---|---|---|---|---|---|
| fresh | 2 | 2423 | 2612 | 2423 | 2612 | 9 |
| live | 8 | 4070 | 4709 | 4070 | 4709 | 718 |

<details><summary>Por turno</summary>

| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |
|---|---|---|---|---|---|---|---|---|
| q01 | 979 | 1708 | 9/0 | 1552 (1050) | 2612 | aggregate_ips(ok,fresh) | ¿Cuántas IPS hay en Colombia? | [pre] Un momento. [post] 9.320 prestadores según el REPS de 2022, soy un asistente de IA. |
| q02 | 929 | 1725 | 9/0 | 1414 (1000) | 2423 | aggregate_ips(ok,fresh) | ¿Cuántas camas hay en total? | [pre] Un momento. [post] 97.036 camas según el REPS de 2022. |
| q03 | 907 | 2556 | 597/586 | 2129 (1050) | 4709 | aggregate_ips(ok,live) | ¿Cuántas IPS públicas hay en Antioquia? | [pre] Un momento. [post] 125 prestadores según el REPS de 2022; soy un asistente de IA. |
| q04 | 955 | 2240 | 530/527 | 1703 (1050) | 4070 | aggregate_ips(ok,live) | ¿Qué municipios tienen más camas? | [pre] Un momento. [post] 16.193 camas en Bogotá, 6.280 en Medellín (Antioquia) y 5.876 en Cali, según el REPS de 2022. |
| q05 | 900 | 1572 | 644/636 | 1275 (950) | 3106 | aggregate_ips(ok,live) | ¿Cuántas IPS privadas hay en Bogotá? | [pre] Un momento. [post] 1.260 prestadores, según el REPS de 2022. Soy un asistente de IA. |
| q06 | 864 | 1808 | 718/713 | 1532 (1100) | 3642 | aggregate_ips(ok,live) | ¿Cuántos códigos de sede hay en Cali? | [pre] Un momento. [post] 491 códigos de sede, según el REPS de 2022. |
| q07 | 948 | 2098 | 848/843 | 1627 (1050) | 3935 | aggregate_ips(ok,live) | ¿Cuántas ambulancias hay en Santander? | [pre] Un momento. [post] 337 ambulancias, según el REPS de 2022. |
| q08 | 973 | 1885 | 1025/1012 | 1641 (850) | 4282 | aggregate_ips(ok,live) | ¿Cuántas IPS de nivel 3 hay? | [pre] Un momento. [post] 29 prestadores según el REPS de 2022; soy un asistente de IA. |
| q09 | 1228 | 2446 | 732/718 | 1740 (1050) | 4075 | aggregate_ips(ok,live) | ¿Cuántas camas de adultos hay en Medellín? | [pre] Un momento. [post] 3.853 camas, según el REPS de 2022. |
| q10 | 1100 | 2063 | 1178/1174 | 1886 (1100) | 4467 | aggregate_ips(ok,live) | ¿Cuántas IPs mixtas hay? | [pre] Un momento. [post] 14 prestadores según el REPS de 2022; soy un asistente de IA. |

</details>

**Fallos (verbatim, R-29):**
- ninguno

## after · gemini · `gemini-3.8-live` · 2026-10-09T17:57:04Z

- Commit: `8df29b7 Merge commit '19b8261' into feat/reto-01-api-bench` · prompt `reto01-ips-v5` · overrides: `ninguno`
- Turn detection: `{"type": "server"}`
- n = 10 preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: False; espera tras /realtime/session antes de hablar: 2.0 s
- (a) medido con: first_msg:serverContent+inputTranscription, first_msg:usageMetadata
- Herramientas `unavailable`: 0

| Métrica (ms desde t0) | p50 | p95 | n |
|---|---|---|---|
| (a) fin de voz detectado | 1061 | 4075 | 10 |
| (b) decisión de herramienta | 1921 | 4353 | 10 |
| (c) POST /tools ida y vuelta (ms) | 732 | 1467 | 10 |
| (c) trace.ms de la fuente | 723 | 1455 | 10 |
| reconocimiento previo: primer audio | 1615 | 4271 | 10 |
| reconocimiento previo: duración | 780 | 1060 | 10 |
| **(d) primer audio útil** (llegada) | 4175 | 6933 | 10 |
| (d') audible si el reconocimiento suena completo | 4175 | 6933 | 10 |
| turno completo | 10758 | 21219 | 10 |
| emitir credencial (ms) | 695 | 1294 | 10 |
| abrir WebSocket (ms) | 531 | 611 | 10 |

| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |
|---|---|---|---|---|---|---|
| fresh | 2 | 3318 | 4175 | 3318 | 4175 | 3 |
| live | 8 | 4203 | 6933 | 4203 | 6933 | 797 |

<details><summary>Por turno</summary>

| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |
|---|---|---|---|---|---|---|---|---|
| q01 | 933 | 1933 | 8/0 | 1627 (1060) | 3318 | aggregate_ips(ok,fresh) | ¿Cuántas IPS hay en Colombia? | [pre] Un momento. [post] 9.320 prestadores hay, además de ser yo un asistente de IA, según el REPS de 2022. |
| q02 | 1065 | 1792 | 3/0 | 1600 (1050) | 4175 | aggregate_ips(ok,fresh) | ¿Cuántas camas hay en total? | [pre] Un momento. [post] 97.036 camas hay en total, siendo yo un asistente de IA, según el REPS de 2022. |
| q03 | 1061 | 1983 | 602/595 | 1680 (1040) | 3431 | aggregate_ips(ok,live) | ¿Cuántas IPS públicas hay en Antioquia? | [pre] Un momento. [post] 125 prestadores son públicos en Antioquia, según el REPS de 2022, y soy un asistente de IA. |
| q04 | 4075 | 4353 | 1445/1436 | 4271 (1050) | 6933 | aggregate_ips(ok,live) | ¿Qué municipios tienen más camas? | [pre] Un momento. [post] Bogotá tiene 16.193 camas, Medellín tiene 6.280 camas y Cali tiene 5.876 camas, según el REPS de 2022, y aclaro que soy un asistente de |
| q05 | 931 | 2207 | 797/789 | 2045 (800) | 4203 | aggregate_ips(ok,live) | ¿Cuántas IPS privadas hay en Bogotá? | [pre] Un momento. [post] Hay 1.260 prestadores de IPS privadas en Bogotá, según el REPS de 2022, y soy un asistente de IA. |
| q06 | 1090 | 1674 | 1458/1440 | 1362 (750) | 5896 | search_ips(ok,live); aggregate_ips(ok,live) | ¿Cuántos códigos de sede hay en Cali? | [pre] Un momento. [post] Un momento.491 códigos de sede hay en Cali, según el REPS de 2022, y soy un asistente de IA. |
| q07 | 1148 | 1768 | 732/723 | 1554 (780) | 3592 | aggregate_ips(ok,live) | ¿Cuántas ambulancias hay en Santander? | [pre] Un momento. [post] Hay 337 ambulancias en Santander, según el REPS de 2022, y soy un asistente de IA. |
| q08 | 1056 | 1921 | 1467/1455 | 1615 (760) | 4322 | aggregate_ips(ok,live) | ¿Cuántas IPS de nivel 3 hay? | [pre] Un momento. [post] 29 prestadores de nivel 3 hay, según el REPS de 2022, y soy un asistente de IA. |
| q09 | 1210 | 3012 | 7/0 | 2854 (760) | 4505 | aggregate_ips(ambiguous,live) | ¿Cuántas camas de adultos hay en Medellín? | [pre] Un momento. [post] ¿Te refieres a SPA Adultos? |
| q10 | 1037 | 1490 | 1072/1061 | 1079 (760) | 3570 | aggregate_ips(ok,live) | ¿Cuántas IPS mixtas hay? | [pre] Un momento. [post] Hay 14 prestadores mixtos según el REPS de 2022, siendo yo un asistente de IA. |

</details>

**Fallos (verbatim, R-29):**
- ninguno

## after-silence300 · openai · `gpt-realtime-2.1` · 2026-10-09T17:59:50Z

- Commit: `8df29b7 Merge commit '19b8261' into feat/reto-01-api-bench` · prompt `reto01-ips-v5` · overrides: `{"REALTIME_SILENCE_DURATION_MS": "300"}`
- Turn detection: `{"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 300, "create_response": true, "interrupt_response": true}`
- n = 10 preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: False; espera tras /realtime/session antes de hablar: 2.0 s
- (a) medido con: speech_stopped
- Herramientas `unavailable`: 0

| Métrica (ms desde t0) | p50 | p95 | n |
|---|---|---|---|
| (a) fin de voz detectado | 757 | 1145 | 10 |
| (b) decisión de herramienta | 1814 | 1937 | 10 |
| (c) POST /tools ida y vuelta (ms) | 707 | 1614 | 10 |
| (c) trace.ms de la fuente | 700 | 1610 | 10 |
| reconocimiento previo: primer audio | 1508 | 1865 | 10 |
| reconocimiento previo: duración | 1000 | 1150 | 10 |
| **(d) primer audio útil** (llegada) | 3685 | 4554 | 10 |
| (d') audible si el reconocimiento suena completo | 3685 | 4554 | 10 |
| turno completo | 4794 | 6979 | 10 |
| emitir credencial (ms) | 1017 | 1177 | 10 |
| abrir WebSocket (ms) | 1096 | 2057 | 10 |

| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |
|---|---|---|---|---|---|---|
| fresh | 2 | 2305 | 3188 | 2305 | 3188 | 3 |
| live | 8 | 3694 | 4554 | 3694 | 4554 | 720 |

<details><summary>Por turno</summary>

| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |
|---|---|---|---|---|---|---|---|---|
| q01 | 1145 | 1866 | 6/0 | 1865 (1000) | 3188 | aggregate_ips(ok,fresh) | ¿Cuántas IPS hay en Colombia? | [pre] Un momento. [post] 9.320 prestadores según el REPS de 2022; soy un asistente de IA. |
| q02 | 780 | 1575 | 3/0 | 1267 (900) | 2305 | aggregate_ips(ok,fresh) | ¿Cuántas camas hay en total? | [pre] Un momento. [post] 97.036 camas según el REPS de 2022; soy un asistente de IA. |
| q03 | 893 | 1814 | 878/870 | 1547 (1000) | 3731 | aggregate_ips(ok,live) | ¿Cuántas IPS públicas hay en Antioquia? | [pre] Un momento. [post] 125 prestadores, según el REPS de 2022. |
| q04 | 865 | 1859 | 1326/1319 | 1438 (1100) | 4204 | aggregate_ips(ok,live) | ¿Qué municipios tienen más camas? | [pre] Un momento. [post] 16.193 camas Bogotá, 6.280 Medellín y 5.876 Cali, según el REPS de 2022. |
| q05 | 659 | 1679 | 707/700 | 1515 (900) | 3694 | aggregate_ips(ok,live) | ¿Cuántas IPS privadas hay en Bogotá? | [pre] Un momento. [post] Mil doscientos sesenta prestadores, según el REPS de 2022. Soy un asistente de IA. |
| q06 | 738 | 1636 | 692/689 | 1397 (1050) | 3317 | aggregate_ips(ok,live) | ¿Cuántos códigos de sede hay en Cali? | [pre] Un momento. [post] 491 códigos de sede según el REPS de 2022. |
| q07 | 750 | 1704 | 720/717 | 1328 (900) | 3466 | aggregate_ips(ok,live) | ¿Cuántas ambulancias hay en Santander? | [pre] Un momento. [post] 337 ambulancias, según el REPS de 2022. |
| q08 | 757 | 1904 | 674/669 | 1806 (1100) | 3685 | aggregate_ips(ok,live) | ¿Cuántas IPS de nivel tres hay? | [pre] Un momento. [post] 29 prestadores, según el REPS de 2022. Soy un asistente de IA. |
| q09 | 730 | 1937 | 1614/1610 | 1508 (1150) | 4554 | aggregate_ips(ok,live) | ¿Cuántas camas de adultos hay en Medellín? | [pre] Un momento. [post] 3.853 camas según el REPS de 2022. Soy un asistente de IA. |
| q10 | 986 | 1876 | 814/806 | 1569 (950) | 3812 | aggregate_ips(ok,live) | ¿Cuántas IPSes mixtas hay? | [pre] Un momento. [post] 14 prestadores, según el REPS de 2022. Soy un asistente de IA. |

</details>

**Fallos (verbatim, R-29):**
- ninguno

## after-gpt-realtime · openai · `gpt-realtime` · 2026-10-09T17:59:50Z

- Commit: `8df29b7 Merge commit '19b8261' into feat/reto-01-api-bench` · prompt `reto01-ips-v5` · overrides: `{"VOICE_OPENAI_MODEL": "gpt-realtime"}`
- Turn detection: `{"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 500, "create_response": true, "interrupt_response": true}`
- n = 10 preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: False; espera tras /realtime/session antes de hablar: 2.0 s
- (a) medido con: speech_stopped
- Herramientas `unavailable`: 0

| Métrica (ms desde t0) | p50 | p95 | n |
|---|---|---|---|
| (a) fin de voz detectado | 966 | 1334 | 10 |
| (b) decisión de herramienta | 2343 | 2881 | 10 |
| (c) POST /tools ida y vuelta (ms) | 806 | 1527 | 10 |
| (c) trace.ms de la fuente | 798 | 1519 | 10 |
| reconocimiento previo: primer audio | 1374 | 1754 | 10 |
| reconocimiento previo: duración | 2450 | 3300 | 10 |
| **(d) primer audio útil** (llegada) | 3951 | 4483 | 10 |
| (d') audible si el reconocimiento suena completo | 4315 | 4935 | 10 |
| turno completo | 4866 | 5769 | 10 |
| emitir credencial (ms) | 1216 | 1542 | 10 |
| abrir WebSocket (ms) | 1118 | 3197 | 10 |

| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |
|---|---|---|---|---|---|---|
| fresh | 2 | 2868 | 3657 | 2868 | 3798 | 2 |
| live | 8 | 4118 | 4483 | 4419 | 4935 | 917 |

<details><summary>Por turno</summary>

| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |
|---|---|---|---|---|---|---|---|---|
| q01 | 1039 | 2214 | 6/0 | 1348 (2450) | 3657 | aggregate_ips(ok,fresh) | ¿Cuántas IPS hay en Colombia? | [pre] Un momento. [post] 9.320 prestadores, según el REPS de 2022. |
| q02 | 941 | 2194 | 2/0 | 1296 (800) | 2868 | aggregate_ips(ok,fresh) | ¿Cuántas camas hay en total? | [pre] Un momento. [post] 97.036 camas en total según el REPS de 2022. |
| q03 | 884 | 2488 | 1079/1070 | 1440 (3000) | 4357 | aggregate_ips(ok,live) | ¿Cuántas IPS públicas hay en Antioquia? | [pre] Un momento. [post] 125 IPS públicas en Antioquia, según el REPS de 2022. |
| q04 | 1334 | 2881 | 30/0 | 1754 (3150) | 3500 | aggregate_ips(invalid,live) | ¿Qué municipios tienen más camas? | [pre] Un momento. [post] La fuente no respondió esta vez, te sugiero intentar de nuevo. |
| q05 | 916 | 2203 | 655/646 | 1374 (1350) | 3549 | aggregate_ips(ok,live) | ¿Cuántas IPS privadas hay en Bogotá? | [pre] Un momento. [post] 1.260 prestadores privados en Bogotá, según el REPS de 2022. Soy un asistente de IA. |
| q06 | 983 | 2234 | 917/912 | 1341 (1200) | 3951 | aggregate_ips(ok,live) | ¿Cuántos códigos de sede hay en Cali? | [pre] Un momento. [post] 491 códigos de sede según el REPS de 2022. |
| q07 | 966 | 2831 | 929/925 | 1625 (2750) | 4483 | aggregate_ips(ok,live) | ¿Cuántas ambulancias hay en Santander? | [pre] Un momento. [post] 337 ambulancias en Santander, según el REPS de 2022. |
| q08 | 901 | 2530 | 1067/1063 | 1445 (2550) | 4315 | aggregate_ips(ok,live) | ¿Cuántas IPS de nivel tres hay? | [pre] Un momento. [post] 29 prestadores de nivel 3, según el REPS de 2022. |
| q09 | 1008 | 2343 | 1527/1519 | 1317 (1750) | 4419 | aggregate_ips(ok,live) | ¿Cuántas camas de adultos hay en Medellín? | [pre] Un momento. [post] 3.853 camas de adultos en Medellín, según el REPS de 2022. |
| q10 | 999 | 2718 | 806/798 | 1635 (3300) | 4118 | aggregate_ips(ok,live) | ¿Cuántas IPses mixtas hay? | [pre] Un momento. [post] 14 prestadores mixtos según el REPS de 2022. |

</details>

**Fallos (verbatim, R-29):**
- ninguno

## after-semantic-high · openai · `gpt-realtime-2.1` · 2026-10-09T18:00:07Z

- Commit: `8df29b7 Merge commit '19b8261' into feat/reto-01-api-bench` · prompt `reto01-ips-v5` · overrides: `{"REALTIME_TURN_DETECTION": "semantic_vad", "REALTIME_VAD_EAGERNESS": "high"}`
- Turn detection: `{"type": "semantic_vad", "eagerness": "high", "create_response": true, "interrupt_response": true}`
- n = 10 preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: False; espera tras /realtime/session antes de hablar: 2.0 s
- (a) medido con: speech_stopped
- Herramientas `unavailable`: 0

| Métrica (ms desde t0) | p50 | p95 | n |
|---|---|---|---|
| (a) fin de voz detectado | 1224 | 2882 | 10 |
| (b) decisión de herramienta | 2245 | 4220 | 10 |
| (c) POST /tools ida y vuelta (ms) | 754 | 1620 | 10 |
| (c) trace.ms de la fuente | 750 | 1610 | 10 |
| reconocimiento previo: primer audio | 1943 | 3951 | 10 |
| reconocimiento previo: duración | 1000 | 1100 | 10 |
| **(d) primer audio útil** (llegada) | 4481 | 6493 | 10 |
| (d') audible si el reconocimiento suena completo | 4481 | 6493 | 10 |
| turno completo | 5824 | 8321 | 10 |
| emitir credencial (ms) | 1024 | 1262 | 10 |
| abrir WebSocket (ms) | 1162 | 3832 | 10 |

| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |
|---|---|---|---|---|---|---|
| fresh | 2 | 4481 | 5741 | 4481 | 5741 | 3 |
| live | 8 | 4250 | 6493 | 4250 | 6493 | 772 |

<details><summary>Por turno</summary>

| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |
|---|---|---|---|---|---|---|---|---|
| q01 | 2429 | 3194 | 3/0 | 2969 (1100) | 4481 | aggregate_ips(ok,fresh) | ¿Cuántas IPS hay en Colombia? | [pre] Un momento. [post] 9.320 prestadores, según el REPS de 2022. Soy un asistente de IA. |
| q02 | 2882 | 4220 | 8/0 | 3951 (1000) | 5741 | aggregate_ips(ok,fresh) | ¿Cuántas camas hay en total? | [pre] Un momento. [post] 97.036 camas según el REPS de 2022. |
| q03 | 1224 | 2245 | 1620/1610 | 1943 (1000) | 6493 | aggregate_ips(ok,live) | ¿Cuántas IPS públicas hay en Antioquia? | [pre] Un momento. [post] 125 prestadores según el REPS de 2022. Soy un asistente de IA. |
| q04 | 2223 | 3250 | 775/766 | 2839 (1050) | 5006 | aggregate_ips(ok,live) | ¿Qué municipios tienen más camas? | [pre] Un momento. [post] 16.193 camas en Bogotá, 6.280 en Medellín y 5.876 en Cali, según el REPS de 2022. |
| q05 | 1075 | 1958 | 754/750 | 1636 (1000) | 3686 | aggregate_ips(ok,live) | ¿Cuántas IPS privadas hay en Bogotá? | [pre] Un momento. [post] 1.260 prestadores, según el REPS de 2022, soy un asistente de IA. |
| q06 | 1413 | 3227 | 772/769 | 3035 (950) | 5236 | aggregate_ips(ok,live) | ¿Cuántos códigos de sede hay en Cali? | [pre] Un momento. [post] 491 códigos de sede, según el REPS de 2022. Soy un asistente de IA. |
| q07 | 1088 | 2136 | 899/892 | 1722 (1100) | 4250 | aggregate_ips(ok,live) | ¿Cuántas ambulancias hay en Santander? | [pre] Un momento. [post] 337 ambulancias según el REPS de 2022. |
| q08 | 915 | 1853 | 701/696 | 1661 (950) | 3688 | aggregate_ips(ok,live) | ¿Cuántas IPS de nivel tres hay? | [pre] Un momento. [post] 29 prestadores, según el REPS de 2022. Soy un asistente de IA. |
| q09 | 2531 | 3793 | 1230/1223 | 3278 (950) | 6308 | aggregate_ips(ok,live) | ¿Cuántas camas de adultos hay en Medellín? | [pre] Un momento. [post] 3.853 camas, según el REPS de 2022. |
| q10 | 981 | 2054 | 241/238 | 1715 (1050) | 3545 | aggregate_ips(ok,live) | ¿Cuántas IPs mixtas hay? | [pre] Un momento. [post] 14 prestadores, según el REPS de 2022. Soy un asistente de IA. |

</details>

**Fallos (verbatim, R-29):**
- ninguno
