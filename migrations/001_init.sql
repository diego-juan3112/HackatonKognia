-- =========================================================================
-- 001_init -- Esquema inicial: usuarios, conversaciones y base de conocimiento.
--
-- Este archivo es la fuente de verdad del modelo relacional. No se edita
-- despues de aplicado: los cambios van en una migracion nueva (002_, 003_...),
-- porque el runner lleva registro de cual ya corrio.
--
-- Las tablas del checkpointer de LangGraph NO estan aqui: las crea la propia
-- libreria con `.setup()` al arrancar la aplicacion.
-- =========================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- -------------------------------------------------------------------------
-- Identidad
-- -------------------------------------------------------------------------

-- Identificacion por cedula, SIN contrasena. Esto no es autenticacion real:
-- cualquiera que conozca una cedula entra. Es una decision consciente para
-- la demo; si el reto exige seguridad, hay que agregar password_hash aqui.
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cedula        TEXT        NOT NULL UNIQUE,
    display_name  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ
);

CREATE TABLE sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX sessions_user_idx ON sessions (user_id);

-- -------------------------------------------------------------------------
-- Conversaciones
-- -------------------------------------------------------------------------

-- thread_id es el puente con LangGraph: es la clave que el checkpointer usa
-- para reanudar el estado del grafo. Por eso es UNIQUE y no es la PK -- la PK
-- es nuestra (UUID) y thread_id pertenece al mundo de LangGraph.
CREATE TABLE conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id   TEXT        NOT NULL UNIQUE,
    title       TEXT,
    domain      TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX conversations_user_recent_idx
    ON conversations (user_id, updated_at DESC);

-- Historial legible. Complementa al checkpointer, no lo duplica por descuido:
-- el checkpointer guarda estado serializado del grafo (ilegible en SQL); esta
-- tabla guarda quien dijo que, con que intencion y citando que fuentes.
CREATE TABLE messages (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT        NOT NULL CHECK (role IN ('user', 'agent', 'system')),
    content          TEXT        NOT NULL,
    intent           TEXT,
    route            TEXT,
    sources          JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX messages_conversation_idx
    ON messages (conversation_id, created_at);

-- -------------------------------------------------------------------------
-- Base de conocimiento (RAG)
-- -------------------------------------------------------------------------

CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source      TEXT        NOT NULL UNIQUE,
    title       TEXT,
    metadata    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    indexed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- vector(768) corresponde a intfloat/multilingual-e5-base.
-- CAMBIAR DE MODELO DE EMBEDDING EXIGE UNA MIGRACION NUEVA Y REINDEXAR:
-- la dimension queda fija en la columna y pgvector no la convierte sola.
CREATE TABLE document_chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER     NOT NULL,
    content      TEXT        NOT NULL,
    embedding    vector(768) NOT NULL,
    metadata     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (document_id, chunk_index)
);

-- HNSW con distancia coseno: los vectores se normalizan antes de escribirlos,
-- asi que coseno es el espacio correcto.
CREATE INDEX document_chunks_embedding_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops);
