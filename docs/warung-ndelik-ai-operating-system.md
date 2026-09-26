# Warung Ndelik — Sistem Operasi AI

> **Status:** desain implementasi bertahap.  
> **Lokasi:** Mranggen, Demak.  
> **Batas produksi saat ini:** aplikasi Resto-AI masih berstatus staging/simulasi; data transaksi, QRIS, dan laporan keuangan belum boleh disebut pembukuan riil sampai sumber data serta rekonsiliasinya disetujui.

## 1. Sasaran bisnis dan baseline biaya

Sistem ini bertugas membuat Warung Ndelik lebih terukur: pesanan tidak tercecer, stok dapat diprediksi, menu dipantau margin-nya, pemasaran dievaluasi, dan keputusan tetap berada pada owner.

### Asumsi perencanaan yang diberikan owner

- Karyawan: 10 orang.
- Gaji per karyawan: Rp1.500.000 per bulan.
- Total gaji per bulan: **Rp15.000.000**.
- Listrik dan air: **Rp1.500.000** per bulan.
- Biaya tetap minimum per bulan: **Rp16.500.000**.
- Biaya tetap minimum per tahun: **Rp198.000.000**.
- Beban tetap rata-rata per hari (30 hari): **Rp550.000**.

Angka tersebut adalah **baseline perencanaan**, bukan daftar payroll atau bukti pengeluaran. Belum termasuk bahan baku, sewa bila ada, gas, kemasan, ongkir, pajak, perawatan, promosi, dan biaya tak terduga.

### Rumus yang harus dipakai Finance Agent

```text
Pendapatan bersih = pembayaran tervalidasi - refund/void tervalidasi
Margin kotor = pendapatan bersih - HPP bahan baku terpakai
Laba operasional = margin kotor - biaya tetap - biaya variabel - biaya marketing
Titik impas omzet = biaya operasi total / margin kotor rata-rata
```

Tidak ada agent yang boleh menyimpulkan laba, mengubah harga, membayar gaji, atau menyetujui belanja tanpa data sumber dan persetujuan owner.

## 2. Arsitektur sumber kebenaran

```text
Pelanggan WhatsApp / Kasir / Owner
                 |
                 v
          n8n Orchestrator
                 |
   +-------------+--------------+------------------+
   |             |              |                  |
   v             v              v                  v
Resto-AI DB   Google Sheets  Drive/Folder       Web read-only
pesanan/menu  biaya & shift  bukti/tagihan      kompetitor publik
   |             |              |                  |
   +-------------+--------------+------------------+
                 |
                 v
            AI Agents (draft, analisis, alarm)
                 |
                 v
           Owner Approval Gate
                 |
                 +--> tindakan terbatas yang disetujui
```

### Ketentuan data

- **Resto-AI / database** adalah sumber menu, resep, stok, status pesanan, dan total pesanan.
- **Pembayaran** baru dianggap pendapatan setelah webhook/payment provider atau rekonsiliasi kas owner memvalidasi; pesan pelanggan atau foto bukti transfer tidak cukup.
- **Google Sheets atau database operasional privat** menyimpan biaya, absensi, payroll, kampanye, dan target. Hindari menyimpan data itu di prompt atau chat.
- **Riset kompetitor** hanya dari sumber publik dan menyimpan URL, tanggal observasi, kutipan fakta, serta tingkat keyakinan.
- Semua tindakan tulis sensitif wajib meninggalkan audit log: siapa meminta, agent apa, data sumber, keputusan owner, waktu, dan hasil.

## 3. Organisasi AI Warung Ndelik

Setiap agent adalah pekerja terbatas dengan input, output, kualitas, dan batas otoritas yang jelas. Mereka tidak boleh saling memberi persetujuan akhir.

### A. CEO / Orchestrator Agent

- **Misi:** menerima permintaan owner, menentukan agent yang relevan, memeriksa kelengkapan data, dan membuat ringkasan keputusan.
- **Input:** perintah owner terautentikasi, status pekerjaan, laporan semua agent.
- **Output:** job terstruktur dengan status `QUEUED → RUNNING → NEEDS_APPROVAL → COMPLETED/FAILED`.
- **Boleh:** merutekan, menggabungkan laporan, mengingatkan approval yang tertunda.
- **Tidak boleh:** menyetujui pengeluaran, payroll, perubahan harga, publikasi, atau pembayaran.

### B. Finance Controller Agent

- **Misi:** laporan harian/mingguan/bulanan, proyeksi kas, variance terhadap baseline Rp16,5 juta/bulan, dan alarm anomali.
- **Input:** pesanan selesai, pembayaran tervalidasi, biaya operasional, pembelian, refund/void.
- **Output:** pendapatan, HPP, margin, biaya, laba/rugi, arus kas, data yang belum direkonsiliasi.
- **Quality gate:** setiap angka harus punya sumber, periode, dan status `VALIDATED`, `PENDING_RECONCILIATION`, atau `SIMULATED`.
- **Approval:** owner menyetujui tutup buku dan setiap koreksi ledger.

### C. Payroll & People Agent

- **Misi:** membuat draft absensi, komponen payroll, slip gaji, dan rekap biaya SDM.
- **Input:** data 10 karyawan, shift, absensi, izin, lembur, potongan, dan komponen yang disetujui.
- **Output:** draft payroll per orang dan total; tidak mengeksekusi pembayaran.
- **Quality gate:** dua pengecekan: jumlah karyawan aktif dan total payroll harus cocok dengan data HR. Baseline awal Rp15.000.000/bulan hanya berlaku bila semua 10 orang menerima Rp1.500.000 penuh.
- **Akses:** owner/admin HR saja. Tidak pernah melalui route WhatsApp pelanggan.
- **Approval:** owner wajib menyetujui payroll final sebelum file bank/payment dibuat.

### D. Menu, Recipe & Inventory Agent

- **Misi:** menjaga ketersediaan menu, menghitung risiko stok habis, HPP, menu margin rendah, dan draft pembelian.
- **Input:** menu, harga, cost price, resep, stok minimum, stok masuk, pesanan selesai, supplier.
- **Output:** daftar stok kritis, forecast kebutuhan 3/7 hari, menu yang perlu dinonaktifkan, dan purchase request draft.
- **Quality gate:** tidak merekomendasikan pembelian tanpa satuan, stok aktual, dan supplier/estimasi harga.
- **Approval:** owner/penanggung jawab dapur menyetujui belanja dan perubahan menu/harga.

### E. Marketing Growth Agent

- **Misi:** merancang kampanye lokal Mranggen–Demak, mengukur hasil promosi, dan menyiapkan konten.
- **Input:** target omzet, menu unggulan, kapasitas, data transaksi agregat, biaya kampanye, kanal, periode.
- **Output:** brief kampanye, kalender konten, draft caption/visual brief, kode promo draft, CAC/ROAS bila datanya tersedia.
- **Quality gate:** klaim promosi, harga, diskon, dan stok harus ditarik dari data resmi.
- **Approval:** owner menyetujui setiap publikasi, budget, diskon, serta balasan publik yang sensitif.
- **Larangan:** tidak posting otomatis atau membelanjakan iklan tanpa approval eksplisit.

### F. Competitor & Local Market Intelligence Agent

- **Misi:** memantau kompetitor publik di kawasan Mranggen dan Demak untuk menu, harga, promo, rating, dan ulasan berulang.
- **Input:** daftar target yang disetujui owner dan sumber publik seperti Google Maps, Instagram, GoFood/GrabFood bila halaman publik tersedia.
- **Output:** catatan observasi dengan `nama`, `URL`, `tanggal`, `fakta`, `bukti/kutipan`, `confidence`, dan perbandingan.
- **Quality gate:** tidak boleh menyatakan perkiraan sebagai fakta; tidak login, tidak scraping agresif, tidak menghubungi kompetitor.
- **Approval:** rekomendasi perubahan harga/menu selalu diputuskan owner.

### G. Customer Experience & Reputation Agent

- **Misi:** mengelompokkan keluhan, pujian, pertanyaan menu, dan status pesanan; membuat draft respons dan isu layanan mingguan.
- **Input:** chat pelanggan yang diizinkan, rating/ulasan publik, status order.
- **Output:** draft balasan, label isu, SLA tindak lanjut, dan tema keluhan.
- **Quality gate:** tidak menjanjikan refund, kompensasi, ketersediaan, atau waktu antar tanpa aturan yang disetujui.
- **Approval:** kasus refund, alergi, keluhan keselamatan makanan, dan konflik pelanggan dieskalasi ke owner/manajer.

### H. Compliance, Audit & Data Steward Agent

- **Misi:** mengecek kelengkapan audit log, backup, akses role, data yang tidak direkonsiliasi, dan kondisi error workflow.
- **Input:** log workflow, job queue, backup status, daftar credential/role tanpa membaca nilai rahasia.
- **Output:** checklist risiko, pekerjaan gagal, dan rekomendasi pemulihan.
- **Boleh:** membuka tiket perbaikan dan menghentikan workflow berisiko tinggi.
- **Tidak boleh:** melihat/menyalin secret atau menghapus catatan finansial/payroll.

## 4. Workflow n8n target

### 4.1 Lajur pelanggan (sudah ada fondasi)

```text
WhatsApp masuk
  → validasi/idempotensi message ID
  → intent pesanan / menu / reservasi / status
  → Resto-AI API
  → respons pelanggan
  → audit event
```

Workflow saat ini `Resto-AI - WhatsApp Incoming via n8n` hanya menangani lajur ini. Ia **bukan** sistem finance, marketing, kompetitor, atau payroll.

### 4.2 Lajur owner/admin baru

```text
Owner command / schedule
  → autentikasi owner dan role
  → buat job tahan-restart di queue/database
  → CEO Orchestrator
  → Finance | Payroll | Inventory | Marketing | Competitor | CX
  → quality gate
  → owner approval
  → write-back terbatas + audit log
  → laporan WhatsApp/Email/Drive privat
```

### 4.3 Trigger dan ritme kerja

- **Setiap order selesai:** update penjualan, konsumsi resep, cek stok minimum.
- **Setiap pagi:** ringkasan omzet kemarin, order tertunda, stok kritis, reservasi hari ini.
- **Setiap sore:** rekomendasi prep dapur dan follow-up order/keluhan yang belum selesai.
- **Mingguan:** margin menu, efektivitas marketing, ringkasan kompetitor, isu layanan, jadwal konten minggu depan.
- **Tanggal 25–akhir bulan:** payroll draft dari absensi yang sudah disetujui.
- **Akhir bulan:** close book draft, variance biaya, target bulan depan; final hanya setelah rekonsiliasi owner.

### 4.4 Status data dan job wajib

```text
Data: RAW → VALIDATED → RECONCILED → LOCKED
Job:  QUEUED → RUNNING → NEEDS_DATA/NEEDS_APPROVAL → COMPLETED/FAILED
```

Retry hanya untuk kegagalan teknis, maksimal 3 kali dengan backoff. Job yang menulis data harus memakai idempotency key agar tidak membuat payroll, laporan, atau pesan ganda.

## 5. Data minimum sebelum masing-masing agent diaktifkan

- **Finance:** metode pembayaran, transaksi kas harian, biaya bahan, biaya operasional, refund/void, rekening/settlement hanya sebagai referensi privat.
- **Payroll:** nama/ID internal karyawan, status aktif, jabatan, basis gaji, rekening disimpan terenkripsi atau di sistem payroll, absensi, aturan lembur/potongan, periode gaji.
- **Inventory:** satuan bahan, stok awal, threshold, resep dan takaran, supplier, harga beli terakhir.
- **Marketing:** kanal, target, budget maksimum, jadwal, materi yang disetujui, KPI.
- **Kompetitor:** daftar target yang disetujui owner dan frekuensi observasi.

## 6. Prioritas implementasi

1. **Fondasi aman:** role owner/admin, job queue persisten, audit log, data schema biaya/HR/inventory, backup.
2. **Finance + inventory:** laporan harian tervalidasi, stok minimum, HPP dan variance biaya.
3. **Owner dashboard:** perintah WhatsApp owner, laporan otomatis, approval gate.
4. **Payroll privat:** absensi sampai payroll draft dan approval final; belum ada pembayaran otomatis.
5. **Marketing & kompetitor:** riset read-only, konten draft, metrik; publikasi tetap approval manual.
6. **CX & optimasi:** klasifikasi feedback, SLA, menu engineering, forecast.

## 7. KPI owner dashboard

- Omzet tervalidasi harian/bulanan.
- Margin kotor dan laba operasional dengan label kelengkapan data.
- Biaya aktual versus baseline Rp16.500.000/bulan.
- Persentase stok aman, stok kritis, dan waste.
- Menu terlaris, margin tertinggi/terendah, serta kontribusi menu.
- Jumlah order, nilai rata-rata order, waktu proses dapur, pembatalan/refund.
- Biaya marketing, leads, konversi, CAC dan ROAS bila sumber data tersedia.
- Kehadiran, payroll draft, dan approval payroll; data individu hanya terlihat role HR/owner.
- Pekerjaan agent gagal, data belum direkonsiliasi, dan approval tertunda.

## 8. Batas keamanan dan keputusan owner

- Tidak ada agent boleh memindahkan uang, membayar gaji, mengubah rekening, mengaktifkan diskon, memesan barang, atau menerbitkan konten tanpa approval yang tercatat.
- Tidak ada data gaji individu, absensi, atau dokumen karyawan dikirim ke WhatsApp pelanggan.
- Tidak ada angka laba atau omzet yang diberi label final jika payment settlement/kas belum direkonsiliasi.
- Semua connector eksternal dimulai dalam mode read-only/draft.
- Koneksi Meta, Google, marketplace, iklan, dan bank ditambahkan satu per satu setelah owner menyediakan kredensial melalui jalur aman dan menyetujui scope.

## 9. Kondisi selesai setiap tahap

Sebuah modul baru dapat disebut siap hanya bila: schema tersimpan, workflow terimpor, akses role diuji, job bertahan setelah restart, audit log terbaca, input dummy dan error path diuji, serta laporan dibaca kembali dari sumber data. Health check saja tidak membuktikan workflow agent sudah berjalan.
