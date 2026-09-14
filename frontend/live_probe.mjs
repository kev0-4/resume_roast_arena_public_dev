// Mirrors the PRODUCTION flow in frontend/src/lib/live-session.ts +
// hooks/use-live-interview.ts exactly: connect with the ephemeral token,
// then kickoff(), then listen. Measures time-to-first-audio, which is the
// number this whole rebuild exists to move.
// Throwaway verification script.

import { readFileSync } from "node:fs";
import { GoogleGenAI, Modality, ThinkingLevel } from "@google/genai";

const payload = JSON.parse(readFileSync(new URL("./start_payload.json", import.meta.url)));
const ai = new GoogleGenAI({ apiKey: payload.token, httpOptions: { apiVersion: "v1alpha" } });

let firstAudioAt = null;
let audioChunks = 0;
let audioBytes = 0;
let kickoffAt = null;
const outTranscript = [];
const t0 = performance.now();

const session = await ai.live.connect({
  model: payload.model,
  config: {
    responseModalities: [Modality.AUDIO],
    systemInstruction: { parts: [{ text: payload.system_instruction }] },
    inputAudioTranscription: {},
    outputAudioTranscription: {},
    thinkingConfig: { thinkingLevel: ThinkingLevel.MINIMAL },
  },
  callbacks: {
    onopen: () => console.log(`[${(performance.now() - t0).toFixed(0)}ms] socket open`),
    onmessage: (message) => {
      const content = message.serverContent;
      if (!content) return;
      for (const part of content.modelTurn?.parts ?? []) {
        if (part.inlineData?.data) {
          audioChunks++;
          audioBytes += Buffer.from(part.inlineData.data, "base64").length;
          if (firstAudioAt === null) firstAudioAt = performance.now();
        }
      }
      if (content.outputTranscription?.text) outTranscript.push(content.outputTranscription.text);
    },
    onerror: (e) => console.log("ERROR:", e.message),
    onclose: (e) => console.log(`socket closed: ${e.reason || "(no reason)"}`),
  },
});

console.log(`[${(performance.now() - t0).toFixed(0)}ms] connect() resolved`);
kickoffAt = performance.now();
session.sendClientContent({
  turns: [{ role: "user", parts: [{ text: "I'm here and ready. Please begin the interview." }] }],
  turnComplete: true,
});
console.log(`[${(kickoffAt - t0).toFixed(0)}ms] kickoff sent`);

await new Promise((r) => setTimeout(r, 22000));

console.log("\n================ RESULT ================");
console.log("token minted by:", payload.variant);
console.log("audio:", audioChunks, `chunks (~${(audioBytes / 48000).toFixed(1)}s of speech at 24kHz/16-bit)`);
console.log("TIME TO FIRST AUDIO (from page connect):", firstAudioAt ? `${((firstAudioAt - t0) / 1000).toFixed(2)}s` : "NEVER");
console.log("  ...from kickoff:", firstAudioAt ? `${((firstAudioAt - kickoffAt) / 1000).toFixed(2)}s` : "n/a");
console.log("\ninterviewer opened with:\n ", outTranscript.join("") || "(nothing)");
console.log("========================================");

session.close();
process.exit(0);
