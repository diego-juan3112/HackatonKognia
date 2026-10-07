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

## Pendiente de definir

- Umbral mínimo de cobertura exigido antes de un merge.
