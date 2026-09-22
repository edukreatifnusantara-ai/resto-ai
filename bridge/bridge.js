const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');
const { Boom } = require('@hapi/boom');

const SESSION_DIR = path.join(__dirname, 'session');
const RESTO_API_URL = process.env.RESTO_API_URL || 'http://127.0.0.1:18081/api/chat';
const PYTHON_BIN = '/home/edukreativ-vps/.hermes/hermes-agent/venv/bin/python';

let sock = null;
let reconnectTimer = null;

function scheduleReconnect(delayMs = 3000) {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    startBridge().catch(console.error);
  }, delayMs);
}

async function startBridge() {
  if (!fs.existsSync(SESSION_DIR)) {
    fs.mkdirSync(SESSION_DIR, { recursive: true });
  }

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
  let versionInfo;
  try {
    versionInfo = await fetchLatestBaileysVersion();
  } catch (err) {
    versionInfo = { version: [2, 3000, 1043857760] };
  }

  sock = makeWASocket({
    version: versionInfo.version,
    auth: state,
    logger: pino({ level: 'silent' }),
    printQRInTerminal: false,
    browser: ['Ubuntu', 'Chrome', '22.04.4'],
    syncFullHistory: false,
    markOnlineOnConnect: false,
    getMessage: async () => ({ conversation: '' })
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('New QR code received');
      const qrTxtPath = path.join(__dirname, 'qr.txt');
      const qrPngPath = path.join(__dirname, 'qr.png');
      fs.writeFileSync(qrTxtPath, qr);

      try {
        execSync(`${PYTHON_BIN} -c "import qrcode; qrcode.make(open('${qrTxtPath}').read()).save('${qrPngPath}')"`);
        console.log('QR code saved as PNG at ' + qrPngPath);
      } catch (err) {
        console.error('Error generating QR PNG:', err.message);
      }
    }

    if (connection === 'close') {
      const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode;
      const isLoggedOut = statusCode === DisconnectReason.loggedOut;

      // If unregistered and connection closes, reset session for fresh QR
      if (isLoggedOut && !sock.authState.creds.registered) {
        console.log('Unregistered session closed. Resetting session for fresh QR...');
        try {
          fs.readdirSync(SESSION_DIR).forEach(file => fs.unlinkSync(path.join(SESSION_DIR, file)));
        } catch {}
        scheduleReconnect(2000);
        return;
      }

      const shouldReconnect = !isLoggedOut;
      console.log(`Connection closed (code: ${statusCode}). Reconnecting: ${shouldReconnect}`);

      if (shouldReconnect) {
        scheduleReconnect(statusCode === 515 ? 1000 : 3000);
      } else {
        console.log('Logged out. Please re-pair.');
      }
    } else if (connection === 'open') {
      console.log('WhatsApp connection established successfully! Resto-AI Bot is online.');
      try {
        if (fs.existsSync(path.join(__dirname, 'qr.png'))) fs.unlinkSync(path.join(__dirname, 'qr.png'));
        if (fs.existsSync(path.join(__dirname, 'qr.txt'))) fs.unlinkSync(path.join(__dirname, 'qr.txt'));
      } catch {}
      fs.writeFileSync(path.join(__dirname, 'status.json'), JSON.stringify({
        status: 'connected',
        user: sock.user?.id || null,
        connected_at: new Date().toISOString()
      }));
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;

    for (const m of messages) {
      if (m.key.fromMe) continue;
      const remoteJid = m.key.remoteJid;
      if (!remoteJid || remoteJid.endsWith('@g.us') || remoteJid === 'status@broadcast') continue;

      const text =
        m.message?.conversation ||
        m.message?.extendedTextMessage?.text ||
        m.message?.imageMessage?.caption ||
        '';

      if (!text || !text.trim()) continue;

      const senderNumber = remoteJid.split('@')[0];
      const messageId = m.key.id;

      console.log(`[Resto-AI] Incoming from ${senderNumber}: "${text.trim()}"`);

      try {
        const response = await fetch(RESTO_API_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sender: senderNumber,
            body: text.trim(),
            message_id: messageId
          })
        });

        if (response.ok) {
          const data = await response.json();
          if (data.reply) {
            console.log(`[Resto-AI] Replying to ${senderNumber}: "${data.reply.slice(0, 40)}..."`);
            await sock.sendMessage(remoteJid, { text: data.reply }, { quoted: m });
          }
        } else {
          console.error(`Resto API returned status ${response.status}`);
        }
      } catch (err) {
        console.error('Error forwarding message to Resto-AI API:', err.message);
      }
    }
  });
}

startBridge().catch(console.error);
