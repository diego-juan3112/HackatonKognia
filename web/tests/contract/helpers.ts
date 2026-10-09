/**
 * Shared harness for the contract tests of docs/08 §13.
 * Drives FakeEngine with vitest fake timers and records every event it emits.
 */
import { vi } from "vitest";
import { MOCK_BRIEF, runTool } from "../../src/voice/api";
import { FakeEngine, type EngineDeps, type FakeEngineOptions } from "../../src/voice/fake-engine";
import type { AnyEngineEvent, EngineEvents, EngineId, EvidenceEnvelope, ToolCallPayload } from "../../src/voice/types";

export const EVENT_TYPES: (keyof EngineEvents)[] = [
  "status",
  "transcript",
  "tool_call",
  "tool_result",
  "speech",
  "interrupted",
  "latency",
  "session",
  "error",
];

export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface Harness {
  engine: FakeEngine;
  events: AnyEngineEvent[];
  toolCalls: ToolCallPayload[];
}

export function harness(
  opts: FakeEngineOptions = {},
  id: EngineId = "openai",
  tool?: EngineDeps["runTool"],
): Harness {
  const t0 = Date.now();
  const toolCalls: ToolCallPayload[] = [];
  const deps: EngineDeps = {
    now: () => Date.now() - t0,
    getBrief: async () => MOCK_BRIEF,
    runTool: (call, ctx): Promise<EvidenceEnvelope> => {
      toolCalls.push(call);
      return tool ? tool(call, ctx) : runTool(call, ctx);
    },
  };
  const engine = new FakeEngine(id, deps, opts);
  const events: AnyEngineEvent[] = [];
  for (const type of EVENT_TYPES) engine.on(type, (ev) => events.push(ev as AnyEngineEvent));
  return { engine, events, toolCalls };
}

/** Advances fake time in small steps until `done()` or the budget runs out. */
export async function runUntil(done: () => boolean, maxMs = 120_000, step = 25): Promise<void> {
  for (let elapsed = 0; elapsed < maxMs && !done(); elapsed += step) {
    await vi.advanceTimersByTimeAsync(step);
  }
  if (!done()) throw new Error(`condition not reached after ${maxMs} ms of simulated time`);
}

export const ofType = <K extends keyof EngineEvents>(events: AnyEngineEvent[], type: K): Extract<AnyEngineEvent, { type: K }>[] =>
  events.filter((e) => e.type === type) as Extract<AnyEngineEvent, { type: K }>[];

export const lastStatus = (events: AnyEngineEvent[]): string | undefined => ofType(events, "status").at(-1)?.payload.state;

/** Connects without the script and waits until the brief is over. */
export async function connected(h: Harness): Promise<void> {
  // connect() waits on a timer: never await it before advancing the fake clock.
  const done = h.engine.connect({ conversationId: "conv-test" });
  await runUntil(() => lastStatus(h.events) === "listening");
  await done;
}

/** Sends a text turn and waits for the engine to go back to listening. */
export async function ask(h: Harness, text: string): Promise<AnyEngineEvent[]> {
  const from = h.events.length;
  h.engine.sendText(text);
  await runUntil(() => h.events.length > from && lastStatus(h.events.slice(from)) === "listening");
  return h.events.slice(from);
}

/** Final text of the agent's answers (kind = answer) inside a slice of events. */
export function answers(events: AnyEngineEvent[]): string[] {
  const gens = new Set(ofType(events, "speech").filter((e) => e.payload.kind === "answer").map((e) => e.payload.generation_id));
  return ofType(events, "transcript")
    .filter((e) => e.payload.role === "agent" && e.payload.final && e.generation_id !== null && gens.has(e.generation_id))
    .map((e) => e.payload.text);
}
