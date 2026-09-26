import base64
import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_voice_transcription_endpoint_calls_backend_and_returns_transcript(monkeypatch):
    import app.main as main

    received = {}

    def fake_transcribe(audio_bytes, mime_type, *, filename):
        received["audio_bytes"] = audio_bytes
        received["mime_type"] = mime_type
        received["filename"] = filename
        return "Saya mau menu makanan"

    monkeypatch.setattr(main, "transcribe_audio", fake_transcribe, raising=False)
    response = client.post(
        "/api/voice/transcribe",
        json={
            "audio_base64": base64.b64encode(b"ogg-audio-bytes").decode("ascii"),
            "mime_type": "audio/ogg; codecs=opus",
            "filename": "voice-note.ogg",
        },
        headers={"X-RESTO-API-TOKEN": "test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "Saya mau menu makanan"}
    assert received == {
        "audio_bytes": b"ogg-audio-bytes",
        "mime_type": "audio/ogg; codecs=opus",
        "filename": "voice-note.ogg",
    }


def test_voice_transcription_endpoint_rejects_invalid_base64_before_provider(monkeypatch):
    import app.main as main

    called = False

    def fake_transcribe(*args, **kwargs):
        nonlocal called
        called = True
        return "tidak boleh terpanggil"

    monkeypatch.setattr(main, "transcribe_audio", fake_transcribe)
    response = client.post(
        "/api/voice/transcribe",
        json={"audio_base64": "not-valid-base64!", "mime_type": "audio/ogg"},
        headers={"X-RESTO-API-TOKEN": "test-token"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Payload audio tidak valid"
    assert called is False


def test_voice_transcription_endpoint_returns_customer_safe_error(monkeypatch):
    import app.main as main
    from app.voice import VoiceTranscriptionError

    def fake_transcribe(*args, **kwargs):
        raise VoiceTranscriptionError("Format audio belum didukung.")

    monkeypatch.setattr(main, "transcribe_audio", fake_transcribe)
    response = client.post(
        "/api/voice/transcribe",
        json={
            "audio_base64": base64.b64encode(b"voice").decode("ascii"),
            "mime_type": "video/mp4",
        },
        headers={"X-RESTO-API-TOKEN": "test-token"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Format audio belum didukung."}


def test_voice_transcription_endpoint_accepts_scoped_bridge_token(monkeypatch):
    import app.main as main

    monkeypatch.setenv("RESTO_VOICE_BRIDGE_TOKEN", "bridge-token")
    monkeypatch.setattr(main, "transcribe_audio", lambda *args, **kwargs: "menu")
    response = client.post(
        "/api/voice/transcribe",
        json={
            "audio_base64": base64.b64encode(b"voice").decode("ascii"),
            "mime_type": "audio/ogg",
        },
        headers={"X-RESTO-API-TOKEN": "bridge-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "menu"}


def test_transcribe_voice_sends_ogg_to_openai_and_returns_text(monkeypatch):
    from app import voice

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"text":"Saya mau menu makanan"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = request.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(voice, "urlopen", fake_urlopen)

    transcript = voice.transcribe_audio(
        b"ogg-audio-bytes",
        "audio/ogg; codecs=opus",
        filename="voice-note.ogg",
    )

    assert transcript == "Saya mau menu makanan"
    assert captured["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert captured["headers"]["Authorization"] == "Bearer test-openai-key"
    assert captured["timeout"] == 30
    assert b'name="model"' in captured["body"]
    assert b"whisper-1" in captured["body"]
    assert b'name="file"; filename="voice-note.ogg"' in captured["body"]
    assert b"Content-Type: audio/ogg" in captured["body"]
    assert b"ogg-audio-bytes" in captured["body"]


def test_validate_voice_input_rejects_unsupported_or_oversized_audio():
    import pytest

    from app.voice import MAX_AUDIO_BYTES, VoiceTranscriptionError, validate_voice_input

    assert validate_voice_input(b"voice", "audio/ogg; codecs=opus") == "audio/ogg"

    with pytest.raises(VoiceTranscriptionError, match="Format audio"):
        validate_voice_input(b"voice", "video/mp4")

    with pytest.raises(VoiceTranscriptionError, match="terlalu besar"):
        validate_voice_input(b"x" * (MAX_AUDIO_BYTES + 1), "audio/ogg")
