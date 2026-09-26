# Workflow n8n Resto-AI

File `resto-ai-whatsapp-incoming.json` adalah export workflow n8n yang menggambarkan alur:

`WhatsApp Incoming -> Normalize Incoming -> Resto-AI API -> Prepare WhatsApp Reply -> Baileys Bridge Send`

## Fungsi setiap node

- **WhatsApp Incoming**: menerima `POST` dari bridge pada webhook n8n.
- **Normalize Incoming**: mengambil `sender`, `body`, dan `message_id`.
- **Resto-AI API**: meneruskan pesan ke `http://172.18.0.1:18081/api/chat` melalui local SSH forward PC Mint.
- **Prepare WhatsApp Reply**: menjaga nomor pengirim dan menyiapkan teks atau `image_path` QRIS.
- **Baileys Bridge Send**: mengirim balasan melalui `http://172.18.0.1:18082/send` melalui local SSH forward PC Mint.

## Cara memakai

1. Buka n8n.
2. Pilih **Import from File**.
3. Pilih `resto-ai-whatsapp-incoming.json`.
4. Simpan workflow dan salin **Production URL** webhook.
5. Pastikan service `mint-resto-ai-forward.service` aktif di PC Mint. Unit ini meneruskan port `172.18.0.1:18081` dan `172.18.0.1:18082` ke Resto-AI di VPS.
6. Hubungkan bridge Baileys ke URL webhook tersebut dengan mengubah `RESTO_API_URL` pada service bridge di VPS.
7. Uji dengan satu pesan `MENU` sebelum mengaktifkan workflow produksi.

Workflow dibuat `active: false` pada export, lalu dapat dipublish dari CLI n8n setelah diimpor.

## Catatan keamanan dan status saat dibuat

- Endpoint `/api/chat` memang merupakan endpoint publik internal pada kode Resto-AI saat ini; jangan expose port API ke internet tanpa reverse proxy dan pembatasan akses.
- Endpoint bridge `/send` hanya listen di `127.0.0.1` pada kode saat ini.
- n8n berjalan di PC Mint; URL workflow memakai gateway Docker PC Mint (`172.18.0.1`) yang harus memiliki local SSH forward aktif.
- Hasil dari API dapat membawa `image_path`; bridge akan mengirim file itu bila tersedia.
- Workflow sudah diimpor dan dipublish ke n8n PC Mint dengan ID `resto-ai-whatsapp-incoming-v1`; status database terbaca aktif.
- `mint-resto-ai-forward.service` dan `mint-n8n-reverse.service` sudah terpasang, enabled, dan active di PC Mint untuk menghubungkan kedua arah trafik.
- Uji end-to-end pesan WhatsApp melalui workflow belum dilakukan.
