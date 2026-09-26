const assert = require('node:assert/strict');
const test = require('node:test');

const { transcribeIncomingAudio } = require('../voice');

test('transcribeIncomingAudio downloads WhatsApp audio and calls the internal API', async () => {
  const captured = {};
  const transcript = await transcribeIncomingAudio({
    message: {
      ephemeralMessage: {
        message: {
          audioMessage: { mimetype: 'audio/ogg; codecs=opus' },
        },
      },
    },
    downloadMediaMessage: async (message, type, options, context) => {
      captured.download = { message, type, options, context };
      return Buffer.from('ogg-audio-bytes');
    },
    reuploadRequest: async () => undefined,
    transcribeUrl: 'http://127.0.0.1:18081/api/voice/transcribe',
    authToken: 'bridge-token',
    fetchImpl: async (url, options) => {
      captured.url = url;
      captured.options = options;
      return {
        ok: true,
        json: async () => ({ transcript: 'Saya mau menu makanan' }),
      };
    },
  });

  assert.equal(transcript, 'Saya mau menu makanan');
  assert.equal(captured.download.type, 'buffer');
  assert.equal(captured.url, 'http://127.0.0.1:18081/api/voice/transcribe');
  assert.equal(captured.options.method, 'POST');
  assert.equal(captured.options.headers['X-RESTO-API-TOKEN'], 'bridge-token');
  const payload = JSON.parse(captured.options.body);
  assert.equal(payload.mime_type, 'audio/ogg; codecs=opus');
  assert.equal(payload.filename, 'voice-note.ogg');
  assert.equal(Buffer.from(payload.audio_base64, 'base64').toString(), 'ogg-audio-bytes');
});

test('transcribeIncomingAudio rejects an oversized voice note before download', async () => {
  let downloaded = false;

  await assert.rejects(
    transcribeIncomingAudio({
      message: { audioMessage: { mimetype: 'audio/ogg', fileLength: 8 * 1024 * 1024 + 1 } },
      downloadMediaMessage: async () => {
        downloaded = true;
        return Buffer.alloc(0);
      },
      reuploadRequest: async () => undefined,
      transcribeUrl: 'http://127.0.0.1:18081/api/voice/transcribe',
      authToken: 'bridge-token',
      fetchImpl: async () => {
        throw new Error('should not fetch');
      },
    }),
    /terlalu besar/,
  );

  assert.equal(downloaded, false);
});
