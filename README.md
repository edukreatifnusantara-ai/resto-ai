# Resto AI Agent — MVP Staging

Status: **DATA DUMMY / SIMULASI / TIDAK BERLAKU SEBAGAI PENAWARAN RESMI**.

MVP ini menyediakan backend lokal untuk alur resto yang dirancang:

- katalog menu dan harga dari database;
- pembuatan order dan perhitungan total;
- pembayaran simulasi yang tidak melakukan settlement;
- pengiriman order ke dapur dan pengurangan stok berdasarkan resep;
- transisi status order;
- laporan penjualan, keuangan simulasi, dan stok.

## Batasan penting

Belum ada koneksi WhatsApp, QRIS, rekening bank, payment gateway, data pelanggan nyata, pengiriman pesan eksternal, refund, atau deployment produksi. API hanya bind localhost dan seluruh endpoint data membutuhkan header `X-RESTO-API-TOKEN`; token runtime tersimpan di `.env.runtime` dan tidak masuk Git.

## Menjalankan

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
set -a; . ./.env.runtime; set +a
export RESTO_DATABASE_URL=sqlite:///./staging.db
python -m app.cli
uvicorn main:app --host 127.0.0.1 --port 18081
```

Health check publik:

```bash
curl http://127.0.0.1:18081/
```

Endpoint data memakai token:

```bash
curl -H "X-RESTO-API-TOKEN: $RESTO_API_TOKEN" http://127.0.0.1:18081/menu
```

Jika instalasi editable belum diperlukan, dependensi staging dapat dipasang langsung:

```bash
python -m pip install fastapi uvicorn sqlalchemy pytest httpx2
```

## Test

```bash
PYTHONPATH=. pytest -q
```

Test mencakup katalog, total order, pembayaran simulasi dan idempotensi, validasi stok, pengurangan stok, transisi dapur, dan laporan.

## API inti

- `GET /menu`
- `POST /menu`
- `POST /orders/`
- `POST /orders/{order_id}/request-payment`
- `GET /orders/{order_id}`
- `POST /orders/{order_id}/pay` — simulasi konfirmasi saja
- `POST /orders/{order_id}/payment-failed` — simulasi gagal bayar
- `POST /orders/{order_id}/send-to-kitchen`
- `POST /orders/{order_id}/prepare`
- `POST /orders/{order_id}/ready`
- `POST /orders/{order_id}/complete`
- `GET /reports/sales`
- `GET /reports/finance`
- `GET /reports/stock`

## WhatsApp Cloud API (staging)

The project now includes a deterministic Meta WhatsApp Cloud API adapter. It is not an AI/LLM conversation engine yet; it handles a bounded command workflow and keeps the order state in SQLite.

Supported customer messages:

- `MENU` — list the seeded menu;
- `PESAN <id_menu> <jumlah>` — create a draft order;
- `BAYAR <id_order>` — confirm a payment simulation;
- `STATUS <id_order>` — read the sender's own order;
- `BATAL <id_order>` — cancel a draft or pending-payment order;
- `HELP` — show the commands.

The webhook endpoints are:

- `GET /webhooks/whatsapp` — Meta subscription verification;
- `POST /webhooks/whatsapp` — signed incoming events.

Unlike internal API routes, the webhook does not use `X-RESTO-API-TOKEN`. It is protected by Meta's verify token and `X-Hub-Signature-256` app-secret signature. Incoming message IDs are stored in `whatsapp_events` so Meta retries do not create duplicate orders.

### WhatsApp environment variables

Add the following variables to the ignored `.env.runtime` file. Keep the values private and never commit them:

```text
RESTO_API_TOKEN=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_GRAPH_API_VERSION=
WHATSAPP_DRY_RUN=true
```

Append each real value locally after its `=` sign. `WHATSAPP_DRY_RUN=true` is the safe staging mode: outbound replies are recorded by the adapter but are not sent to Meta. Set it to `false` only after the Meta credentials and callback are ready.

### Meta setup outline

1. Create or open a Meta Developer application.
2. Add the WhatsApp product and obtain a test/business phone number.
3. Save the phone number ID, access token, app secret, and a private webhook verify token in `.env.runtime`.
4. Expose the local server through an HTTPS tunnel for testing, or use a deployed HTTPS URL. Meta cannot call a private `127.0.0.1` address directly.
5. Configure the callback URL as `/webhooks/whatsapp`.
6. Use the same verify token in Meta and `WHATSAPP_VERIFY_TOKEN`.
7. Subscribe the WhatsApp business account to message events.
8. Set `WHATSAPP_DRY_RUN=false` only when outbound Meta delivery is intentionally enabled.

The current implementation sends text replies through:

```text
POST https://graph.facebook.com/{WHATSAPP_GRAPH_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages
```

The Graph API version is deliberately configured through the environment so it can be updated according to the Meta account's currently supported version.

### Local webhook test

For a local signed dry-run test, use the test suite:

```bash
pytest -q
```

The tests cover subscription verification, bad signature rejection, duplicate event handling, menu commands, customer order ownership, and simulated payment.

## Payment status

The WhatsApp `BAYAR` command currently performs a clearly labeled simulated confirmation. It does not create a QRIS, call a bank, verify a transfer, or settle funds. A real Midtrans/Xendit integration still requires a separately selected provider, credentials, public HTTPS webhook, signature verification, refund policy, and reconciliation tests.
