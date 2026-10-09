# RAG — base de conocimiento

**El día del evento nos entregarán información que el agente debe poder usar
de inmediato.** Puede ser un PDF, un CSV, un manual o una base de preguntas
frecuentes: no lo sabemos. Por eso el RAG se diseña alrededor de la
**ingesta**, no del contenido.

## Reglas

| Código | Regla |
|---|---|
| R-12 | La ingesta es un paso ejecutable y repetible (un comando), no un proceso manual: apuntar a una carpeta y reindexar. |
| R-13 | El formato de origen se maneja con cargadores intercambiables (`src/integrations/retrieval/loaders.py`): agregar un formato es una función y una entrada en un diccionario, sin tocar el resto del pipeline. |
| R-14 | `services/` solo pide "contexto relevante para este turno" a través de `RetrievalPort`. Nunca sabe qué motor responde ni en qué formato estaba el documento. |
| R-15 | La dimensión del vector está fija en la migración (`vector(768)`, ligada a D-05). Cambiar de modelo de embedding exige una migración nueva y reindexar. `E5Embedder` lo valida al arrancar. |

## Piezas

| Pieza | Dónde | Nota |
|---|---|---|
| Almacén | PostgreSQL + pgvector (D-02) | Índice HNSW `vector_cosine_ops`, operador `<=>` |
| Embeddings | `src/integrations/retrieval/embeddings.py` (D-05) | Interfaz asimétrica (`embed_documents` / `embed_query`) por los prefijos `passage:` / `query:` de E5 |
| Cargadores | `src/integrations/retrieval/loaders.py` | `.md`, `.txt`, `.csv`, `.pdf` |
| Retriever | `src/integrations/retrieval/pgvector_retriever.py` | Una transacción por documento: reingestar reemplaza atómicamente |

## Comandos

```bash
python -m scripts.ingest --path <carpeta> --reset   # lo que se corre el día del reto
python -m scripts.seed                              # corpus de juguete (docs/faq_demo) + usuarios demo
```

`GET /health` muestra `indexed_chunks`: si es 0, el agente no tiene conocimiento.
