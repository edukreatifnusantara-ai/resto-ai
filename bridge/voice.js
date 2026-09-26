"use strict";

const WRAPPER_KEYS = [
  "ephemeralMessage",
  "viewOnceMessage",
  "viewOnceMessageV2",
  "viewOnceMessageV2Extension",
  "documentWithCaptionMessage",
];
const MAX_AUDIO_BYTES = 8 * 1024 * 1024;

function findAudioMessage(content, depth = 0) {
  if (!content || depth > 5 || typeof content !== "object") return null;
  if (content.audioMessage && typeof content.audioMessage === "object") {
    return content.audioMessage;
  }
  for (const key of WRAPPER_KEYS) {
    const wrapped = content[key]?.message;
    const audio = findAudioMessage(wrapped, depth + 1);
    if (audio) return audio;
  }
  return null;
}

function extensionForMime(mimeType) {
  const normalized = String(mimeType || "").split(";", 1)[0].trim().toLowerCase();
  return {
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/wav": "wav",
    "audio/webm": "webm",
  }[normalized] || "ogg";
}

async function transcribeIncomingAudio({
  message,
  downloadMediaMessage,
  reuploadRequest,
  transcribeUrl,
  authToken,
  fetchImpl = fetch,
}) {
  const content = message?.message || message;
  const audioMessage = findAudioMessage(content);
  if (!audioMessage) return null;
  const advertisedSize = Number(audioMessage.fileLength || 0);
  if (Number.isFinite(advertisedSize) && advertisedSize > MAX_AUDIO_BYTES) {
    throw new Error("Ukuran voice note terlalu besar untuk diproses.");
  }
  if (!authToken) throw new Error("Token transkripsi bridge belum dikonfigurasi.");

  const audioBuffer = await downloadMediaMessage(
    message,
    "buffer",
    {},
    { reuploadRequest },
  );
  const response = await fetchImpl(transcribeUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-RESTO-API-TOKEN": authToken,
    },
    body: JSON.stringify({
      audio_base64: Buffer.from(audioBuffer).toString("base64"),
      mime_type: audioMessage.mimetype || "audio/ogg",
      filename: `voice-note.${extensionForMime(audioMessage.mimetype)}`,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(String(payload?.detail || "Voice note belum dapat diproses."));
  }
  const transcript = String(payload?.transcript || "").trim();
  if (!transcript) throw new Error("Isi voice note belum dapat dikenali.");
  return transcript;
}

module.exports = { findAudioMessage, transcribeIncomingAudio };
