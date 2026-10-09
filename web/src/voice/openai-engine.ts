/**
 * OpenAI Realtime adapter (engine 1): translates its WebSocket protocol into the
 * neutral reducers of RealtimeEngineBase. Protocol facts come from the G2 spike
 * (docs/anexos/g2-voz-y-contexto-para-carril-b.md §4):
 *
 *   - the ephemeral secret travels as a WebSocket subprotocol and is single use;
 *   - microphone audio must be PCM16 at 24 kHz (16 kHz is rejected);
 *   - a barge-in arrives as "speech started" plus a cancelled response, and the
 *     heard part is fixed with an item truncation;
 *   - after a function output the client must ask for the next response;
 *   - the credential does not lock the session, so style is a session update.
 *
 * Nothing provider-specific leaves this file (R-03).
 */
import type { RealtimeSessionGrant } from "./api";
import { base64ToPcm, openSocket, parseFrame, pcmToBase64, RealtimeEngineBase, type CancelInfo, type ProviderToolCall } from "./realtime-base";
import type { ContextEnvelope, StyleDecision } from "./types";

type Msg = Record<string, unknown>;

const str = (v: unknown): string => (typeof v === "string" ? v : "");
const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
const obj = (v: unknown): Msg => (v && typeof v === "object" ? (v as Msg) : {});

/** Provider errors that are expected races, not failures. */
const BENIGN_ERRORS = new Set(["response_cancel_not_active", "conversation_already_has_active_response", "item_truncate_invalid_audio_end_ms"]);

interface ResponseState {
  /** Assistant audio item of this response, needed to truncate it. */
  itemId: string | null;
  done: boolean;
  /** Function calls of this response still waiting for their output. */
  openCalls: number;
  hadCalls: boolean;
  turnId: string | null;
  /** Played ms to fix once the provider has closed the response. */
  truncateAt: number | null;
}

export class OpenAIRealtimeEngine extends RealtimeEngineBase {
  readonly id = "openai" as const;
  protected readonly inputRate = 24_000 as const;

  private ws: WebSocket | null = null;
  private ready = false;
  private baseInstructions = "";
  private readonly responses = new Map<string, ResponseState>();
  private activeResponse: string | null = null;
  /** Session-clock time of the first audio sample sent on this connection. */
  private audioEpoch: number | null = null;

  protected get transportReady(): boolean {
    return this.ready && this.ws?.readyState === WebSocket.OPEN;
  }

  protected async openTransport(grant: RealtimeSessionGrant): Promise<void> {
    const token = grant.connect.token;
    const given = grant.connect.protocols ?? ["realtime"];
    const protocols = given.some((p) => p.includes(token)) ? given : [...given, `openai-insecure-api-key.${token}`];
    const ws = await openSocket(grant.connect.url, protocols);
    this.ws = ws;
    this.ready = false;
    this.audioEpoch = null;
    this.activeResponse = null;
    this.responses.clear();
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("session timeout")), 8000);
      ws.onmessage = (ev) => {
        const msg = parseFrame(ev.data);
        if (!msg) return;
        if (msg.type === "session.created") {
          clearTimeout(timer);
          this.baseInstructions = str(obj(msg.session).instructions);
          this.ready = true;
          ws.onmessage = (e) => this.onMessage(e.data);
          resolve();
        } else if (msg.type === "error") {
          clearTimeout(timer);
          reject(new Error("session rejected"));
        }
      };
      ws.onclose = () => {
        clearTimeout(timer);
        reject(new Error("closed before session"));
      };
    });
    ws.onclose = (ev) => {
      if (this.ws !== ws) return;
      this.ready = false;
      this.transportClosed(`code ${ev.code}`);
    };
  }

  protected closeTransport(): void {
    const ws = this.ws;
    this.ws = null;
    this.ready = false;
    if (!ws) return;
    ws.onmessage = ws.onclose = ws.onerror = null;
    try {
      ws.close();
    } catch {
      // already closed
    }
  }

  protected dropTransportForTest(): void {
    this.ws?.close();
  }

  private send(msg: Msg): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  // ── Outbound ───────────────────────────────────────────────────────────────

  protected sendAudioFrame(pcm: Int16Array): void {
    this.audioEpoch ??= this.now() - (pcm.length / this.inputRate) * 1000;
    this.send({ type: "input_audio_buffer.append", audio: pcmToBase64(pcm) });
  }

  protected sendUserText(text: string): void {
    this.send({ type: "conversation.item.create", item: { type: "message", role: "user", content: [{ type: "input_text", text }] } });
    this.send({ type: "response.create" });
  }

  protected sendNote(text: string): void {
    this.sendUserText(text);
  }

  protected sendGreeting(spokenBrief: string): void {
    // The figures of the greeting come from the live brief, never from the model (R-22).
    this.send({
      type: "response.create",
      response: {
        instructions: `Saluda diciendo exactamente este texto, en español colombiano, sin añadir ni cambiar cifras: «${spokenBrief}»`,
        tool_choice: "none",
      },
    });
  }

  protected sendToolOutput(call: ProviderToolCall, output: Record<string, unknown>): void {
    this.send({ type: "conversation.item.create", item: { type: "function_call_output", call_id: call.callId, output: JSON.stringify(output) } });
    const responseId = call.generationId;
    const state = responseId ? this.responses.get(responseId) : undefined;
    if (state) state.openCalls = Math.max(0, state.openCalls - 1);
    this.maybeContinue(responseId, state);
  }

  /** After every function output of a finished response is in, ask for the answer. */
  private maybeContinue(responseId: string | null, state: ResponseState | undefined): void {
    if (!responseId || !state || !state.hadCalls || !state.done || state.openCalls > 0) return;
    // A newer user turn gets its own response from the provider's turn detection.
    if (state.turnId !== this.currentTurnId || this.activeResponse !== null) return;
    state.hadCalls = false;
    this.send({ type: "response.create" });
  }

  protected sendSeed(context: ContextEnvelope): void {
    for (const turn of context.recent_turns.slice(-8)) {
      this.send({
        type: "conversation.item.create",
        item:
          turn.role === "user"
            ? { type: "message", role: "user", content: [{ type: "input_text", text: turn.text }] }
            : { type: "message", role: "assistant", content: [{ type: "output_text", text: turn.text }] },
      });
    }
    this.send({ type: "conversation.item.create", item: { type: "message", role: "system", content: [{ type: "input_text", text: this.describeContext(context) }] } });
  }

  protected sendStyle(style: StyleDecision): void {
    if (!this.baseInstructions) return;
    this.send({ type: "session.update", session: { type: "realtime", instructions: `${this.baseInstructions}\n${this.styleNote(style)}` } });
  }

  protected cancelGeneration(generationId: string, info: CancelInfo): void {
    const state = this.responses.get(generationId);
    if (!info.byProvider && this.activeResponse === generationId) this.send({ type: "response.cancel" });
    // The conversation keeps only the audio that was really played (docs/08 §6.3).
    if (!state?.itemId) return;
    const playedMs = Math.max(0, Math.floor(info.playedMs));
    if (state.done) this.truncate(state.itemId, playedMs);
    else state.truncateAt = playedMs; // the item is still open: fix it when the response closes
  }

  private truncate(itemId: string, playedMs: number): void {
    this.send({ type: "conversation.item.truncate", item_id: itemId, content_index: 0, audio_end_ms: playedMs });
  }

  // ── Inbound ────────────────────────────────────────────────────────────────

  private onMessage(data: unknown): void {
    const msg = parseFrame(data);
    if (!msg) return;
    const type = str(msg.type);
    const responseId = str(msg.response_id);
    switch (type) {
      case "input_audio_buffer.speech_started": {
        const at = num(msg.audio_start_ms);
        this.userSpeechStarted(str(msg.item_id), this.audioEpoch !== null && at !== undefined ? this.audioEpoch + at : undefined);
        break;
      }
      case "input_audio_buffer.speech_stopped": {
        const at = num(msg.audio_end_ms);
        this.userSpeechStopped(str(msg.item_id), this.audioEpoch !== null && at !== undefined ? this.audioEpoch + at : undefined);
        break;
      }
      case "conversation.item.input_audio_transcription.delta":
        this.userTranscript(str(msg.item_id), str(msg.delta), { final: false, append: true });
        break;
      case "conversation.item.input_audio_transcription.completed":
        this.userTranscript(str(msg.item_id), str(msg.transcript), { final: true });
        break;
      case "response.created": {
        const id = str(obj(msg.response).id);
        if (!id) break;
        this.activeResponse = id;
        this.responses.set(id, { itemId: null, done: false, openCalls: 0, hadCalls: false, turnId: this.currentTurnId, truncateAt: null });
        if (this.responses.size > 24) {
          const oldest = this.responses.keys().next().value;
          if (oldest !== undefined) this.responses.delete(oldest);
        }
        this.generationStarted(id);
        break;
      }
      case "response.output_audio.delta": {
        const state = this.responses.get(responseId);
        if (state && !state.itemId) state.itemId = str(msg.item_id) || null;
        this.agentAudio(responseId, base64ToPcm(str(msg.delta)));
        break;
      }
      case "response.output_audio_transcript.delta":
        this.agentTranscript(responseId, str(msg.delta), { final: false, append: true });
        break;
      case "response.output_audio_transcript.done":
        this.agentTranscript(responseId, str(msg.transcript), { final: true });
        break;
      case "response.output_text.delta":
        this.agentTranscript(responseId, str(msg.delta), { final: false, append: true });
        break;
      case "response.function_call_arguments.done": {
        const state = this.responses.get(responseId);
        if (state) {
          state.openCalls++;
          state.hadCalls = true;
        }
        let args: Record<string, unknown> = {};
        try {
          args = obj(JSON.parse(str(msg.arguments) || "{}"));
        } catch {
          // Malformed arguments reach the backend as an empty object and come back `invalid`.
        }
        this.toolRequested({ callId: str(msg.call_id), name: str(msg.name), args, generationId: responseId || null });
        break;
      }
      case "response.done": {
        const response = obj(msg.response);
        const id = str(response.id);
        const state = this.responses.get(id);
        if (this.activeResponse === id) this.activeResponse = null;
        if (state) state.done = true;
        const status = str(response.status);
        const flushTruncate = (): void => {
          if (state?.itemId && state.truncateAt !== null) this.truncate(state.itemId, state.truncateAt);
          if (state) state.truncateAt = null;
        };
        if (status === "cancelled") {
          this.providerInterrupted(id);
          flushTruncate();
        } else if (status === "failed") {
          const error = obj(obj(response.status_details).error);
          const quota = /quota|rate_limit/i.test(`${str(error.code)} ${str(error.type)}`);
          this.generationDone(id);
          this.fail(quota ? "ENGINE_QUOTA" : "ENGINE_DROPPED", "El motor de voz no pudo generar la respuesta.", true);
          break;
        }
        flushTruncate();
        this.generationDone(id);
        this.maybeContinue(id, state);
        break;
      }
      case "error": {
        const error = obj(msg.error);
        const code = str(error.code);
        if (code === "session_expired") this.transportExpiring("la sesión del proveedor venció");
        else if (!BENIGN_ERRORS.has(code)) console.warn(`[voice:openai] provider error: ${code || str(error.type) || "unknown"}`);
        break;
      }
      default:
        break;
    }
  }
}
