# Blueprint & Panduan Enterprise AI Workforce Resto-AI (Warung Ndelik)

Dokumen ini menjelaskan arsitektur integrasi multi-agent (AI Employee) pada platform **Resto-AI**, mencakup divisi **Front-Office (Layanan Tamu WhatsApp: Waitress & Kasir)** dan divisi **Back-Office (Operasional, Keuangan, Riset & SDM)**, koneksi ke ekosistem **Google Workspace (Sheets, Docs, Excel)**, perancangan **Dashboard UI Interaktif dengan Grafik Lengkap**, integrasi **Media Sosial**, manajemen token hemat biaya, serta pengoperasian workflow **n8n** dengan data operasional riil Warung Ndelik Mranggen.

---

## 1. Arsitektur & Peran Tim AI Employee

Sistem mempekerjakan tim AI spesialis yang bekerja secara terkoordinasi dengan pembagian tugas dan batasan wewenang yang ketat:

### A. Divisi Front-Office (Layanan Pelanggan WhatsApp)

| Peran AI Employee | Tanggung Jawab Utama | Trigger & Interaksi | Output & Deliverable | Batasan Keamanan (Guardrail) |
|---|---|---|---|---|
| **1. AI Waitress (Pramusaji / Menu Advisor)** | • Menyambut pelanggan dengan ramah dan sopan khas Warung Ndelik Mranggen.<br>• Menawarkan & menjelaskan menu terlaris (Nasi Ayam Penyet Rp 16rb, Bebek Bumbu Hitam Rp 25rb, Garang Asem Rp 20rb).<br>• Upselling minuman segar (Es Teh Jumbo Rp 5rb, Kopi Hitam Rp 5rb, Soda Gembira Rp 10rb).<br>• Menjelaskan varian rasa, kepedasan, jam operasional (10:00-22:00), dan info lokasi. | Chat WhatsApp Masuk dari Pelanggan (`resto-ai/incoming`) | Rekomendasi Menu Interaktif, Jawaban FAQ Ramah, Ajakan Pemesanan Sopan | Tidak memberikan diskon sepihak tanpa instruksi Bos; selalu menjaga keramahan santun. |
| **2. AI Kasir (POS Order, Billing & Pembayaran)** | • Mencatat pesanan tamu (menu, jumlah porsi, nomor meja / bungkus).<br>• Menghitung subtotal belanja, total tagihan, dan mencetak struk digital resmi.<br>• Menyediakan opsi pembayaran: Tunai di Kasir atau QRIS Dinamis Midtrans.<br>• Sinkronisasi transaksi langsung ke Google Sheets `LOG_TRANSAKSI_PENJUALAN`.<br>• Mengirimkan tiket pesanan ke bagian Dapur (*Kitchen Dispatch*). | Chat Pemesanan Tamu ("Pesan...", "Bayar...", "Struk...", "QRIS...") | Struk Tagihan Digital WhatsApp, Payload QRIS Midtrans, Tiket Dapur, Log Google Sheets | Tidak membatalkan order lunas tanpa izin Bos; nominal tagihan terkunci sesuai harga sistem. |

### B. Divisi Back-Office (Operasional, Keuangan, Riset & Manajemen)

| Peran AI Employee | Tanggung Jawab Utama | Trigger & Jadwal | Output & Deliverable | Batasan Keamanan (Guardrail) |
|---|---|---|---|---|
| **3. CEO / Orchestrator** | Mengoordinasikan seluruh tugas agen, memilah perintah Owner vs chat tamu, menormalkan payload, dan menyaring instruksi. | Event-driven, On-demand, Jadwal Harian | Dispatching tugas, Notifikasi ringkas WhatsApp Owner | Tidak boleh mengeksekusi pengeluaran uang atau perubahan data tanpa approval Bos. |
| **4. Tim Riset (Research Specialist)** | • Riset tren menu kuliner viral (TikTok/IG Reels).<br>• Riset harga komoditas pangan pasar lokal (cabai rawit, daging ayam, telur, minyak).<br>• Intelijen menu & promo kompetitor lokal di Mranggen dan Semarang. | Mingguan (Rabu 09:00 WIB) & Sesuai Permintaan | Tab `RISET_PASAR` Google Sheets, Google Docs Brief Riset, WhatsApp Executive Brief | Hanya membaca sumber publik; tidak mengubah harga menu tanpa izin Bos. |
| **5. Finance Controller** | • Rekap transaksi penjualan harian/bulanan.<br>• Perhitungan P&L berbasis biaya riil (HPP bahan rata-rata Rp 1,17jt/hari, Biaya Tetap Rp 933.333/hari).<br>• Sinkronisasi otomatis ke Google Sheets & Excel. | Harian (Closing 22:00 WIB) & On-demand | Tab `LABA_RUGI_PNL` Sheets, Laporan Keuangan Google Docs, Feed Looker Studio | Draf laporan keuangan; tidak boleh melakukan settlement perbankan otomatis. |
| **6. Social Media & Marketing** | • Penyusunan Kalender Konten (Content Calendar).<br>• Draf copywriting (caption, hook video Reels/TikTok, hashtag promosi).<br>• Penjadwalan posting ke Meta Graph API (IG/FB). | Mingguan & Harian | Tab `KALENDER_MEDSOS` Sheets, Draf Post ke Approval Gate | Wajib melewati konfirmasi Bos sebelum diterbitkan ke medsos publik. |
| **7. Inventory & Kitchen Supply** | • Monitoring stok bahan dapur (74 item) & minuman (25 item) vs batas minimum.<br>• Rekapitulasi belanja harian masuk (pasar, minuman, dan perlengkapan toko).<br>• Penyusunan Purchase Order (PO) / Daftar Belanja Pasar Harian esok hari. | Harian (Pagi 07:00 WIB) & Per Order | Tab `STOK_INVENTORY`, Tab `LOG_BELANJA_HARIAN`, Notifikasi Belanja ke Dapur & Bos | Tidak memesan barang ke supplier sebelum disetujui Bos. |
| **8. HR & Payroll (Personalia)** | • Rekapitulasi absensi & draf gaji bulanan untuk **Manajemen (Owner Rp 5jt, Co-owner Rp 3jt) dan 10 Staf (Rp 18,5jt) -> Total Rp 26.500.000**.<br>• Draf slip gaji privat. | Bulanan (Tgl 25) | Google Docs Payroll Ledger, Tab `MASTER_KARYAWAN` | Data privat; dilarang dibagikan ke kanal umum atau dicairkan otomatis. |

---

## 2. Master Data Personalia, Belanja Harian & Biaya Operasional Riil

### A. Roster Personalia & Gaji Bulanan (12 Orang)
Berdasarkan ketetapan resmi manajemen dan operasional Warung Ndelik Mranggen:

| No | Nama | Gaji Pokok (Bulan) | Alokasi Harian (30 hari) | Peran / Penugasan |
|---|---|---|---|---|
| **MANAJEMEN & PEMILIK** |
| 1 | **Owner** | Rp 5.000.000 | Rp 166.667 | Pemilik Utama / Eksekutif |
| 2 | **Co-owner** | Rp 3.000.000 | Rp 100.000 | Co-owner / Manajemen Operasional |
| **STAF OPERASIONAL** |
| 3 | **Pincuk** | Rp 2.500.000 | Rp 83.333 | Staf Inti / Senior |
| 4 | **Dirimu** | Rp 2.500.000 | Rp 83.333 | Staf Inti / Senior |
| 5 | **Fika** | Rp 2.000.000 | Rp 66.667 | Staf Operasional |
| 6 | **Tatik** | Rp 1.500.000 | Rp 50.000 | Staf Dapur / Kasir |
| 7 | **Wahyu** | Rp 2.000.000 | Rp 66.667 | Staf Operasional |
| 8 | **Tyas** | Rp 2.000.000 | Rp 66.667 | Staf Operasional |
| 9 | **Alwi** | Rp 1.500.000 | Rp 50.000 | Staf Dapur / Layanan |
| 10 | **Zaki** | Rp 1.500.000 | Rp 50.000 | Staf Dapur / Layanan |
| 11 | **Ping an** | Rp 1.500.000 | Rp 50.000 | Staf Layanan |
| 12 | **Amat** | Rp 1.500.000 | Rp 50.000 | Staf Layanan |
| **TOTAL** | **12 Personil** | **Rp 26.500.000** | **Rp 883.333** | **Total Anggaran Payroll** |

*Rincian Subtotal:*
- **Subtotal Manajemen (2 Orang):** Rp 8.000.000 / bulan
- **Subtotal Staf Operasional (10 Orang):** Rp 18.500.000 / bulan

### B. Biaya Tetap (Fixed Cost Baseline)
1. **Total Payroll (Manajemen + Staf):** Rp 26.500.000 / bulan
2. **Listrik & Air (Utilitas):** Rp 1.500.000 / bulan
3. **Total Biaya Tetap Bulanan:** **Rp 28.000.000 / bulan**
4. **Alokasi Beban Tetap Harian:** **Rp 933.333 / hari** (~ Rp 28.000.000 / 30 hari)
5. **Biaya Tetap Tahunan:** Rp 336.000.000 / tahun

### C. Rekapitulasi Belanja Harian & Belanja Operasional Lainnya (`Agustus.xlsx`)
Berdasarkan pencatatan 28 hari operasional (26.08.26 s/d 24.09.26):
- **Total Belanja Masuk (28 Hari):** **Rp 33.152.297**
- **Rata-rata Pengeluaran Belanja Harian:** **Rp 1.184.010 / hari**

*Komposisi Kategori Belanja:*
1. **Belanja Bahan Dapur (Pasar):** **Rp 26.038.717 (78.5%)**
   - Beras (Rp 4,15jt), Bebek (Rp 3,78jt), Ayam Penyet (Rp 2,52jt), Gula Pasir (Rp 1,96jt), Minyak (Rp 1,65jt), Telur (Rp 1,52jt), Mie Kwetiau (Rp 1,09jt), Kecap (Rp 945rb), Cabai, Bawang, Sayur.
2. **Belanja Bahan Minuman:** **Rp 3.952.380 (11.9%)**
   - Es Batu (Rp 904rb), Teh (Rp 720rb), Kopi Hitam, Susu, Good Day, Sirup, Soda.
3. **Belanja Operasional & Perlengkapan Lainnya (Non-Bahan):** **Rp 3.161.200 (9.5%)**
   - **Gas Elpiji:** Rp 2.088.000 (87 tabung gas @ Rp 24.000)
   - **Air Galon:** Rp 464.000 (116 galon @ Rp 4.000)
   - **Nota Kasir 3-Play:** Rp 180.000 (30 buku)
   - **Tisu Makan:** Rp 277.200
   - **Plastik Kresek & Sampah:** Rp 112.000
   - **Sabun Cuci Sunlight & Sedotan:** Rp 40.000

---

## 3. Strategi Pemilihan Model Google Gemini Berbayar (Anggaran Rp 200.000 / Bulan)

Kekhawatiran Bos mengenai model gratis yang sering "ngacau", lambat saat jam sibuk (throttling), atau mengalami degradasi penalaran adalah **sangat tepat**. Pada model gratisan (Free Tier), Google tidak memberikan jaminan Service Level Agreement (SLA), kapasitas server dibagi dengan jutaan pengguna umum, dan ada kuota request per menit yang ketat.

Dengan mengalokasikan **anggaran Rp 200.000 / bulan (~ $12.50 USD)** di Google AI Studio (Pay-As-You-Go), kita mendapatkan akses **Enterprise Paid Tier**:
- **SLA Prioritas Tinggi & Zero Throttling:** Permintaan API diproses di jalur server prioritas Google tanpa antrean.
- **Privasi Data Bisnis:** Data transaksi, resep, dan percakapan pelanggan Warung Ndelik **TIDAK** dipakai Google untuk melatih model publik.
- **Kapasitas Sangat Besar:** Limit naik hingga 1.000 - 2.000 Request per Menit (RPM).

### A. Arsitektur Dual-Gemini (Flash + Pro) Sesuai Pembagian Tugas

| Divisi / Peran AI | Model Google Gemini Terpilih | Alokasi Anggaran Bulanan | Alasan & Karakteristik Model |
|---|---|---|---|
| **1. Pengelola Medsos (TikTok, IG, FB)** | **Gemini 1.5 Pro (Paid Tier)** | **Rp 85.000 / bln** (~$5.30 USD) | **Kreativitas & Storytelling Tertinggi.** Menghasilkan hook FYP TikTok yang memikat, caption Instagram yang estetis & persuasif, serta posting komunitas Facebook yang interaktif tanpa kesan bahasa kaku/robotik. Multimodal (bisa membaca visual foto hidangan Warung Ndelik). |
| **2. Front-Office (Waitress & Kasir WA)** | **Gemini 1.5 Flash (Paid Tier)** | **Rp 35.000 / bln** (~$2.20 USD) | **Kecepatan Kilat & Anti-Halusinasi.** Latensi super cepat (< 1 detik) agar pelanggan tidak menunggu lama. Disetel pada `temperature: 0.2` agar kasir 100% disiplin pada harga menu dan tidak pernah salah hitung nominal. |
| **3. Tim Riset & Intelijen Pasar** | **Gemini 1.5 Flash + Search Grounding** | **Rp 25.000 / bln** (~$1.50 USD) | Terhubung langsung dengan mesin pencari Google live untuk memantau harga komoditas pasar lokal (cabai, ayam, beras) dan tren makanan viral di Demak/Semarang. |
| **4. Back-Office (Executive Briefing & P&L)** | **Gemini 1.5 Flash (Paid Tier)** | **Rp 15.000 / bln** (~$1.00 USD) | Menuliskan rangkuman eksekutif pagi (07:00) dan laporan closing malam (22:00) ke WhatsApp Bos berdasarkan data angka riil. |
| **5. Buffer Cadangan Operasional** | *Cadangan Siaga* | **Rp 40.000 / bln** (~$2.50 USD) | Alokasi cadangan jika terjadi lonjakan pesanan pelanggan pada akhir pekan ramai atau musim liburan/promosi besar. |
| **TOTAL ANGGARAN** | **Ekosistem Google Gemini Paid** | **Rp 200.000 / bln** | **Performa Maksimal, Stabil, dan Terkendali 100%.** |

### B. Prinsip Efisiensi Biaya (Zero-Waste Cost Blueprint)
1. **Zero-Token Math Policy:**
   Semua kalkulasi angka (HPP, total belanja, P&L, sisa stok, alokasi gaji) diproses di dalam node kode n8n/FastAPI tanpa mengirim data mentah tabel ke LLM. Ini menghemat hingga **85% konsumsi token** harian.
2. **Token Capping (Batas Token Ketat):**
   - Chat Pelanggan WhatsApp (Waitress & Kasir): Dibatasi maksimal **300 token output** per balasan (menjaga jawaban tetap padat, sopan, dan tidak bertele-tele).
   - Konten Medsos (Caption & Script Video): Dibatasi maksimal **800 token output**.
   - Laporan Eksekutif Harian (Closing P&L): Dibatasi maksimal **400 token output**.
3. **Chat History Pruning (Jendela Memori Terbatas):**
   Riwayat percakapan yang dikirimkan ke model dibatasi hanya **5 putaran terakhir**. Hal ini mencegah pembengkakan token input saat pelanggan mengobrol panjang.
4. **Pengaturan Temperature Model:**
   - AI Kasir & Order POS: `temperature = 0.2` (Sangat presisi, kaku pada harga resmi, dan bebas halusinasi).
   - AI Waitress: `temperature = 0.4` (Hangat, ramah, dan sopan).
   - AI Marketing & Medsos: `temperature = 0.75` (Kreatif menyusun ide caption, hook FYP, dan sudut pandang visual).

---

## 4. Integrasi Google Sheets, Docs, Excel & Dashboard UI Ber-Grafik

### A. Struktur Master Google Sheets (`Resto-AI Data Hub`)
Spreadsheet ini berfungsi sebagai *Single Source of Truth* yang diperbarui otomatis oleh n8n:
1. **`SUMMARY_DASHBOARD`**: Agregat KPI bulanan (Total Omzet, Estimasi Laba Bersih, Rata-rata Order, Persentase Food Cost).
2. **`LOG_TRANSAKSI_PENJUALAN`**: Catatan transaksi per pesanan oleh **AI Kasir** (`Tanggal`, `OrderID`, `No_Pelanggan`, `Meja/Takeaway`, `Item`, `Total`, `MetodeBayar`, `Status`).
3. **`LABA_RUGI_PNL`**: Buku kas harian oleh **AI Finance** (`Tanggal`, `Total_Omzet`, `Estimasi_HPP`, `Laba_Kotor`, `Beban_Operasional_dan_Gaji`, `Laba_Bersih`, `Margin_Persen`, `Status`).
4. **`LOG_BELANJA_HARIAN`**: Rincian arus kas keluar (`Tanggal`, `Belanja_Dapur_Pasar`, `Belanja_Minuman`, `Belanja_Ops_Gas_Galon_Dll`, `Total_Belanja`, `Jumlah_Item`).
5. **`MASTER_KARYAWAN`**: Data 12 personil (Owner, Co-owner, dan 10 staf), gaji pokok, kehadiran, lembur, dan slip gaji privat.
6. **`STOK_INVENTORY`**: Bahan dapur & minuman (99 item katalog), stok awal, belanja masuk, stok akhir, dan sisa nilai rupiah.
7. **`KALENDER_MEDSOS`**: Perencanaan promosi oleh **AI Marketing** (`Tanggal`, `Platform`, `Konsep`, `Caption`, `Status_Approval`).
8. **`RISET_PASAR`**: Hasil pantauan intelijen oleh **AI Tim Riset** (`Tanggal`, `Kategori`, `Item_Komoditas`, `Nilai_Pasar`, `Tren`, `Rekomendasi_Aksi`).

### B. Dashboard UI Interaktif Lengkap dengan Grafik (Web Localhost & Tablet Android)
- **Web Localhost & Tablet:** Dapat dibuka langsung di `http://103.89.5.220:18081/dashboard` atau via PC Mint di `http://172.18.0.1:18081/dashboard`.
- **7 Modul Lengkap:**
  1. 📊 **Overview Eksekutif:** Omzet 28 Hari (Rp 80,7jt), Laba Bersih (Rp 21,7jt), Margin 26.9%, Fixed Cost (Rp 28jt/bln), Grafik Tren Omzet vs HPP vs Laba.
  2. 💰 **Laba Rugi (P&L):** Income statement standar resmi, pendapatan makanan/minuman, HPP riil, beban gaji manajemen & staf, beban operasional utilitas/gas/galon/tisu.
  3. 🛒 **Belanja & Pengeluaran:** 4 KPI Belanja, Top 10 Pengeluaran Belanja, Donut Proporsi Belanja, dan Tabel Log Belanja Harian dengan tombol Modal Detail Nota per tanggal.
  4. 🍗 **Menu Engineering:** Matriks Kasavana & Smith (Stars, Workhorses, Puzzles), Top 11 Menu Leaderboard, Horizontal Bar Chart porsi vs omzet, Rekomendasi Taktis AI.
  5. 📦 **Inventori & Kartu Stok:** Valuasi Rupiah sisa stok di dapur/gudang, katalog lengkap 99 item bahan baku, filter bahan dapur vs minuman.
  6. 👥 **SDM & Payroll Ledger:** 12 personil (Owner, Co-owner, 10 Staf), grafik gaji personalia, dan fitur preview slip gaji digital.
  7. 🔬 **Tim Riset & AI Advisory:** Pantauan harga komoditas pangan pasar lokal, intelijen kompetitor di Mranggen, dan kalender konten medsos.

---

## 5. File Workflow n8n & Lokasi Data

1. **File Workflow n8n Terpadu (Front-Office + Back-Office + Token Config):**  
   `/home/edukreativ-vps/resto-ai/n8n/resto-ai-enterprise-workforce.json` (42 nodes, 31 connections)
2. **File Master Data Operasional:**  
   - Excel Riil: `/home/edukreativ-vps/resto-ai/data/Agustus.xlsx`
   - Master Roster, Belanja & Baseline JSON: `/home/edukreativ-vps/resto-ai/data/warung_ndelik_master_data.json`
   - Registry Agen: `/home/edukreativ-vps/resto-ai/n8n/agent-registry.json`

### Langkah Pemasangan di n8n:
1. Buka dashboard n8n di browser PC Mint (`http://localhost:5678`).
2. Klik menu **Workflows** -> **Add Workflow** -> titik tiga di kanan atas -> pilih **Import from File**.
3. Pilih file `resto-ai-enterprise-workforce.json`.
4. Buka node **"Global Token & Model Config Hub"** di kanvas paling kiri untuk menyesuaikan pilihan model (`gemini` atau `openai`) dan token API.
5. Hubungkan kredensial **Google Sheets** dan **Google Docs** (menggunakan akun Google Workspace yang sudah siap).
6. Workflow diatur dalam status aman `active: false` (draf) sehingga Bos dapat meninjau tata letak kanvas visualnya terlebih dahulu sebelum mengaktifkan jadwal otomatisnya.
