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
