# Pruebas

## Reglas

| Código | Regla |
|---|---|
| R-16 | La suite por defecto (`pytest`) corre **sin credenciales, sin red, sin Docker, sin micrófono y sin GPU**, usando los dobles de `tests/doubles/` (R-09). |
| R-17 | `services/` se prueba con tests unitarios, reemplazando `integrations/` por dobles. `integrations/` se prueba mockeando la llamada externa: nunca se golpea el servicio real en la suite por defecto. |
| R-18 | Los tests contra PostgreSQL real viven en `tests/integration/`, están marcados `integration` y se saltan solos si no hay base. **Nunca tocan la base de desarrollo:** corren contra `TEST_DATABASE_URL` (`kognia_test`), que se crea y migra sola, y se niegan a ejecutarse si el nombre de la base no termina en `_test`. |
| R-19 | La cédula completa nunca llega al LLM. `tests/services/test_user_context.py` revisa todos los prompts y falla si aparece. |

## Comandos

```bash
pytest                  # offline, con dobles
pytest -m integration   # contra PostgreSQL real, en kognia_test
```

## Qué prueba y qué no prueba la suite

Que la suite pase prueba que el **cableado** es correcto, no la calidad de las
respuestas. Los dobles respetan las mismas invariantes que la base (cédula
única, cascada, `updated_at`), pero `FakeChatModel` no es Gemini. Para la
calidad está el recorrido HTTP con modelos reales, que se anota en la sección
"Verificado" del `CHANGELOG.md`.

## Reto 01

Aplican R-16 (suite offline) y R-17; **no aplican** R-18 ni R-19 (sin base de datos ni
cédula). Escenarios y metas: [07](07-reto-01-especificacion.md) §7–§8.

| Qué | Cómo |
|---|---|
| Dobles (R-09) | Python en `tests/doubles/`: `FakeDataset`, `FakeAnalyst`, `FakeRealtimeSession`, `FakeChatModel`; cliente en `web/mocks/`: `FakeEngine` con eventos guionados |
| Fixtures de datos | A partir de `docs/sdd_ips/evidence/socrata_probe.json` (incluye filas repetidas de un prestador) más sintéticos: Mixta, nivel vacío, cantidad nula, varias sedes, cambio de corte y el grupo sin clave ([09](09-datos-en-vivo-datos-gov-co.md) §4) |
| Pruebas unitarias (B) | Constructores de consulta y escape, normalización y ambigüedad, sobre de evidencia, mapeo de estados y plazos, política de estilo y fusión de afecto |
| Pruebas de contrato (A y B) | Orden de `seq`, `delivered_text` tras interrumpir, eventos tardíos descartados, idempotencia por `tool_call_id`, conmutación de motor sin herramienta duplicada ([08](08-contrato-voz-en-vivo.md) §13) |
| Sondas en vivo | `tests/live/`, marca `live`; **no corren por defecto**; usan la API real |
| Benchmark | `scripts/bench_models.py`, **fuera** de la suite; protocolo de [07](07-reto-01-especificacion.md) §8; publica también los fallos |
| Humo público | `scripts/smoke_public.py` contra la URL de producción ([11](11-despliegue.md) §7) |
| Navegador | Playwright con micrófono simulado (`--use-fake-device-for-media-stream`) para los flujos de interfaz |

```bash
pytest                       # offline, con dobles
pytest -m live               # sondas contra datos.gov.co (manual)
npm run build                # dentro de web/ (compila el frontend)
```

Que pase la suite prueba el **cableado**, no la calidad de voz ni de las respuestas: eso lo
prueban el benchmark y los ensayos del guion con proveedores reales.

## Pendiente de definir

- Umbral mínimo de cobertura exigido antes de un merge.
