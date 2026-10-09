# Pruebas

## Reglas

| Código | Regla |
|---|---|
| R-16 | La suite por defecto (`pytest`) corre **sin credenciales, sin red, sin micrófono y sin GPU**, usando los dobles de `tests/doubles/` (R-09). Las sondas en vivo (`tests/live/`, marca `live`) se saltan solas salvo con `KOGNIA_LIVE=1`. |
| R-17 | `services/` se prueba con tests unitarios, reemplazando `integrations/` por dobles. `integrations/` se prueba mockeando la llamada externa (`httpx.MockTransport`): nunca se golpea el servicio real en la suite por defecto. |
| R-18 | **Retirada (D-23): la base genérica se eliminó.** *(Era: pruebas de integración solo contra una base de datos de prueba aislada.)* |
| R-19 | **Retirada (D-23): la base genérica se eliminó.** *(Era: el documento de identidad completo nunca llega al LLM. La app actual no pide datos personales: sesión anónima, R-28.)* |

Escenarios y metas de aceptación: [07](07-reto-01-especificacion.md) §7–§8.

## Comandos

```bash
pytest                                   # suite offline, con dobles (R-16)
KOGNIA_LIVE=1 pytest tests/live -m live  # sondas contra datos.gov.co real (manual)
cd web && npm test                       # pruebas de contrato del cliente (vitest)
cd web && npm run build                  # compila el frontend
```

## Qué hay en la suite

| Qué | Dónde |
|---|---|
| Dobles (R-09) | `tests/doubles/fake_dataset.py` (`FakeDataset`) y `tests/doubles/fake_voice.py` (`FakeRealtimeSession`, `FakeSpeechSession`, `FakeAffectModel`, `FakeAnalyst`, `FakeFeedback`). En el cliente, respuestas JSON en `web/mocks/` y el motor simulado `FakeEngine` (`web/src/voice/fake-engine.ts`) |
| Fixtures | `tests/fixtures/`: léxico pequeño, casos de *grounding* y preguntas del banco; las filas de ejemplo se registran en `FakeDataset` por prueba (Mixta, nivel vacío, cantidad nula, varias sedes, homónimos; [09](09-datos-en-vivo-datos-gov-co.md) §4) |
| Unitarias de servicios | `tests/services/`: constructores de consulta y escape, normalización y ambigüedad, sobre de evidencia, herramientas de agente, verificador de cifras, sesión y especificaciones, analista (política de estilo y fusión de afecto) |
| Adaptadores | `tests/integrations/test_socrata_client.py`: plazos, reintentos, token y caché con transporte simulado |
| API | `tests/api/test_app_voice.py`: rutas, formato de error, límites y prefijo `/api` |
| Contrato del cliente | `web/tests/contract/` (vitest): orden de `seq`, `delivered_text` tras interrumpir, eventos tardíos descartados, idempotencia por `tool_call_id`, conmutación de motor sin herramienta duplicada ([08](08-contrato-voz-en-vivo.md) §13) |
| Sondas en vivo | `tests/live/`, marca `live`; **no corren por defecto**; usan la API real y los números dorados de [09](09-datos-en-vivo-datos-gov-co.md) §9 |
| Benchmark | `scripts/bench_models.py`, **fuera** de la suite; protocolo de [07](07-reto-01-especificacion.md) §8; publica también los fallos |
| Evaluación de alucinaciones | `scripts/eval_grounding.py`, fuera de la suite |
| Humo público | `scripts/smoke_public.py` contra la URL de producción ([11](11-despliegue.md) §7) |
| Navegador | Playwright con micrófono simulado (`--use-fake-device-for-media-stream`), `cd web && npm run test:e2e` |

## Qué prueba y qué no prueba la suite

Que la suite pase prueba el **cableado** y las invariantes deterministas (consultas
armadas por el servidor, grano, unidades, verificador), no la calidad de voz ni de las
respuestas: eso lo prueban el benchmark, la evaluación de *grounding* y los ensayos del
guion con proveedores reales, que se anotan en el `CHANGELOG.md`.

## Pendiente de definir

- Umbral mínimo de cobertura exigido antes de un merge.
