# Diferenciadores, Europa y backlog

Qué nos distingue, qué copiamos de Europa y qué queda para después. Los ítems del backlog son
**borradores de issue**: no se crean en GitHub sin confirmación del equipo.

## 1. Diferenciadores (de menor a mayor esfuerzo para el impacto)

| # | Diferenciador | Esfuerzo | Por qué suma |
|---|---|---|---|
| 1 | Panel «API en vivo»: SoQL, ms, filas, fuente y corte, «Reconsultar» | S | Prueba visible de que está conectado, que el jurado verifica (F-11) |
| 2 | Honestidad: cifras solo de herramientas, «según el REPS, corte nov-2022», y límites explícitos | S | RETO-P4 la observa (R-22) |
| 3 | Estilo adaptativo visible con motivo y «Más directo» | M | Responde a la «psicología» pedida (F-09) |
| 4 | Recuperación visible: corrección, desambiguación, conmutación de motor | M | Es lo que más se nota cuando algo falla (R-25) |
| 5 | HUD de latencia por etapa con motor y modelo | S | Evidencia de «voz y latencia» (20%) |
| 6 | Reconocimiento previo a consultar («déjame verificarlo en datos.gov.co…») | S | Baja la latencia percibida, medida aparte |
| 7 | Desambiguación hablada con léxico («¿San Vicente de Paúl de Garzón o de Remedios?») | M | Evita errores de cifras y es la idea de «verificar la transcripción con un RAG», sin base de datos |
| 8 | Aviso de IA + consentimiento + sin audio guardado | S | Credibilidad en P6 y ángulo europeo |
| 9 | Selector de motor en vivo (OpenAI ↔ Gemini) | M | Compara fortalezas y debilidades delante del jurado |

## 2. Europa (fuentes secundarias; no verificadas con el proveedor)

- **Mistral Voxtral:** transcripción en tiempo real con diarización y *biasing* de contexto, con pesos abiertos para despliegue privado, y TTS propio.
- **Kyutai Unmute:** receta modular STT→LLM→TTS con detección semántica de fin de turno.
- **AI Act (UE):** el art. 50 exige avisar que se habla con una IA (en vigor desde 2026-08-02); la inferencia de emociones a partir de datos biométricos está **prohibida en entornos laborales y educativos** (art. 5.1.f) y exige transparencia en otros. No es asesoría legal.
- **Lo que copiamos hoy:** modularidad por contrato, cumplimiento por diseño (aviso, consentimiento, sin almacenar audio, estado efímero). **Backlog:** turno semántico y proveedores europeos; residencia de datos si se vende en la UE.

## 3. Backlog (borradores de issue)

| ID | Título | Prioridad y dependencia | Definición de hecho | Esfuerzo |
|---|---|---|---|---|
| B-01 | Recuperación híbrida de entidades con pgvector | P2, solo si se reintroduce base de datos | Embeddings versionados, filtros geográficos, recall medido frente al léxico, sin regresión en agregados; nunca mezclar espacios de embedding | 2–4 h |
| B-02 | Comparación en sombra Gemini/OpenAI | P1 tras la Puerta 2 | Mismo contexto y evidencia, muestreo ≤ 10% con consentimiento, sin ejecutar herramientas, informe y presupuesto | 1–2 h |
| B-03 | Perfiles Claude y Grok | P2 tras B-02 | Chequeo de capacidades, traducción de herramientas por proveedor, misma aceptación, costo y latencia medidos | 2–4 h |
| B-04 | Motor 3 en cascada (STT del navegador + `/v1/turns` + TTS) | P1 si falla un motor en vivo | Contrato de sdd_ips/03; reutiliza la demo de la rama `spike/demo-voz-avatar`; mismas pruebas A-xx | 3–5 h |
| B-05 | Espejo paginado y refresco de la fuente | P2, solo si se reconsidera un snapshot | IDs estables, reconciliación de conteos y versión, *upsert* idempotente, promoción atómica | 1–3 h |
| B-06 | Ciclo de evaluación del feedback revisado | P1 | Taxonomía de errores, casos anonimizados, versión de prompt, reporte de regresión y reversión ([10](10-modelos-afecto-y-recuperacion.md) §5) | 1–2 h |
| B-07 | Diarización robusta de varias voces humanas | P1 | Evaluar Gemini 3.5 Transcribe, Deepgram y Azure; medir la precisión por separado de los roles | 2–4 h |
| B-08 | Automatización de Azure | P2 | Terraform reproducible, secretos, salud, despliegue y reversión; `terraform apply` manual (R-21) | 2–4 h |
| B-09 | Canal telefónico con Twilio | P2 tras B-08 o backend estable | Llamada real, μ-law 8 kHz, interrupción y reconexión, validación de firma del webhook, tope de gasto; un track por hablante da diarización exacta | 3–6 h |
| B-10 | Estudio de interacción adaptativa | P2 tras B-06 | Preferencia explícita frente a estimaciones de texto y voz, divulgación, beneficio medible, sin diagnóstico | 2–4 h |
| B-11 | Ingesta de documento sorpresa | Condicional (si los organizadores lo exigen) | Ámbito de fuente separado, límites de archivo, procedencia, sin contaminar respuestas de IPS | reestimar |
| B-12 | Modelo acústico de emoción dedicado | P2 | Comparar con Gemini multimodal; consentimiento; sin almacenar audio | 2–4 h |
| B-13 | Avatar 3D con lip-sync | P2 | RocketBox + Three.js + `wawa-lipsync` ([anexos/us2-avatar-3d.md](anexos/us2-avatar-3d.md)) | 3–5 h |
| B-14 | Turno semántico y *hedged requests* | P2 | Fin de turno por significado; respaldo tras un retraso medido; herramientas ejecutadas una sola vez | 3–5 h |
| B-15 | Verificador de cifras | P1 | Comparar los dígitos dichos con los resultados de herramientas y autocorregir con aviso | 2–3 h |

Los rangos de esfuerzo son estimaciones, no compromisos. Ninguno debe consumir el colchón de entrega.

## 4. Pendiente de herramientas

Regenerar los diagramas de `docs/diagrams/` con `archify` cuando haya tiempo; mientras tanto, el
diagrama de arquitectura y de un turno viven como Mermaid en [01](01-arquitectura.md) §11.
