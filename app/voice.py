"""OpenAI-backed speech-to-text helper for inbound WhatsApp voice notes."""

from __future__ import annotations

import json
import os
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class VoiceTranscriptionError(RuntimeError):
    """Raised when a voice note cannot be transcribed."""


MAX_AUDIO_BYTES = 8 * 1024 * 1024
SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/webm",
}


def validate_voice_input(audio_bytes: bytes, mime_type: str) -> str:
    """Validate bounded WhatsApp audio before invoking the paid provider."""
    if not audio_bytes:
        raise VoiceTranscriptionError("Voice note kosong atau tidak dapat diunduh.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise VoiceTranscriptionError("Ukuran voice note terlalu besar untuk diproses.")
    normalized_mime = mime_type.split(";", 1)[0].strip().lower()
    if normalized_mime not in SUPPORTED_AUDIO_MIME_TYPES:
        raise VoiceTranscriptionError("Format audio belum didukung.")
    return normalized_mime


def _multipart_body(
    *,
    model: str,
    audio_bytes: bytes,
    mime_type: str,
    filename: str,
) -> tuple[bytes, str]:
    boundary = f"----resto-ai-{uuid.uuid4().hex}"
    line = b"\r\n"
    normalized_mime = mime_type.split(";", 1)[0].strip().lower() or "application/octet-stream"
    body = b"".join(
        [
            f"--{boundary}".encode(),
            line,
            b'Content-Disposition: form-data; name="model"',
            line,
            line,
            model.encode("utf-8"),
            line,
            f"--{boundary}".encode(),
            line,
            (
                'Content-Disposition: form-data; name="file"; '
                f'filename="{filename}"'
            ).encode("utf-8"),
            line,
            f"Content-Type: {normalized_mime}".encode("utf-8"),
            line,
            line,
            audio_bytes,
            line,
            f"--{boundary}--".encode(),
            line,
        ]
    )
    return body, boundary


def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str,
    *,
    filename: str = "voice-note.ogg",
) -> str:
    """Send one WhatsApp voice note to OpenAI and return its transcript."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise VoiceTranscriptionError("Layanan transkripsi belum dikonfigurasi.")

    normalized_mime = validate_voice_input(audio_bytes, mime_type)
    model = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe").strip() or "gpt-4o-mini-transcribe"
    body, boundary = _multipart_body(
        model=model,
        audio_bytes=audio_bytes,
        mime_type=normalized_mime,
        filename=filename,
    )
    request = Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise VoiceTranscriptionError("Voice note belum dapat ditranskripsikan.") from exc

    transcript = str(payload.get("text", "")).strip()
    if not transcript:
        raise VoiceTranscriptionError("Isi voice note belum dapat dikenali.")
    return transcript
