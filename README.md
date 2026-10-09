# Kognia Voice Agent — Reto 01: agente vocal sobre IPS de datos.gov.co

Agente de voz en tiempo real, en español colombiano, que **consulta en vivo** la «Relación de
IPS públicas y privadas según el nivel de atención y capacidad instalada» (datos.gov.co, REPS,
corte 2022-11-05), muestra la **transcripción con roles y marcas de tiempo**, el **sentimiento y
las emociones** (texto y voz) y **adapta su tono**. Reto 01 de la Hackatón interna de Kognia Labs;
entrega el 2026-10-09 a las 16:00.

| | |
|---|---|
| **Demo pública** | *Se completa al cierre con la URL de producción ([docs/12](docs/12-guia-de-trabajo-2-personas.md) §9)* |
| **Estado** | Contratos escritos ([docs/07](docs/07-reto-01-especificacion.md) a [13](docs/13-diferenciadores-y-backlog.md)); la implementación está en curso. **Este README solo declara como hecho lo que ya corre.** |

## Qué hace

- Conversación por voz con interrupciones: saluda, dice que es una IA y presenta lo que puede consultar.
- Las cifras salen **siempre de una consulta en vivo** a la API (panel «API en vivo»: SoQL, ms, filas, fuente y corte); si no hay dato, lo dice.
- Transcripción en vivo (usuario y agente, con marcas de tiempo) y panel de emociones con estilo adaptativo.
- Recuperación: correcciones («no, dije Melgar»), reintentos acotados y cambio de motor de voz.

## Arquitectura

Navegador (**Astro + TypeScript**) ⇄ motor de voz en tiempo real (**OpenAI Realtime** o **Gemini
Live**, con credencial efímera). Backend **FastAPI en Vercel, solo HTTP**: credenciales, 5
herramientas cerradas que consultan **SODA3** y un analista de afecto en **LangGraph**. Sin base
de datos, RAG ni cédula. Diagrama: [docs/01 §11](docs/01-arquitectura.md).

## Decisiones técnicas

- El contexto es la API en vivo (D-12); el modelo envía JSON y **nunca SoQL** (D-13).
- Voz en tiempo real desde el navegador (D-11), con una excepción acotada a R-04 (D-14).
- Afecto por texto y voz con política de estilo determinista, con aviso y consentimiento (D-16).
- `main` es la rama de integración y de producción (D-19). Lista completa: [docs/00 §5](docs/00-contexto-y-decisiones.md).

## Qué generó la IA (RETO-M04)

Este proyecto se construye con asistencia de IA: **Claude Code (Anthropic)** para la planeación
SDD, la documentación y *[código: completar al cierre]*; **GPT (OpenAI)** para el paquete de
planeación `docs/sdd_ips`. Las personas del equipo revisan y prueban todo lo generado antes de
fusionarlo. Al cierre se listan aquí los módulos generados por IA.

## Cómo correrlo

Monorepo: el front vive en `web/` (Astro) y la API en `src/` (FastAPI). Claves en `.env` de la
raíz, nunca en git: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID`,
`DATOS_GOV_APP_TOKEN`, `SESSION_SIGNING_KEY`.

```bash
cd web && npm ci          # una vez
npm run dev               # http://localhost:4321  (sin backend: motor simulado)
npm run build             # sitio estático en web/dist
npm test                  # pruebas de contrato
```

Con backend: definir `PUBLIC_API_URL` antes de `npm run dev` o del build. Mientras la API de
`src/` se despliega, `node web/dev/dev-backend.mjs` sirve un sustituto local en
`http://localhost:8787` (solo desarrollo). Pantallas: `/` portada, `/consola` usuario,
`/admin` administrador. Despliegue: [docs/11](docs/11-despliegue.md).

## Límites honestos

Capacidad **instalada** (REPS, 2022), no disponibilidad; nivel de atención vacío en el 89% de las
IPS; `departamento` incluye distritos; la separación de hablantes es por rol; el análisis de voz
es una estimación, no un diagnóstico.

Datos: Ministerio de Salud y Protección Social — REPS, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
