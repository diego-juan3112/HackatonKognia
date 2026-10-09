/**
 * Gemini Live adapter (engine 2): translates its WebSocket protocol into the
 * neutral reducers of RealtimeEngineBase. Protocol facts come from the G2 spike
 * (docs/anexos/g2-voz-y-contexto-para-carril-b.md §4):
 *
 *   - the ephemeral token goes in the URL and fixes the whole configuration, so
 *     the client only names the model;
 *   - microphone audio is PCM16 at 16 kHz; server frames arrive as binary JSON;
 *   - a tool response needs no follow-up request;
 *   - a barge-in arrives as an explicit "interrupted" flag;
 *   - style and context are sent as a tagged user note that must not be answered
 *     (a system turn closes the connection);
 *   - text-only output is not supported, so the cloned voice is not available.
 *
 * The provider has no response ids: one local id is made per spoken stretch.
 * Nothing provider-specific leaves this file (R-03).
 */
import type { RealtimeSessionGrant } from "./api";
import { base64ToPcm, openSocket, parseFrame, pcmToBase64, RealtimeEngineBase, type CancelInfo, type ProviderToolCall } from "./realtime-base";
import type { ContextEnvelope, StyleDecision } from "./types";

type Msg = Record<string, unknown>;

const str = (v: unknown): string => (typeof v === "string" ? v : "");
const obj = (v: unknown): Msg => (v && typeof v === "object" ? (v as Msg) : {});
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

const NOTE = "[NOTA DEL SISTEMA, no la respondas ni la menciones]";
/** Wait for late transcription fragments before closing a user utterance. */
const FINALIZE_MS = 300;

export class GeminiLiveEngine extends RealtimeEngineBase {
  readonly id = "gemini" as const;
  protected readonly inputRate = 16_000 as const;
  /** The server cuts by itself (low start-of-speech sensitivity on the backend): no local wait. */
  protected readonly bargeConfirmMs = 0;

  private ws: WebSocket | null = null;
  private ready = false;
  private audioEpoch: number | null = null;
  /** Local id of the stretch of speech being received. */
  private generation: string | null = null;
  /** The server is still inside a model turn. */
  private serverTurnOpen = false;
  /** Drop model output until the server closes the turn we interrupted locally. */
  private dropping = false;
  private userKey: string | null = null;
  private userStopped = false;
  private finalizeTimer: ReturnType<typeof setTimeout> | undefined;
  private readonly cancelledCalls = new Set<string>();

  protected get transportReady(): boolean {
    return this.ready && this.ws?.readyState === WebSocket.OPEN;
  }

  protected sessionRequestExtras(): Record<string, unknown> {
    // The credential fixes the instructions, so the style in force goes with the request.
    return this.currentStyle ? { style: this.currentStyle } : {};
  }

  protected async openTransport(grant: RealtimeSessionGrant): Promise<void> {
    const base = grant.connect.url;
    const url = /[?&]access_token=/.test(base) ? base : `${base}${base.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(grant.connect.token)}`;
    const ws = await openSocket(url);
    this.ws = ws;
    this.ready = false;
    this.audioEpoch = null;
    this.generation = null;
    this.serverTurnOpen = false;
    this.dropping = false;
    this.userKey = null;
    this.cancelledCalls.clear();
    const model = grant.model.startsWith("models/") ? grant.model : `models/${grant.model}`;
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("setup timeout")), 8000);
      ws.onmessage = (ev) => {
        const msg = parseFrame(ev.data);
        if (!msg?.setupComplete) return;
        clearTimeout(timer);
        this.ready = true;
        ws.onmessage = (e) => this.onMessage(e.data);
        resolve();
      };
      ws.onclose = () => {
        clearTimeout(timer);
        reject(new Error("closed before setup"));
      };
      ws.send(JSON.stringify({ setup: { model } }));
    });
    ws.onclose = (ev) => {
      if (this.ws !== ws) return;
      this.ready = false;
      this.transportClosed(`code ${ev.code}`);
    };
  }

  protected closeTransport(): void {
    clearTimeout(this.finalizeTimer);
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
    this.send({ realtimeInput: { audio: { data: pcmToBase64(pcm), mimeType: `audio/pcm;rate=${this.inputRate}` } } });
  }

  protected sendUserText(text: string): void {
    this.send({ realtimeInput: { text } });
  }

  protected sendNote(text: string): void {
    this.send({ clientContent: { turns: [{ role: "user", parts: [{ text }] }], turnComplete: true } });
  }

  protected sendGreeting(spokenBrief: string): void {
    // The figures of the greeting come from the live brief, never from the model (R-22).
    this.send({ realtimeInput: { text: `${NOTE} Preséntate ahora diciendo exactamente este texto, sin añadir ni cambiar cifras: «${spokenBrief}»` } });
  }

  protected sendToolOutput(call: ProviderToolCall, output: Record<string, unknown>): void {
    if (this.cancelledCalls.delete(call.callId)) return; // the provider withdrew this call
    this.send({ toolResponse: { functionResponses: [{ id: call.callId, name: call.name, response: output }] } });
  }

  protected sendSeed(context: ContextEnvelope): void {
    const turns = context.recent_turns.slice(-8).map((t) => ({ role: t.role === "user" ? "user" : "model", parts: [{ text: t.text }] }));
    turns.push({ role: "user", parts: [{ text: `${NOTE} ${this.describeContext(context)}` }] });
    this.send({ clientContent: { turns, turnComplete: false } });
  }

  protected sendStyle(style: StyleDecision): void {
    this.send({ clientContent: { turns: [{ role: "user", parts: [{ text: `${NOTE} ${this.styleNote(style)}` }] }], turnComplete: false } });
  }

  protected cancelGeneration(generationId: string, _info: CancelInfo): void {
    // There is no client-side cancel: the provider stops by itself when it hears the user.
    // After a local stop it may keep sending the old turn, which is dropped until it closes.
    if (this.generation === generationId) {
      this.generation = null;
      this.dropping = this.serverTurnOpen;
    }
  }

  // ── Inbound ────────────────────────────────────────────────────────────────

  private offsetToClock(offset: unknown): number | undefined {
    const seconds = Number.parseFloat(str(offset));
    return this.audioEpoch !== null && Number.isFinite(seconds) ? this.audioEpoch + seconds * 1000 : undefined;
  }

  private openUser(tStart?: number): string {
    this.closeUser();
    const key = crypto.randomUUID();
    this.userKey = key;
    this.userStopped = false;
    this.userSpeechStarted(key, tStart);
    return key;
  }

  private stopUser(tEnd?: number): void {
    if (!this.userKey || this.userStopped) return;
    this.userStopped = true;
    this.userSpeechStopped(this.userKey, tEnd);
    this.scheduleFinalize();
  }

  private scheduleFinalize(): void {
    clearTimeout(this.finalizeTimer);
    this.finalizeTimer = setTimeout(() => {
      // The transcription can trail the end of the speech: stay open until there is text.
      if (this.userKey && this.userUtteranceText(this.userKey)) this.closeUser();
    }, FINALIZE_MS);
  }

  private closeUser(): void {
    clearTimeout(this.finalizeTimer);
    const key = this.userKey;
    if (!key) return;
    this.userKey = null;
    if (!this.userStopped) this.userSpeechStopped(key);
    this.userTranscript(key, "", { final: true, append: true });
  }

  private ensureGeneration(): string {
    if (!this.generation) {
      // The model is answering: the user's turn is over, even if no activity event said so.
      this.stopUser();
      this.generation = `gem-${crypto.randomUUID()}`;
      this.serverTurnOpen = true;
      this.generationStarted(this.generation);
    }
    return this.generation;
  }

  private endGeneration(): void {
    const id = this.generation;
    if (!id) return;
    this.generation = null;
    this.agentTranscript(id, "", { final: true, append: true });
    this.generationDone(id);
  }

  private onMessage(data: unknown): void {
    const msg = parseFrame(data);
    if (!msg) return;

    if (msg.voiceActivity) {
      const activity = obj(msg.voiceActivity);
      const kind = str(activity.type);
      if (kind === "ACTIVITY_START") this.openUser(this.offsetToClock(activity.audioOffset));
      else if (kind === "ACTIVITY_END") this.stopUser(this.offsetToClock(activity.audioOffset));
    }

    if (msg.serverContent) {
      const content = obj(msg.serverContent);

      if (content.inputTranscription) {
        const text = str(obj(content.inputTranscription).text);
        let key = this.userKey !== null && this.userUtteranceText(this.userKey) !== null ? this.userKey : null;
        // Fallback when no activity event announced the utterance. A fragment that trails an
        // answer already in flight belongs to a closed utterance and is not a new turn.
        if (text && key === null && this.generation === null && !this.serverTurnOpen) key = this.openUser();
        if (text && key !== null) {
          this.userTranscript(key, text, { final: false, append: true });
          if (this.userStopped) this.scheduleFinalize();
        }
      }

      if (content.interrupted) {
        this.dropping = false;
        const id = this.generation;
        this.generation = null;
        this.providerInterrupted(id);
      }

      if (!this.dropping) {
        for (const part of arr(obj(content.modelTurn).parts)) {
          const inline = obj(obj(part).inlineData);
          if (typeof inline.data === "string" && inline.data) this.agentAudio(this.ensureGeneration(), base64ToPcm(inline.data));
        }
        const spoken = str(obj(content.outputTranscription).text);
        if (spoken) this.agentTranscript(this.ensureGeneration(), spoken, { final: false, append: true });
      }

      if (content.generationComplete) this.endGeneration();
      if (content.turnComplete) {
        this.serverTurnOpen = false;
        this.dropping = false;
        this.endGeneration();
      }
    }

    if (msg.toolCall) {
      this.stopUser();
      const acknowledgement = this.generation;
      for (const raw of arr(obj(msg.toolCall).functionCalls)) {
        const call = obj(raw);
        this.toolRequested({ callId: str(call.id), name: str(call.name), args: obj(call.args), generationId: acknowledgement });
      }
      // Whatever was said before the call was the acknowledgement; the answer is a new stretch.
      this.endGeneration();
    }

    if (msg.toolCallCancellation) {
      for (const id of arr(obj(msg.toolCallCancellation).ids)) this.cancelledCalls.add(str(id));
    }

    if (msg.goAway) this.transportExpiring("el proveedor anunció el cierre de la conexión");
  }
}
